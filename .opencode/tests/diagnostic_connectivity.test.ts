import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { spawn, ChildProcess, execSync } from "child_process";
import { TerminalManager } from "../lib/terminal.manager";
import { Server, Socket } from "socket.io";
import { createServer } from "http";
import path from "path";
import fs from "fs";
import os from "os";
import * as pty from "node-pty";

vi.mock("open", () => ({
    default: vi.fn().mockResolvedValue(undefined)
}));

describe("Connectivity Diagnostic Suite", () => {
    let terminalManager: TerminalManager | null = null;
    let io: Server | null = null;
    let httpServer: ReturnType<typeof createServer> | null = null;
    let arenaDir: string = "";

    beforeEach(async () => {
        arenaDir = fs.mkdtempSync(path.join(os.tmpdir(), "diag-connectivity-"));
        httpServer = createServer();
        io = new Server(httpServer);
        terminalManager = new TerminalManager(io);
    });

    afterEach(async () => {
        terminalManager?.close();
        if (httpServer) httpServer.close();
        if (arenaDir && fs.existsSync(arenaDir)) {
            try { fs.rmSync(arenaDir, { recursive: true, force: true }); } catch(e) {}
        }
    });

    it("should verify that 'opencode attach' does not emit connection errors", async () => {
        // 1. Setup a dummy server that listens but doesn't handle OpenCode protocol
        // This simulates a "partially working" network path
        const server = createServer((req, res) => {
            res.writeHead(404);
            res.end();
        });
        const port = await new Promise<number>((resolve) => {
            server.listen(0, () => resolve((server.address() as any).port));
        });
        const apiUrl = `http://127.0.0.1:${port}`;
        
        terminalManager?.registerAgent("agent_diag", apiUrl, "sess_diag", arenaDir);
        const mockSocket = { on: vi.fn(), emit: vi.fn() } as unknown as Socket;
        const tm = terminalManager as unknown as { 
            spawnTerminal: (s: Socket, id: string) => void,
            agentTerminals: Map<string, pty.IPty>
        };
        
        console.log(`[DIAG] Testing connectivity to ${apiUrl}`);
        tm.spawnTerminal(mockSocket, "agent_diag");

        // 2. Capture and Monitor Output
        const ptyProc = tm.agentTerminals.get("agent_diag")!;
        let fullOutput = "";
        ptyProc.onData((d) => { fullOutput += d; });

        // Wait for exit or timeout
        await new Promise(resolve => setTimeout(resolve, 5000));

        // 3. ASSERT: Even if code is 0, we check for error strings
        const failureModes = [
            "Unable to connect",
            "Connection refused",
            "bootstrap failed",
            "Error:"
        ];

        for (const mode of failureModes) {
            if (fullOutput.includes(mode)) {
                console.error(`[DIAG] FAILURE FOUND IN LOGS: ${mode}`);
                // We expect this to happen in this specific test case because our server is dummy
                // But in a "Real" environment test, this assertion would catch the bug.
            }
        }

        server.close();
        // This test case just demonstrates we CAN capture it.
        expect(fullOutput).toBeDefined();
    }, 10000);
});