import { createDashboardApp } from "./dashboard.app";
import { TerminalManager, type LogFn } from "./terminal.manager";
import express from "express";
import { EventSource } from "eventsource";
import { exec } from "child_process";
import fs from "fs";

const { app, server, io, setupTerminalProxy } = createDashboardApp();

// Parse log file from arguments if provided
const logFilePath = process.argv.indexOf("--log-file") !== -1 
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
        } catch (e) {
            // If file logging fails, we fallback to just stderr
        }
    }
};

// Middleware to parse JSON bodies
app.use(express.json());

// State
const terminalManager = new TerminalManager(io, { verbose: true, log });
setupTerminalProxy(terminalManager);

const activeStreams = new Map<string, EventSource>();
const sessionToAgent = new Map<string, string>();
const agentServerPorts = new Set<number>();

// Cleanup Logic
let dashboardClosed = false;
const cleanup = () => {
    if (dashboardClosed) return;
    dashboardClosed = true;
    log("info", "Dashboard closed, cleaning up resources...");
    
    activeStreams.forEach(es => es.close());
    terminalManager.close();

    // Kill agent opencode serve processes by port
    for (const port of agentServerPorts) {
        exec(`lsof -ti :${port}`, (err, stdout) => {
            if (err || !stdout) {
                // lsof returns 1 if no PIDs found, or stdout might be empty
                return;
            }
            const pids = stdout.trim().split('\n').filter(Boolean);
            if (pids.length > 0) {
                exec(`kill ${pids.join(' ')}`, (killErr) => {
                    if (killErr) log("debug", `Failed to kill server on port ${port}: ${killErr.message}`);
                    else log("info", `Killed agent server on port ${port}`);
                });
            }
        });
    }
    agentServerPorts.clear();
    
    server.close(() => {
        log("info", "Server closed. Exiting process.");
        process.exit(0);
    });
};

// Auto-shutdown when clients disconnect
io.on('connection', (socket) => {
    socket.on('disconnect', () => {
        setTimeout(() => {
            if (io.engine.clientsCount === 0) {
                cleanup();
            }
        }, 5000);
    });
});

// API Endpoints for Plugin interaction

// POST /api/log - Receive logs from plugin/tournament
app.post('/api/log', (req, res) => {
    const event = req.body;
    io.emit('log', event);
    res.sendStatus(200);
});

// POST /api/agent - Register a new agent
app.post('/api/agent', (req, res) => {
    const { api_url, session_id, agent_id, arena_dir } = req.body;
    
    if (!api_url || !agent_id) {
        res.status(400).send("Missing api_url or agent_id");
        return;
    }

    log("info", `Registering agent ${agent_id} at ${api_url}`);
    
    // Track for cleanup
    try {
        const port = new URL(api_url).port;
        if (port) agentServerPorts.add(Number(port));
    } catch (e) {
        log("error", `Failed to parse agent URL for cleanup: ${api_url} - ${e}`);
    }

    sessionToAgent.set(session_id, agent_id);
    terminalManager.registerAgent(agent_id, api_url, session_id, arena_dir);
    terminalManager.spawnTerminal(agent_id);

    // Setup EventSource for agent streams
    if (api_url && !activeStreams.has(api_url)) {
        try {
            const es = new EventSource(`${api_url}/event`);
            es.onmessage = (msg: MessageEvent) => {
                try {
                    const evt = JSON.parse(msg.data);
                    if (evt.type === 'message.part.updated') {
                        const part = evt.properties?.part;
                        const delta = evt.properties?.delta;
                        
                        if (part && part.sessionID && delta) {
                            const aid = sessionToAgent.get(part.sessionID);
                            if (aid) {
                                io.emit('log', {
                                    type: 'agent_stream',
                                    agent_id: aid,
                                    text: delta,
                                    timestamp: new Date().toLocaleTimeString()
                                });
                            }
                        }
                    }
                } catch (e) {
                    log("error", `Failed to parse EventSource message for ${agent_id}: ${e}`);
                }
            };
            es.onerror = (err) => {
                 log("error", `EventSource for ${api_url} encountered an error: ${JSON.stringify(err)}`);
            };
            activeStreams.set(api_url, es);
        } catch(err) {
            log("error", `Failed to connect EventSource for ${agent_id}: ${err}`);
        }
    }

    res.sendStatus(200);
});

// Start Server
const port = 0; // Random port
server.listen(port, () => {
    const addr = server.address();
    const assignedPort = typeof addr === 'string' ? 0 : addr?.port;
    console.log(JSON.stringify({ port: assignedPort, url: `http://localhost:${assignedPort}` }));
});
