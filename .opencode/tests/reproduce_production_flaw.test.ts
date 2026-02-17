import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { spawn, ChildProcess } from "child_process";
import { TerminalManager } from "../lib/terminal.manager";
import { Server } from "socket.io";
import { createServer } from "http";
import path from "path";
import fs from "fs";
import os from "os";
import WebSocket from "ws";

const ANSI_RE = /[\u001b\u009b][\[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[^[\]]/g;

describe("Production Flaw Reproduction (Real Python Backend)", () => {
    let pythonProcess: ChildProcess | null = null;
    let terminalManager: TerminalManager | null = null;
    let io: Server | null = null;
    let httpServer: ReturnType<typeof createServer> | null = null;
    let logFile: string = "";
    let logFd: number = -1;

    const logToFile = (msg: string) => {
        if (logFd >= 0) fs.writeSync(logFd, msg + "\n");
    };

    beforeEach(() => {
        logFile = path.join(os.tmpdir(), `repro-pty-${Date.now()}.log`);
        logFd = fs.openSync(logFile, "w");
    });

    afterEach(async () => {
        terminalManager?.close();
        if (pythonProcess) pythonProcess.kill();
        if (httpServer) httpServer.close();
        if (logFd >= 0) { fs.closeSync(logFd); logFd = -1; }
    });

    it("should spawn helper process that attaches to a REAL session", async () => {
        const workspaceRoot = path.join(process.cwd(), "..");
        pythonProcess = spawn("python3", ["-m", "market.cli", "run", "--prompt", "implement fibonacci", "--agents", "1", "--rounds", "1", "--json-logs"], {
            cwd: workspaceRoot,
            env: { ...process.env, PYTHONPATH: workspaceRoot, TERM: "dumb" },
            stdio: ['ignore', 'pipe', 'pipe']
        });

        let apiUrl = "";
        let sessionId = "";
        let arenaDir = "";

        await new Promise<void>((resolve, reject) => {
            const timeout = setTimeout(() => reject(new Error("Python startup timed out")), 60000);
            let buffer = "";

            pythonProcess?.stderr?.on("data", (chunk) => {
                logToFile(`[PYTHON-STDERR] ${chunk.toString()}`);
            });

            pythonProcess?.stdout?.on("data", (chunk) => {
                buffer += chunk.toString();
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";

                for (const line of lines) {
                    try {
                        const event = JSON.parse(line);
                        if (event.type === "agent_init") {
                            apiUrl = event.api_url;
                            sessionId = event.session_id;
                            arenaDir = event.arena_dir;
                        }
                        if (event.type === "log" && event.message.includes("Collecting agent actions")) {
                            clearTimeout(timeout);
                            resolve();
                        }
                    } catch (e) {}
                }
            });
        });

        logToFile(`[REPRO] Real Agent Found: ${sessionId} at ${apiUrl}`);

        // Setup TerminalManager with real Socket.IO server
        httpServer = createServer();
        io = new Server(httpServer);
        terminalManager = new TerminalManager(io, { verbose: true });
        terminalManager.registerAgent("agent_0", apiUrl, sessionId, arenaDir);

        terminalManager.spawnTerminal("agent_0");

        // Wait for helper to report ready
        let helperPort = 0;
        await new Promise<void>((resolve) => {
            const check = setInterval(() => {
                const port = terminalManager!.getHelperPort("agent_0");
                if (port) { helperPort = port; clearInterval(check); resolve(); }
            }, 100);
            setTimeout(() => { clearInterval(check); resolve(); }, 10000);
        });

        logToFile(`[REPRO] Helper ready on port ${helperPort}`);
        expect(helperPort).toBeGreaterThan(0);

        // Connect to helper via WebSocket and collect data
        let tuiBuffer = "";
        const ws = new WebSocket(`ws://127.0.0.1:${helperPort}`);
        await new Promise<void>((resolve, reject) => {
            ws.on("open", resolve);
            ws.on("error", reject);
            setTimeout(() => reject(new Error("WS connect timed out")), 5000);
        });

        ws.on("message", (raw) => {
            try {
                const msg = JSON.parse(raw.toString());
                if (msg.type === "data" || msg.type === "buffer") {
                    tuiBuffer += msg.data;
                }
            } catch (e) {}
        });

        // Wait for TUI data
        await new Promise(resolve => setTimeout(resolve, 15000));

        ws.close();
        const cleanBuffer = tuiBuffer.replace(ANSI_RE, '');
        logToFile(`[REPRO] TUI Buffer Length: ${tuiBuffer.length}`);
        logToFile(`[REPRO] Cleaned TUI Sample: ${cleanBuffer.substring(0, 1000)}`);
        console.log(`[REPRO] PTY debug log: ${logFile}`);

        expect(tuiBuffer.length).toBeGreaterThan(0);
    }, 60000);
});
