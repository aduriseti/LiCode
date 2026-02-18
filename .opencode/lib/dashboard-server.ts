import { createDashboardApp } from "./dashboard.app";
import { TerminalManager } from "./terminal.manager";
import express from "express";
import { EventSource } from "eventsource";
import { exec } from "child_process";

const { app, server, io, setupTerminalProxy } = createDashboardApp();

// Middleware to parse JSON bodies
app.use(express.json());

// State
const terminalManager = new TerminalManager(io, { 
    verbose: true, 
    log: (level, msg) => console.log(`[${level.toUpperCase()}] ${msg}`) 
});
setupTerminalProxy(terminalManager);

const activeStreams = new Map<string, EventSource>();
const sessionToAgent = new Map<string, string>();
const agentServerPorts = new Set<number>();

// Cleanup Logic
let dashboardClosed = false;
const cleanup = () => {
    if (dashboardClosed) return;
    dashboardClosed = true;
    console.log("[INFO] Dashboard closed, cleaning up resources...");
    
    activeStreams.forEach(es => es.close());
    terminalManager.close();

    // Bulk cleanup: Kill all agent opencode serve processes in a single pass
    if (agentServerPorts.size > 0) {
        const ports = Array.from(agentServerPorts).join(',');
        // Using -9 to ensure they die immediately as they are isolated agents
        exec(`lsof -ti :${ports} | xargs kill -9 2>/dev/null`, (err) => {
            if (err) console.log(`[DEBUG] Failed to kill servers on ports ${ports}: ${err.message}`);
            else console.log(`[INFO] Killed agent servers on ports ${ports}`);
        });
    }
    agentServerPorts.clear();
    
    server.close(() => {
        console.log("[INFO] Server closed. Exiting process.");
        process.exit(0);
    });
};

// Graceful signal handling
process.on('SIGINT', cleanup);
process.on('SIGTERM', cleanup);

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
    const data = req.body;
    // Support batched logs
    if (data.type === 'batch' && Array.isArray(data.events)) {
        for (const event of data.events) {
            io.emit('log', event);
        }
    } else {
        io.emit('log', data);
    }
    res.sendStatus(200);
});

// POST /api/agent - Register a new agent
app.post('/api/agent', (req, res) => {
    const { api_url, session_id, agent_id, arena_dir } = req.body;
    
    if (!api_url || !agent_id) {
        res.status(400).send("Missing api_url or agent_id");
        return;
    }

    console.log(`[INFO] Registering agent ${agent_id} at ${api_url}`);
    
    // Track for cleanup
    try {
        const port = new URL(api_url).port;
        if (port) agentServerPorts.add(Number(port));
    } catch (e) {}

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
                        } catch (e) {}
                    };
                    activeStreams.set(api_url, es);
                } catch(err) {
                    console.error(`[ERROR] Failed to connect EventSource for ${agent_id}:`, err);
                }
            }
        })()
    ]).catch(err => {
        console.error(`[ERROR] Concurrent agent setup failed for ${agent_id}:`, err);
    });

    res.sendStatus(200);
});

// Start Server - Phase 4: Support injected port
const injectedPort = process.env.DASHBOARD_PORT ? parseInt(process.env.DASHBOARD_PORT) : 0;

server.listen(injectedPort, () => {
    const addr = server.address();
    const assignedPort = typeof addr === 'string' ? 0 : addr?.port;
    console.log(JSON.stringify({ port: assignedPort, url: `http://localhost:${assignedPort}` }));
});