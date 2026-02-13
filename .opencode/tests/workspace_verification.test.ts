import { describe, it, expect, afterEach, vi } from "vitest";
import { spawn, ChildProcess } from "child_process";
import path from "path";
import { TerminalManager } from "../lib/terminal.manager";
import { Server } from "socket.io";

describe("Workspace Automated Verification", () => {
    let pythonProcess: ChildProcess | null = null;
    let terminalManager: TerminalManager | null = null;

    const killProcessGroup = (child: ChildProcess | null) => {
        if (child && child.pid) {
            try { process.kill(-child.pid, "SIGKILL"); } catch (e) {}
        }
    };

    afterEach(() => {
        killProcessGroup(pythonProcess);
        if (terminalManager) terminalManager.close();
    });

    it("should verify TUI title, code snippets, and progress indicators within 120s", async () => {
        const workspaceRoot = path.join(process.cwd(), "..");
        
        pythonProcess = spawn("python3", [
            "-m", "market.cli", "run", 
            "--prompt", "implement fibonacci", 
            "--agents", "1", 
            "--rounds", "2", 
            "--json-logs"
        ], {
            cwd: workspaceRoot,
            env: { ...process.env, PYTHONPATH: workspaceRoot },
            detached: true
        });

        const io = new Server();
        terminalManager = new TerminalManager(io);

        let foundTitle = false;
        let foundCode = false;
        let foundProgress = false;

        await new Promise<void>((resolve, reject) => {
            const testTimeout = setTimeout(() => {
                killProcessGroup(pythonProcess);
                reject(new Error(`TUI Verification timed out.
Found Title: ${foundTitle}
Found Code: ${foundCode}
Found Progress: ${foundProgress}`));
            }, 120000);

            let buffer = "";
            pythonProcess?.stdout?.on("data", (chunk) => {
                buffer += chunk.toString();
                const lines = buffer.split("\n");
                buffer = lines.pop() || "";

                for (const line of lines) {
                    if (!line.trim().startsWith("{")) continue;
                    try {
                        const event = JSON.parse(line);
                        if (event.type === "agent_init") {
                            const mockSocket = {
                                on: vi.fn(),
                                emit: (ev: string, data: any) => {
                                    if (ev === "terminal.output") {
                                        const text = data.data;
                                        // console.log(`[PTY-DATA] ${text.substring(0, 50)}`);
                                        if (text.includes("OC |")) foundTitle = true;
                                        // Catch implementation OR test assertions
                                        if (text.includes("a, b = b, a + b") || text.includes("def fib") || text.includes("self.assertEqual(fib")) foundCode = true;
                                        if (text.includes("▣")) foundProgress = true;

                                        if (foundTitle && foundCode && foundProgress) {
                                            clearTimeout(testTimeout);
                                            killProcessGroup(pythonProcess);
                                            resolve();
                                        }
                                    }
                                }
                            } as any;
                            
                            terminalManager?.registerAgent(event.agent_id, event.api_url, event.session_id, event.arena_dir);
                            (terminalManager as any).spawnTerminal(mockSocket, event.agent_id);
                        }
                    } catch (e) {}
                }
            });

            pythonProcess?.on("exit", (code) => {
                if (code !== 0 && !foundTitle && !foundCode && !foundProgress) {
                    clearTimeout(testTimeout);
                    reject(new Error(`Orchestrator exited early with code ${code}`));
                }
            });
        });

        expect(foundTitle).toBe(true);
        expect(foundCode).toBe(true);
        expect(foundProgress).toBe(true);
    }, 130000);
});
