import { createDashboardApp } from "./dashboard.app";
import { TerminalManager, type LogFn } from "./terminal.manager";
import express from "express";
import { EventSource } from "eventsource";
import { exec } from "child_process";
import fs from "fs";

const { app, server, io, setupTerminalProxy } = createDashboardApp();

// Parse log file from arguments if provided
const logFilePath =
    process.argv.indexOf("--log-file") !== -1
        ? process.argv[process.argv.indexOf("--log-file") + 1]
        : null;

// Logging helper to avoid polluting stdout when TUI is parsing JSON
const log: LogFn = (level, msg) => {
    const logLine = `[${new Date().toISOString()}][${level.toUpperCase()}] ${msg}\n`;

    // We use console.error for internal logging to keep stdout clean for the TUI
    // (which specifically parses the JSON port info from stdout).
    console.error(logLine.trim());

    // Also write to persistent log file if configured
    if (logFilePath) {
        try {
            fs.appendFileSync(logFilePath, logLine);
        } catch {
            // If file logging fails, we fallback to just stderr
        }
    }
};

// Middleware to parse JSON bodies
app.use(express.json());

// State
const terminalManager = new TerminalManager(io, {
    verbose: true,
    log: (level, msg) => log(level, msg),
});
setupTerminalProxy(terminalManager);

const activeStreams = new Map<string, EventSource>();
const sessionToAgent = new Map<string, string>();
const agentServerPorts = new Set<number>();
const eventHistory: any[] = [];
const MAX_HISTORY = 10000;

// Cleanup Logic
let dashboardClosed = false;
const cleanup = () => {
    if (dashboardClosed) return;
    dashboardClosed = true;
    log("info", "Dashboard closed, cleaning up resources...");

    activeStreams.forEach((es) => es.close());
    terminalManager.close();

    // Bulk cleanup: Kill all agent opencode serve processes in a single pass
    if (agentServerPorts.size > 0) {
        const ports = Array.from(agentServerPorts).join(",");
        // Using -9 to ensure they die immediately as they are isolated agents
        exec(`lsof -ti :${ports} | xargs kill -9 2>/dev/null`, (err) => {
            if (err)
                console.log(`[DEBUG] Failed to kill servers on ports ${ports}: ${err.message}`);
            else console.log(`[INFO] Killed agent servers on ports ${ports}`);
        });
    }
    agentServerPorts.clear();

    server.close(() => {
        log("info", "Server closed. Exiting process.");
        process.exit(0);
    });
};

// Graceful signal handling
process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);

// Parent Liveness Monitoring
let isParentAlive = true;
// Resume stdin so it stays open and emits 'end' when the pipe closes
process.stdin.resume();
process.stdin.on("data", (_chunk) => {
    // Keep-alive heartbeat from parent, just consume it
});
process.stdin.on("end", () => {
    log("info", "Parent process exited (stdin closed). Starting 60s inactivity timer...");
    isParentAlive = false;
    // Start a 60s grace period for human inspection after parent exits
    setTimeout(() => {
        if (io.engine.clientsCount === 0) {
            log("info", "No clients connected after 60s grace period. Shutting down.");
            cleanup();
        }
    }, 60000);
});

// Auto-shutdown when clients disconnect
io.on("connection", (socket) => {
    // Replay event history to new client
    for (const event of eventHistory) {
        socket.emit("log", event);
    }

    socket.on("disconnect", () => {
        setTimeout(() => {
            // Only consider auto-shutdown if:
            // 1. Parent is dead (tournament finished)
            // 2. No browser clients are currently connected
            if (!isParentAlive && io.engine.clientsCount === 0) {
                log("info", "Inactivity detected after tournament end. Shutting down.");
                cleanup();
            }
        }, 10000); // 10s wait after last disconnect
    });
});

// API Endpoints for Plugin interaction

// POST /api/log - Receive logs from plugin/tournament
app.post("/api/log", (req, res) => {
    const data = req.body;
    // Support batched logs
    if (data.type === "batch" && Array.isArray(data.events)) {
        for (const event of data.events) {
            if (eventHistory.length >= MAX_HISTORY) eventHistory.shift();
            eventHistory.push(event);
            io.emit("log", event);
        }
    } else {
        if (eventHistory.length >= MAX_HISTORY) eventHistory.shift();
        eventHistory.push(data);
        io.emit("log", data);
    }
    res.sendStatus(200);
});

// POST /api/agent - Register a new agent
app.post("/api/agent", (req, res) => {
    const { api_url, session_id, agent_id, arena_dir } = req.body;

    if (!api_url || !agent_id) {
        res.status(400).send("Missing api_url or agent_id");
        return;
    }

    log("info", `Registering agent ${agent_id} at ${api_url}`);

    // Track for cleanup
    try {
        const url = new URL(api_url);
        if (url.port) agentServerPorts.add(Number(url.port));
    } catch {
        log("error", `Failed to parse agent URL for cleanup: ${api_url}`);
    }

    sessionToAgent.set(session_id, agent_id);

    // Phase 4: Parallelize registration and stream setup
    Promise.all([
        (async () => {
            terminalManager.registerAgent(agent_id, api_url, session_id, arena_dir);
            terminalManager.spawnTerminal(agent_id);
        })(),
        (async () => {
            if (api_url && !activeStreams.has(api_url)) {
                try {
                    const es = new EventSource(`${api_url}/event`);
                    es.onmessage = (msg: MessageEvent) => {
                        try {
                            const evt = JSON.parse(msg.data);
                            if (evt.type === "message.part.updated") {
                                const part = evt.properties?.part;
                                const delta = evt.properties?.delta;

                                if (part && part.sessionID && delta) {
                                    const aid = sessionToAgent.get(part.sessionID);
                                    if (aid) {
                                        io.emit("log", {
                                            type: "agent_stream",
                                            agent_id: aid,
                                            text: delta,
                                            timestamp: new Date().toLocaleTimeString(),
                                        });
                                    }
                                }
                            }
                        } catch {
                            /* ignore */
                        }
                    };
                    activeStreams.set(api_url, es);
                } catch (err) {
                    console.error(`[ERROR] Failed to connect EventSource for ${agent_id}:`, err);
                }
            }
        })(),
    ]).catch((err) => {
        console.error(`[ERROR] Concurrent agent setup failed for ${agent_id}:`, err);
    });

    res.sendStatus(200);
});

// Start Server - Phase 4: Support injected port
const injectedPort = process.env.DASHBOARD_PORT ? parseInt(process.env.DASHBOARD_PORT) : 0;

server.listen(injectedPort, () => {
    const addr = server.address();
    const assignedPort = typeof addr === "string" ? 0 : addr?.port;
    console.log(JSON.stringify({ port: assignedPort, url: `http://localhost:${assignedPort}` }));
});
