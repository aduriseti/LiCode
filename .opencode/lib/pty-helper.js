"use strict";

const { spawn } = require("node-pty");
const os = require("os");
const _path = require("path");

const args = process.argv.slice(2);
const shell = os.platform() === "win32" ? "powershell.exe" : "bash";

const terminal = spawn(shell, args, {
    name: "xterm-color",
    cols: 80,
    rows: 24,
    cwd: process.cwd(),
    env: process.env,
});

terminal.onData((data) => {
    process.send({ type: "data", data });
});

terminal.onExit(({ exitCode, signal }) => {
    process.send({ type: "exit", exitCode, signal });
    process.exit(exitCode);
});

process.on("message", (raw) => {
    // Process messages as a batch if it is an array
    const messages = Array.isArray(raw) ? raw : [raw];

    messages.forEach((msgOrRaw) => {
        try {
            const msg = typeof msgOrRaw === "string" ? JSON.parse(msgOrRaw) : msgOrRaw;
            if (msg.type === "input") {
                terminal.write(msg.data);
            } else if (msg.type === "resize" && msg.cols > 0 && msg.rows > 0) {
                try {
                    terminal.resize(msg.cols, msg.rows);
                } catch (e) {
                    console.error(`[PTY-HELPER] Terminal resize failed: ${e.message}`);
                }
            }
        } catch (e) {
            console.error(`[PTY-HELPER] Failed to process message: ${e.message}`);
        }
    });
});

// Clean up if parent disconnects
process.on("disconnect", () => {
    if (terminal) {
        try {
            terminal.kill();
        } catch {
            /* ignore */
        }
    }
    process.exit(0);
});

process.on("SIGTERM", () => {
    if (terminal) {
        try {
            terminal.kill();
        } catch {
            /* ignore */
        }
    }
    process.exit(0);
});
