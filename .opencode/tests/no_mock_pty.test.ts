import { describe, it, expect } from "vitest";
import * as pty from "node-pty";
import os from "os";

describe("Zero-Mock PTY Verification", () => {
    it("should successfully spawn a real bash process and capture output", async () => {
        const shell = os.platform() === 'win32' ? 'powershell.exe' : 'bash';
        
        // Spawn a real shell
        const ptyProcess = pty.spawn(shell, ["-c", "echo 'PTY_WORKING'"], {
            name: 'xterm-color',
            cols: 80,
            rows: 24,
            cwd: process.cwd(),
            env: process.env
        });

        const outputPromise = new Promise<string>((resolve, reject) => {
            let buffer = "";
            const timeout = setTimeout(() => reject(new Error("PTY timed out")), 5000);

            ptyProcess.onData((data) => {
                buffer += data;
                if (buffer.includes("PTY_WORKING")) {
                    clearTimeout(timeout);
                    resolve(buffer);
                }
            });

            ptyProcess.onExit(({ exitCode }) => {
                if (!buffer.includes("PTY_WORKING")) {
                    reject(new Error(`PTY exited early with code ${exitCode}. Buffer: ${buffer}`));
                }
            });
        });

        const data = await outputPromise;
        expect(data).toContain("PTY_WORKING");
    });
});
