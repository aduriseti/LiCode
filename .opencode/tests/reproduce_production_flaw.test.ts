import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { spawn, ChildProcess } from "child_process";
import { TerminalManager } from "../lib/terminal.manager";
import { Server, Socket } from "socket.io";
import { createServer } from "http";
import path from "path";
import fs from "fs";
import * as pty from "node-pty";

describe("Production Flaw Reproduction (Real Python Backend)", () => {
    let pythonProcess: ChildProcess | null = null;
    let terminalManager: TerminalManager | null = null;
    let io: Server | null = null;
    let httpServer: ReturnType<typeof createServer> | null = null;

    afterEach(async () => {
        terminalManager?.close();
        if (pythonProcess) pythonProcess.kill();
        if (httpServer) httpServer.close();
    });

    it("should successfully attach to a REAL Python-driven session and render the prompt", async () => {
        // 1. Start the REAL Python Tournament
        // Path logic: process.cwd() is /workspaces/LiCode/.opencode
        const workspaceRoot = path.join(process.cwd(), "..");
        pythonProcess = spawn("python3", ["-m", "market.cli", "run", "--prompt", "implement fibonacci", "--agents", "1", "--rounds", "1", "--json-logs"], {
            cwd: workspaceRoot,
            env: { ...process.env, PYTHONPATH: workspaceRoot }
        });

        let apiUrl = "";
        let sessionId = "";
        let arenaDir = "";

        // 2. Extract real session info from Python JSON stream
        await new Promise<void>((resolve, reject) => {
            const timeout = setTimeout(() => reject(new Error("Python startup timed out")), 60000);
            let buffer = "";

            pythonProcess?.stderr?.on("data", (chunk) => {
                console.log(`[PYTHON-STDERR] ${chunk.toString()}`);
            });

            pythonProcess?.stdout?.on("data", (chunk) => {
                const text = chunk.toString();
                buffer += text;
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
                        // WAIT for the first turn to actually begin
                        if (event.type === "log" && event.message.includes("Collecting agent actions")) {
                            clearTimeout(timeout);
                            resolve();
                        }
                    } catch (e) {}
                }
            });
        });

        console.log(`[REPRO] Real Agent Found: ${sessionId} at ${apiUrl}`);

        // 3. Setup TerminalManager
        httpServer = createServer();
        io = new Server(httpServer);
        terminalManager = new TerminalManager(io);
        terminalManager.registerAgent("agent_0", apiUrl, sessionId, arenaDir);

        // 4. Trigger attachment using the REAL Manager logic
        let tuiDataReceived = false;
        let totalTuiBuffer = "";
        const mockSocket = { 
            on: vi.fn(), 
            emit: vi.fn().mockImplementation((event, data) => {
                if (event === "terminal.output" && data.data && data.data.length > 0) {
                    tuiDataReceived = true;
                    totalTuiBuffer += data.data;
                }
            }) 
        } as unknown as Socket;

        const tm = terminalManager as unknown as { 
            spawnTerminal: (s: Socket, id: string) => void,
            agentTerminals: Map<string, pty.IPty>
        };
        
        tm.spawnTerminal(mockSocket, "agent_0");

        // 5. THE PERSISTENCE ASSERTION
        // Give it more time to render the TUI (30s instead of 20s)
        await new Promise(resolve => setTimeout(resolve, 30000));

        const ptyProc = tm.agentTerminals.get("agent_0");

        console.log(`[REPRO] TUI Buffer Length: ${totalTuiBuffer.length}`);
        
        // Let's print a clean version of the buffer (stripping some ANSI)
        const cleanBuffer = totalTuiBuffer.replace(/[\u001b\u009b][[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]/g, '');
        console.log(`[REPRO] Cleaned TUI Sample: ${JSON.stringify(cleanBuffer.substring(0, 1000))}`);

        expect(ptyProc, "Terminal process exited prematurely").toBeDefined();
        expect(tuiDataReceived, "No TUI data received").toBe(true);
        // Assert against cleanBuffer to avoid ANSI issues, use a more flexible check
        expect(cleanBuffer.toLowerCase()).toContain("fibonacci");
    }, 60000);
});