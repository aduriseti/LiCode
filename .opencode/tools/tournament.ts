import { tool, type ToolContext } from "@opencode-ai/plugin"
import { type OpencodeClient } from "@opencode-ai/sdk"
import { spawn, type ChildProcess } from "child_process";
import fs from "fs/promises";
import express, { type Express, type Request, type Response } from "express";
import { Server, type Socket } from "socket.io";
import http, { type Server as HttpServer } from "http";
import path from "path";
import { type LogEvent } from "./types";

// Simple Dashboard HTML
const DASHBOARD_HTML: string = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Market Tournament Dashboard</title>
    <style>
        body { background-color: #1e1e1e; color: #d4d4d4; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin: 0; padding: 20px; display: flex; flex-direction: column; height: 100vh; box-sizing: border-box; }
        h1 { margin-top: 0; color: #9cdcfe; }
        .container { display: flex; flex: 1; gap: 20px; overflow: hidden; }
        .panel { background: #252526; padding: 15px; border-radius: 8px; overflow-y: auto; flex: 1; display: flex; flex-direction: column; }
        .panel h2 { margin-top: 0; color: #ce9178; border-bottom: 1px solid #3e3e42; padding-bottom: 5px; }
        #logs { font-family: 'Consolas', 'Courier New', monospace; font-size: 14px; white-space: pre-wrap; }
        .log-entry { margin-bottom: 2px; }
        .log-info { color: #d4d4d4; }
        .log-error { color: #f48771; }
        table { width: 100%; border-collapse: collapse; margin-top: 10px; }
        th, td { text-align: left; padding: 8px; border-bottom: 1px solid #3e3e42; }
        th { color: #569cd6; }
        .bar-container { background: #3e3e42; height: 10px; border-radius: 5px; overflow: hidden; width: 100px; }
        .bar { height: 100%; background: #4ec9b0; }
        #status { font-weight: bold; color: #6a9955; margin-bottom: 10px; }
    </style>
</head>
<body>
    <h1>Logical Induction Market Dashboard</h1>
    <div id="status">Connecting...</div>
    <div class="container">
        <div class="panel" style="flex: 2;">
            <h2>Market State</h2>
            <div id="round-info">Waiting for data...</div>
            <div id="tables"></div>
        </div>
        <div class="panel" style="flex: 1;">
            <h2>Live Logs</h2>
            <div id="logs"></div>
        </div>
    </div>

    <script src="/socket.io/socket.io.js"></script>
    <script>
        const socket = io();
        const statusEl = document.getElementById('status');
        const logsEl = document.getElementById('logs');
        const roundInfoEl = document.getElementById('round-info');
        const tablesEl = document.getElementById('tables');

        socket.on('connect', () => {
            statusEl.textContent = 'Connected to Tournament Runner';
        });

        socket.on('disconnect', () => {
            statusEl.textContent = 'Disconnected';
            statusEl.style.color = '#f48771';
        });

        socket.on('log', (data) => {
            if (data.type === 'log') {
                const line = document.createElement('div');
                line.className = 'log-entry log-info';
                line.textContent = \`[\${new Date().toLocaleTimeString()}] \${data.message}\`;
                logsEl.appendChild(line);
                logsEl.scrollTop = logsEl.scrollHeight;
            } else if (data.type === 'state') {
                renderState(data);
            } else if (data.type === 'agent_init') {
                const line = document.createElement('div');
                line.className = 'log-entry log-info';
                line.textContent = \`Agent \${data.agent_id} initialized (Session: \${data.session_id})\`;
                logsEl.appendChild(line);
            }
        });

        function renderState(state) {
            roundInfoEl.textContent = \`Round: \${state.round} | Whale Wealth: \${state.whale_wealth.toFixed(2)}\`;
            
            let html = '<h3>Assets</h3><table><tr><th>ID</th><th>Price</th><th>Vis</th></tr>';
            state.assets.forEach(asset => {
                const width = Math.min(100, asset.price * 100);
                html += \`<tr><td>\${asset.id}</td><td>\${asset.price.toFixed(3)}</td><td><div class="bar-container"><div class="bar" style="width: \${width}%"></div></div></td></tr>\`;
            });
            html += '</table>';

            html += '<h3>Agents</h3><table><tr><th>ID</th><th>Wealth</th></tr>';
            state.agents.sort((a, b) => b.wealth - a.wealth).forEach(agent => {
                html += \`<tr><td>\${agent.id}</td><td>\${agent.wealth.toFixed(2)}</td></tr>\`;
            });
            html += '</table>';

            tablesEl.innerHTML = html;
        }
    </script>
</body>
</html>
`;

export default tool({
  description: "Runs a Logical Induction Market tournament with a live web dashboard. ALWAYS use 'opencode' provider and 'gemini-3-flash' model to utilize available credits.",
  args: {
    prompt: tool.schema.string().describe("The coding task"),
    rounds: tool.schema.number().default(2),
    agents: tool.schema.number().default(3),
    model: tool.schema.string().default("gemini-3-flash").describe("The LLM model ID. Defaults to 'gemini-3-flash'."),
    provider: tool.schema.string().default("opencode").describe("The LLM provider ID. MUST be 'opencode' to use credits."),
    target_file: tool.schema.string().optional().describe("Optional: Path to an existing file to refactor/fix."),
    log_level: tool.schema.string().default("ERROR").describe("Logging level (DEBUG, INFO, WARNING, ERROR). Defaults to ERROR."),
    timeout: tool.schema.number().default(300.0).describe("Timeout for each agent's response in seconds. Increase for complex tasks.")
  },
  async execute({ prompt, rounds, agents, model, provider, target_file, log_level, timeout }, ctx: ToolContext & { client: OpencodeClient }) {
    // 1. Start Dashboard Server
    const app: Express = express();
    const server: HttpServer = http.createServer(app);
    const io: Server = new Server(server);

    app.get('/', (req: Request, res: Response) => {
        res.send(DASHBOARD_HTML);
    });

    const portPromise: Promise<string> = new Promise((resolve) => {
        server.listen(0, () => {
            const addr = server.address();
            const port = typeof addr === 'string' ? 0 : addr?.port;
            resolve(`http://localhost:${port}`);
        });
    });

    const dashboardUrl: string = await portPromise;
    const msg: string = `🚀 Live tournament dashboard available at ${dashboardUrl}`;

    // 2. Report URL via Tool Metadata (Status Bar)
    ctx.metadata({ title: msg });

    // 3. Report URL via TUI Toast
    try {
        await ctx.client.tui.showToast({
            body: {
                message: msg,
                type: "info"
            }
        });
    } catch (e) {
        const err = e as Error;
        await ctx.client.app.log({
            body: {
                service: "tournament-tool",
                level: "error",
                message: `Failed to show toast: ${err.message}`
            }
        });
    }

    // 4. Report URL via Session Prompt (Chat Backup)
    if (ctx.sessionID) {
        try {
            await ctx.client.session.promptAsync({
                path: { id: ctx.sessionID },
                body: {
                    parts: [{ type: "text", text: msg }]
                }
            });
        } catch (e) {
            const err = e as Error;
            await ctx.client.app.log({
                body: {
                    service: "tournament-tool",
                    level: "error",
                    message: `Failed to send promptAsync: ${err.message}`
                }
            });
        }
    }

    // 5. Structured Logging
    await ctx.client.app.log({
        body: {
            service: "tournament-tool",
            level: "info",
            message: msg
        }
    });

    // D. Yield to event loop to ensure flushing
    await new Promise<void>((resolve) => setTimeout(resolve, 2000));

    return new Promise<string>((resolve, reject) => {
        const env: NodeJS.ProcessEnv = { 
            ...process.env, 
            OPENCODE_API_KEY: process.env.OPENCODE,
            FORCE_COLOR: '1',
            PYTHONUNBUFFERED: '1'
        };
        
        const args: string[] = [
            "-m", "market.cli",
            "--log-level", log_level,
            "run",
            "--prompt", prompt,
            "--rounds", String(rounds),
            "--agents", String(agents),
            "--model", model,
            "--provider", provider,
            "--timeout", String(timeout),
            "--json-logs" // Use JSON logs
        ];
        
        if (target_file) {
            args.push("--target-file", target_file);
        }

        const child: ChildProcess = spawn("python3", args, { env });

        let stdoutBuffer: string = "";
        let stderrBuffer: string = "";
        let lineBuffer: string = "";
        let finalReport: string = "No report generated.";

        child.stdout?.on("data", (data: Buffer) => {
            const chunk: string = data.toString();
            stdoutBuffer += chunk;
            lineBuffer += chunk;
            
            if (lineBuffer.includes('\n')) {
                const lines: string[] = lineBuffer.split('\n');
                lineBuffer = lines.pop() || "";
                
                for (const line of lines) {
                    if (!line.trim()) continue;
                    try {
                        const event: LogEvent = JSON.parse(line);
                        
                        if (event.type === 'final_result' && typeof event.report === 'string') {
                            finalReport = event.report;
                            io.emit('log', { type: 'log', message: 'Tournament Finished. Processing results...' });
                        } else {
                            // Forward everything else to dashboard
                            io.emit('log', event);
                        }
                    } catch (e) {
                        // Log parsing errors for debugging
                        const err = e as Error;
                        ctx.client.app.log({
                            body: {
                                service: "tournament-tool",
                                level: "debug",
                                message: `Failed to parse JSON from subprocess: ${err.message}. Line: ${line}`
                            }
                        }).catch(() => {}); // Ignore logging failures
                    }
                }
            }
        });

        child.stderr?.on("data", (data: Buffer) => {
            const msg: string = data.toString();
            stderrBuffer += msg;
            io.emit('log', { type: 'log', message: `[STDERR] ${msg}` });
        });

        child.on("close", async (code: number | null) => {
            server.close();
            if (code !== 0) {
                resolve(`Market crashed (Exit Code ${code}):\n${stderrBuffer}`);
                return;
            }
            resolve(finalReport);
        });

        child.on("error", (err: Error) => {
            server.close();
            resolve(`Failed to start market process: ${err.message}`);
        });
    });
  }
})