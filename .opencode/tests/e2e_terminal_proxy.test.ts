import { describe, it, expect, afterEach } from "vitest";
import { createServer } from "http";
import { _Server } from "socket.io";
import { TerminalManager } from "../lib/terminal.manager";
import { createDashboardApp } from "../lib/dashboard.app";
import WebSocket from "ws";
import * as pty from "node-pty";

// End-to-end test: verifies the full path
// browser -> ws proxy on dashboard server -> helper process -> pty -> opencode attach
// This is the test that would have caught the "dashboard not connecting" bug.

describe("E2E Terminal WebSocket Proxy", () => {
    let dashboardServer: ReturnType<typeof createServer> | null = null;
    let terminalManager: TerminalManager | null = null;
    let dashboardPort: number = 0;

    afterEach(() => {
        terminalManager?.close();
        if (dashboardServer) dashboardServer.close();
    });

    it("should proxy WebSocket from dashboard to helper and receive PTY data", async () => {
        // 1. Set up dashboard server with proxy
        const { server, io, setupTerminalProxy } = createDashboardApp();
        dashboardServer = server;
        terminalManager = new TerminalManager(io);
        setupTerminalProxy(terminalManager);

        dashboardPort = await new Promise<number>((resolve) => {
            server.listen(0, () => resolve((server.address() as any).port));
        });

        // 2. Start a real opencode serve instance
        const { spawn } = await import("child_process");
        const srvProc = spawn("/home/codespace/.opencode/bin/opencode", ["serve", "--port", "0"], {
            stdio: ["ignore", "pipe", "pipe"],
            env: { ...process.env, TERM: "dumb" },
        });

        let srvUrl = "";
        await new Promise<void>((resolve, reject) => {
            const timeout = setTimeout(() => reject(new Error("serve startup timed out")), 15000);
            const handler = (chunk: Buffer) => {
                const m = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
                if (m && !srvUrl) {
                    srvUrl = m[0];
                    clearTimeout(timeout);
                    resolve();
                }
            };
            srvProc.stdout!.on("data", handler);
            srvProc.stderr!.on("data", handler);
        });

        // 3. Register agent and spawn helper
        terminalManager.registerAgent("test_agent", srvUrl, "nonexistent_session", "/tmp");
        terminalManager.spawnTerminal("test_agent");

        // 4. Wait for helper to be ready
        await new Promise<void>((resolve) => {
            const check = setInterval(() => {
                if (terminalManager!.getHelperPort("test_agent")) {
                    clearInterval(check);
                    resolve();
                }
            }, 100);
            setTimeout(() => {
                clearInterval(check);
                resolve();
            }, 10000);
        });

        expect(terminalManager.getHelperPort("test_agent")).toBeGreaterThan(0);

        // 5. Connect via the PROXY path (like a browser would)
        let receivedData = "";
        let validMessages = 0;
        let parseErrors = 0;
        const ws = new WebSocket(`ws://127.0.0.1:${dashboardPort}/terminal/test_agent`);

        await new Promise<void>((resolve, reject) => {
            ws.on("open", resolve);
            ws.on("error", reject);
            setTimeout(() => reject(new Error("proxy WS timed out")), 5000);
        });

        ws.on("message", (raw) => {
            try {
                const msg = JSON.parse(raw.toString());
                if (
                    (msg.type === "data" || msg.type === "buffer") &&
                    typeof msg.data === "string"
                ) {
                    validMessages++;
                    receivedData += msg.data;
                }
            } catch {
                parseErrors++;
            }
        });

        // 6. Wait for TUI data
        await new Promise((resolve) => setTimeout(resolve, 5000));

        ws.close();
        srvProc.kill();

        // 7. Verify we received valid, parseable terminal messages (not corrupted data)
        expect(parseErrors).toBe(0);
        expect(validMessages).toBeGreaterThan(0);
        expect(receivedData.length).toBeGreaterThan(0);
    }, 30000);

    it("should keep helper alive after PTY exits and serve buffer to new connections", async () => {
        const { server, io, setupTerminalProxy } = createDashboardApp();
        dashboardServer = server;
        terminalManager = new TerminalManager(io);
        setupTerminalProxy(terminalManager);

        dashboardPort = await new Promise<number>((resolve) => {
            server.listen(0, () => resolve((server.address() as any).port));
        });

        const { spawn } = await import("child_process");
        const srvProc = spawn("/home/codespace/.opencode/bin/opencode", ["serve", "--port", "0"], {
            stdio: ["ignore", "pipe", "pipe"],
            env: { ...process.env, TERM: "dumb" },
        });

        let srvUrl = "";
        await new Promise<void>((resolve, reject) => {
            const timeout = setTimeout(() => reject(new Error("serve startup timed out")), 15000);
            const handler = (chunk: Buffer) => {
                const m = chunk.toString().match(/http:\/\/127\.0\.0\.1:\d+/);
                if (m && !srvUrl) {
                    srvUrl = m[0];
                    clearTimeout(timeout);
                    resolve();
                }
            };
            srvProc.stdout!.on("data", handler);
            srvProc.stderr!.on("data", handler);
        });

        terminalManager.registerAgent("survivor", srvUrl, "nonexistent_session", "/tmp");
        terminalManager.spawnTerminal("survivor");

        await new Promise<void>((resolve) => {
            const check = setInterval(() => {
                if (terminalManager!.getHelperPort("survivor")) {
                    clearInterval(check);
                    resolve();
                }
            }, 100);
            setTimeout(() => {
                clearInterval(check);
                resolve();
            }, 10000);
        });

        const helperPort = terminalManager.getHelperPort("survivor");
        expect(helperPort).toBeGreaterThan(0);

        // First connection: get initial data
        const ws1 = new WebSocket(`ws://127.0.0.1:${dashboardPort}/terminal/survivor`);
        let firstData = "";
        await new Promise<void>((resolve, reject) => {
            ws1.on("open", resolve);
            ws1.on("error", reject);
            setTimeout(() => reject(new Error("ws1 timed out")), 5000);
        });
        ws1.on("message", (raw) => {
            try {
                const msg = JSON.parse(raw.toString());
                if (msg.type === "data" || msg.type === "buffer") firstData += msg.data;
            } catch {
                /* ignore */
            }
        });

        await new Promise((resolve) => setTimeout(resolve, 3000));
        ws1.close();
        expect(firstData.length).toBeGreaterThan(0);

        // Kill the serve process (simulates PTY exit after tournament ends)
        srvProc.kill("SIGKILL");
        await new Promise((resolve) => setTimeout(resolve, 2000));

        // Helper should still be alive -- new connection should get buffered output
        const ws2 = new WebSocket(`ws://127.0.0.1:${dashboardPort}/terminal/survivor`);
        let bufferData = "";
        let _gotExit = false;
        await new Promise<void>((resolve, reject) => {
            ws2.on("open", resolve);
            ws2.on("error", reject);
            setTimeout(() => reject(new Error("ws2 timed out")), 5000);
        });
        ws2.on("message", (raw) => {
            try {
                const msg = JSON.parse(raw.toString());
                if (msg.type === "buffer") bufferData += msg.data;
                if (msg.type === "exit") _gotExit = true;
            } catch {
                /* ignore */
            }
        });

        await new Promise((resolve) => setTimeout(resolve, 2000));
        ws2.close();

        // Buffer replay should contain the earlier session data
        expect(bufferData.length).toBeGreaterThan(0);
    }, 30000);
});
