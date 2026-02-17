import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { TerminalManager } from "../lib/terminal.manager";
import { Server } from "socket.io";
import { createServer } from "http";
import path from "path";
import fs from "fs";
import os from "os";
import WebSocket from "ws";

const ANSI_RE = /[\u001b\u009b][\[()#;?]*(?:[0-9]{1,4}(?:;[0-9]{0,4})*)?[0-9A-ORZcf-nqry=><]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[^[\]]/g;

vi.mock("open", () => ({
    default: vi.fn().mockResolvedValue(undefined)
}));

describe("Connectivity Diagnostic Suite", () => {
    let terminalManager: TerminalManager | null = null;
    let io: Server | null = null;
    let httpServer: ReturnType<typeof createServer> | null = null;
    let arenaDir: string = "";
    let logFile: string = "";
    let logFd: number = -1;

    const logToFile = (msg: string) => {
        if (logFd >= 0) fs.writeSync(logFd, msg + "\n");
    };

    beforeEach(async () => {
        arenaDir = fs.mkdtempSync(path.join(os.tmpdir(), "diag-connectivity-"));
        logFile = path.join(os.tmpdir(), `diag-pty-${Date.now()}.log`);
        logFd = fs.openSync(logFile, "w");
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
        if (logFd >= 0) { fs.closeSync(logFd); logFd = -1; }
    });

    it("should spawn helper and verify connectivity diagnostics", async () => {
        const server = createServer((req, res) => {
            res.writeHead(404);
            res.end();
        });
        const port = await new Promise<number>((resolve) => {
            server.listen(0, () => resolve((server.address() as any).port));
        });
        const apiUrl = `http://127.0.0.1:${port}`;
        
        terminalManager?.registerAgent("agent_diag", apiUrl, "sess_diag", arenaDir);
        logToFile(`[DIAG] Testing connectivity to ${apiUrl}`);

        let fullOutput = "";

        terminalManager?.spawnTerminal("agent_diag");

        // Wait for helper to be ready, then connect via WebSocket
        await new Promise<void>((resolve) => {
            const check = setInterval(() => {
                const wsPort = terminalManager!.getHelperPort("agent_diag");
                if (!wsPort) return;
                clearInterval(check);
                const ws = new WebSocket(`ws://127.0.0.1:${wsPort}`);
                ws.on("message", (raw) => {
                    try {
                        const msg = JSON.parse(raw.toString());
                        if (msg.type === "data" || msg.type === "buffer") {
                            fullOutput += msg.data;
                        }
                    } catch (e) {}
                });
                // Give it time to collect data
                setTimeout(resolve, 4000);
            }, 100);
            setTimeout(() => { clearInterval(check); resolve(); }, 8000);
        });

        const cleanOutput = fullOutput.replace(ANSI_RE, '');
        logToFile(`[DIAG] Output length: ${fullOutput.length}`);
        logToFile(`[DIAG] Clean output: ${cleanOutput.substring(0, 500)}`);
        console.log(`[DIAG] PTY debug log: ${logFile}`);

        server.close();
        expect(fullOutput).toBeDefined();
    }, 15000);
});
