import { type Plugin } from "@opencode-ai/plugin";
import { tool, type ToolContext } from "@opencode-ai/plugin/tool";
import { spawn, type ChildProcess } from "child_process";
import { type LogEvent } from "../lib/types";
import open from "open";
import path from "path";
import fs from "fs";

export const tournamentPlugin: Plugin = async ({ client, $ }) => {
  return {
    tool: {
      tournament: tool({
        description: "Runs a Logical Induction Market tournament with a live web dashboard. ALWAYS use 'opencode' provider and 'gemini-3-flash' model to utilize available credits.",
        args: {
            prompt: tool.schema.string().describe("The coding task"),
            rounds: tool.schema.number().default(2),
            agents: tool.schema.number().default(3),
            model: tool.schema.string().default("gemini-3-flash").describe("The LLM model ID. Defaults to 'gemini-3-flash'."),
            provider: tool.schema.string().default("opencode").describe("The LLM provider ID. MUST be 'opencode' to use credits."),
            log_level: tool.schema.string().default("ERROR").describe("Logging level (DEBUG, INFO, WARNING, ERROR). Defaults to ERROR."),
            timeout: tool.schema.number().default(300.0).describe("Timeout for each agent's response in seconds. Increase for complex tasks.")
        },
        async execute({ prompt, rounds, agents, model, provider, log_level, timeout }, ctx: ToolContext) {
            // 1. Start Dashboard Server (Detached)
            const dashboardServerPath = path.join(__dirname, "../lib/dashboard-server.ts");
            const arenaDir = path.join(process.cwd(), ".arenas"); // Base arenas dir
            const dashboardLogPath = path.join(arenaDir, "dashboard.log");
            
            // Ensure arena dir exists for the log
            if (!fs.existsSync(arenaDir)) fs.mkdirSync(arenaDir, { recursive: true });

            // Spawn detached process
            const dashboardProcess = spawn("bun", [dashboardServerPath, "--log-file", dashboardLogPath], {
                detached: true,
                stdio: ["ignore", "pipe", "pipe"], // Capture stdout for port
                env: { ...process.env } // Pass environment variables
            });

            let dashboardUrl = "";
            
            // Wait for dashboard to print its URL
            await new Promise<void>((resolve, reject) => {
                let buffer = "";
                let resolved = false;

                const onData = (data: Buffer) => {
                    buffer += data.toString();
                    if (buffer.includes("\n")) {
                        const lines = buffer.split("\n");
                        for (const line of lines) {
                            try {
                                const info = JSON.parse(line);
                                if (info.url) {
                                    dashboardUrl = info.url;
                                    resolved = true;
                                    resolve();
                                    return;
                                }
                            } catch (e) {}
                        }
                    }
                };

                dashboardProcess.stdout?.on("data", onData);
                
                dashboardProcess.on("error", (err) => {
                    if (!resolved) reject(new Error(`Failed to start dashboard: ${err.message}`));
                });
                
                dashboardProcess.on("exit", (code) => {
                    if (!resolved) reject(new Error(`Dashboard exited prematurely with code ${code}`));
                });

                // Timeout after 10s
                setTimeout(() => {
                    if (!resolved) {
                        try { 
                            dashboardProcess.kill(); 
                        } catch(e) {
                            // Use log helper during plugin execution
                            log("error", `[DASHBOARD-START] Failed to kill process on timeout: ${e}`);
                        }
                        reject(new Error("Timeout waiting for dashboard URL"));
                    }
                }, 10000);
            });

            // Forward Dashboard Server stderr to OpenCode logs while plugin is alive
            dashboardProcess.stderr?.on("data", (data: Buffer) => {
                const lines = data.toString().split("\n");
                for (const line of lines) {
                    if (line.trim()) {
                        log("debug", `[DASHBOARD-SERVER] ${line.trim()}`);
                    }
                }
            });

            // Detach and unref so plugin can exit independently
            dashboardProcess.unref();

            const log = (level: "debug" | "info" | "warn" | "error", message: string) => {
                client.app.log({ body: { service: "tournament-tool", level, message } }).catch(() => {});
            };

            log("info", `[DASHBOARD] ${dashboardUrl}`);
            const msg: string = `🚀 Live tournament dashboard available at ${dashboardUrl}`;

            await client.tui.showToast({
                body: { message: `🚀 Opening live tournament dashboard at ${dashboardUrl}`, variant: "info" }
            })

            // Give user time to react to toast
            await new Promise(resolve => setTimeout(resolve, 1000));

            // Auto-open browser using 'open' library
            await open(dashboardUrl);

            // 5. Report URL via Session Prompt (Chat Backup)
            await client.session.promptAsync({
                path: { id: ctx.sessionID },
                body: {
                    parts: [{ type: "text", text: msg }],
                    noReply: true,
                },
            });

            // Yield to event loop
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
                
                const child: ChildProcess = spawn("python3", args, { env });

                let lineBuffer: string = "";
                let finalReport: string = "No report generated.";

                // Helper to send logs to dashboard
                const sendToDashboard = (endpoint: string, data: any) => {
                    fetch(`${dashboardUrl}${endpoint}`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(data)
                    }).catch((err) => {
                        // Use the structured logger to avoid corrupting the TUI
                        log("debug", `[DASHBOARD-COMM] Failed to send to ${endpoint}: ${err.message}`);
                    });
                };

                child.stdout?.on("data", (data: Buffer) => {
                    const chunk: string = data.toString();
                    lineBuffer += chunk;
                    
                    if (lineBuffer.includes('\n')) {
                        const lines: string[] = lineBuffer.split('\n');
                        lineBuffer = lines.pop() || "";
                        
                        for (const line of lines) {
                            if (!line.trim()) continue;
                            try {
                                const event: LogEvent | Record<string, unknown> = JSON.parse(line);
                                
                                if (event.type === 'final_result' && typeof event.report === 'string') {
                                    finalReport = event.report;
                                    sendToDashboard('/api/log', { type: 'log', message: 'Tournament Finished. Processing results...' });
                                } else if (event.type === 'agent_init') {
                                    // Register agent with Dashboard Server
                                    sendToDashboard('/api/agent', event);
                                    sendToDashboard('/api/log', event);
                                } else {
                                    sendToDashboard('/api/log', event);
                                }
                            } catch (e: unknown) {
                                const err = e as Error;
                                client.app.log({
                                    body: {
                                        service: "tournament-tool",
                                        level: "debug",
                                        message: `Failed to parse JSON: ${err.message}`
                                    }
                                }).catch(() => {});
                            }
                        }
                    }
                });

                child.stderr?.on("data", (data: Buffer) => {
                    const msg: string = data.toString();
                    sendToDashboard('/api/log', { type: 'log', message: `[STDERR] ${msg}` });
                });

                child.on("close", async (code: number | null) => {
                    sendToDashboard('/api/log', { 
                        type: 'log', 
                        message: 'Tournament finished. Dashboard and agent sessions remain active for exploration.' 
                    });

                    const resultMsg = code !== 0
                        ? `Market crashed (Exit Code ${code})\nDashboard remains active at ${dashboardUrl}`
                        : `${finalReport}\n\nDashboard remains active at ${dashboardUrl}`;
                    
                    // Resolve immediately so the invoking agent can apply results.
                    // The dashboard server stays alive in the background for the user
                    // to explore sessions; it self-closes when all clients disconnect.
                    resolve(resultMsg);
                });

                child.on("error", (err: Error) => {
                    resolve(`Failed to start market process: ${err.message}`);
                });
            });
          }
      })
    }
  };
};

export default tournamentPlugin;