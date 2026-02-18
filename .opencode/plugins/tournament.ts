import { type Plugin } from "@opencode-ai/plugin";
import { tool, type ToolContext } from "@opencode-ai/plugin/tool";
import { spawn, type ChildProcess } from "child_process";
import { type LogEvent } from "../lib/types";
import open from "open";
import path from "path";
import { createServer, Socket } from "net";

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
            log_level: tool.schema.string().default("INFO").describe("Logging level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO."),
            timeout: tool.schema.number().default(300.0).describe("Timeout for each agent's response in seconds. Increase for complex tasks.")
        },
        async execute({ prompt, rounds, agents, model, provider, log_level, timeout }, ctx: ToolContext) {
            // Helper to find a free port
            const getFreePort = (): Promise<number> => new Promise((resolve, reject) => {
                const srv = createServer();
                srv.listen(0, () => {
                    const port = (srv.address() as any).port;
                    srv.close(() => resolve(port));
                });
                srv.on('error', reject);
            });

            const port = await getFreePort();
            const dashboardUrl = `http://localhost:${port}`;

            // 1. Start Dashboard Server (Detached) - Phase 1 & 4
            const dashboardServerPath = path.join(__dirname, "../lib/dashboard-server.ts");
            const arenaDir = path.join(process.cwd(), ".arenas"); // Base arenas dir
            const dashboardLogPath = path.join(arenaDir, "dashboard.log");
            
            // Spawn detached process immediately
            const dashboardProcess = spawn("bun", [dashboardServerPath], {
                detached: true,
                stdio: ["ignore", "pipe", "pipe"],
                env: { ...process.env, DASHBOARD_PORT: String(port) }
            });

            // Unref immediately so plugin can exit independently
            dashboardProcess.unref();

            // Phase 4: Wait for dashboard to be ready (listening)
            await new Promise<void>((resolve, reject) => {
                const start = Date.now();
                const check = () => {
                    const socket = new Socket();
                    socket.setTimeout(1000);
                    socket.on('connect', () => {
                        socket.destroy();
                        resolve();
                    });
                    socket.on('error', () => {
                        socket.destroy();
                        if (Date.now() - start > 5000) {
                            reject(new Error("Dashboard failed to start in 5s"));
                        } else {
                            setTimeout(check, 100);
                        }
                    });
                    socket.on('timeout', () => {
                        socket.destroy();
                        check();
                    });
                    socket.connect(port, '127.0.0.1');
                };
                check();
            });

            const log = (level: "debug" | "info" | "warn" | "error", message: string) => {
                client.app.log({ body: { service: "tournament-tool", level, message } }).catch(() => {});
            };

            log("info", `[DASHBOARD] ${dashboardUrl}`);
            const msg: string = `🚀 Live tournament dashboard available at ${dashboardUrl}`;

            // Phase 1: Parallel UI Dispatch without blocking
            Promise.all([
                client.tui.showToast({
                    body: { message: `🚀 Opening live tournament dashboard at ${dashboardUrl}`, variant: "info" }
                }),
                open(dashboardUrl),
                client.session.promptAsync({
                    path: { id: ctx.sessionID },
                    body: {
                        parts: [{ type: "text", text: msg }],
                        noReply: true,
                    },
                })
            ]).catch(err => log("debug", `UI Notification failed: ${err.message}`));

            // Phase 1: Start tournament IMMEDIATELY
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
                    "--json-logs"
                ];
                
                const child: ChildProcess = spawn("python3", args, { env });

                let lineBuffer: string = "";
                let finalReport: string = "No report generated.";

                // Phase 2: Log Batching Logic
                const logQueue: any[] = [];
                let flushTimer: NodeJS.Timeout | null = null;
                
                const flushLogs = () => {
                    if (logQueue.length === 0) return;
                    const batch = [...logQueue];
                    logQueue.length = 0;
                    flushTimer = null;

                    fetch(`${dashboardUrl}/api/log`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ type: 'batch', events: batch })
                    }).catch(() => {});
                };

                const queueLog = (data: any) => {
                    logQueue.push(data);
                    if (logQueue.length >= 50) {
                        if (flushTimer) clearTimeout(flushTimer);
                        flushLogs();
                    } else if (!flushTimer) {
                        flushTimer = setTimeout(flushLogs, 100);
                    }
                };

                const sendToDashboard = (endpoint: string, data: any) => {
                    if (endpoint === '/api/log') {
                        queueLog(data);
                    } else {
                        // Registration events are sent immediately
                        fetch(`${dashboardUrl}${endpoint}`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(data)
                        }).catch(() => {});
                    }
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
                    // Flush any remaining logs
                    if (flushTimer) clearTimeout(flushTimer);
                    flushLogs();

                    sendToDashboard('/api/log', { 
                        type: 'log', 
                        message: 'Tournament finished. Dashboard and agent sessions remain active for exploration.' 
                    });

                    const resultMsg = code !== 0
                        ? `Market crashed (Exit Code ${code})\nDashboard remains active at ${dashboardUrl}`
                        : `${finalReport}\n\nDashboard remains active at ${dashboardUrl}`;
                    
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
