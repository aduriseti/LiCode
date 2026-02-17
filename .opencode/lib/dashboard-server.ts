import { createDashboardApp } from "./dashboard.app";
import { TerminalManager } from "./terminal.manager";
import express from "express";
import { EventSource } from "eventsource";
import { exec } from "child_process";

const { app, server, io, setupTerminalProxy } = createDashboardApp();

// Middleware to parse JSON bodies
app.use(express.json());

// State
const terminalManager = new TerminalManager(io, { verbose: true, log: (level, msg) => console.log(`[${level.toUpperCase()}] ${msg}`) });
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

    // Kill agent opencode serve processes by port
    for (const port of agentServerPorts) {
        exec(`lsof -ti :${port} | xargs kill 2>/dev/null`, (err) => {
            if (err) console.log(`[DEBUG] Failed to kill server on port ${port}: ${err.message}`);
            else console.log(`[INFO] Killed agent server on port ${port}`);
        });
    }
    agentServerPorts.clear();
    
    server.close(() => {
        console.log("[INFO] Server closed. Exiting process.");
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

    console.log(`[INFO] Registering agent ${agent_id} at ${api_url}`);
    
    // Track for cleanup
    try {
        const port = new URL(api_url).port;
        if (port) agentServerPorts.add(Number(port));
    } catch (e) {}

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
                } catch (e) {}
            };
            es.onerror = () => {
                 // specific error handling if needed
            };
            activeStreams.set(api_url, es);
        } catch(err) {
            console.error(`[ERROR] Failed to connect EventSource for ${agent_id}:`, err);
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
