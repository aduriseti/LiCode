// Standalone PTY helper process.
// Runs outside the Bun/opencode TUI to avoid forkpty signal conflicts.
// Spawns opencode attach via node-pty and serves terminal I/O over a websocket.
//
// Usage: node pty-helper.js <opencode-bin> <attach-url> <session-id> <cwd>
// Prints JSON { "port": <number> } to stdout on ready, then communicates via ws.

/* eslint-disable @typescript-eslint/no-require-imports */
const pty = require("node-pty");
const { WebSocketServer } = require("ws");
const http = require("http");

const [, , opencodeBin, attachUrl, sessionId, cwd] = process.argv;

const server = http.createServer();
const wss = new WebSocketServer({ server });

let terminal = null;
let outputBuffer = "";
const OUTPUT_BUFFER_MAX = 100_000;

function appendBuffer(data) {
    outputBuffer += data;
    if (outputBuffer.length > OUTPUT_BUFFER_MAX) {
        outputBuffer = outputBuffer.slice(outputBuffer.length - OUTPUT_BUFFER_MAX);
    }
}

server.listen(0, "127.0.0.1", () => {
    const port = server.address().port;
    // Signal readiness to parent
    process.stdout.write(JSON.stringify({ port }) + "\n");

    const args = ["attach", attachUrl, "-s", sessionId, "--print-logs"];
    terminal = pty.spawn(opencodeBin, args, {
        name: "xterm-256color",
        cols: 120,
        rows: 40,
        cwd: cwd || process.cwd(),
        env: { ...process.env, TERM: "xterm-256color", COLORTERM: "truecolor" },
    });

    terminal.onData((data) => {
        appendBuffer(data);
        wss.clients.forEach((client) => {
            if (client.readyState === 1) {
                client.send(JSON.stringify({ type: "data", data }));
            }
        });
    });

    terminal.onExit(({ exitCode, signal }) => {
        terminal = null;
        wss.clients.forEach((client) => {
            if (client.readyState === 1) {
                client.send(JSON.stringify({ type: "exit", exitCode, signal }));
            }
        });
    });
});

wss.on("connection", (ws) => {
    // Send buffered output to new connections
    if (outputBuffer.length > 0) {
        ws.send(JSON.stringify({ type: "buffer", data: outputBuffer }));
    }

    ws.on("message", (raw) => {
        if (!terminal) return;
        try {
            const msg = JSON.parse(raw);
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
            console.error(`[PTY-HELPER] Failed to parse message: ${e.message}`);
        }
    });
});

// Clean up if parent disconnects
process.on("disconnect", () => {
    if (terminal) {
        try {
            terminal.kill();
        } catch (_e) {
            /* ignore */
        }
    }
    process.exit(0);
});

process.on("SIGTERM", () => {
    if (terminal) {
        try {
            terminal.kill();
        } catch (_e) {
            /* ignore */
        }
    }
    process.exit(0);
});
