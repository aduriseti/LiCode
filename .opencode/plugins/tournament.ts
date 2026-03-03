import { type Plugin } from "@opencode-ai/plugin";
import { tool, type ToolContext } from "@opencode-ai/plugin/tool";
import { spawn, type ChildProcess } from "child_process";
import { type LogEvent } from "../lib/types";
import open from "open";

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
            const log = (level: "debug" | "info" | "warn" | "error", message: string) => {
                client.app.log({ body: { service: "tournament-tool", level, message } }).catch(() => {});
            };

            return new Promise<string>((resolve, reject) => {
                const env: NodeJS.ProcessEnv = { 
                    ...process.env, 
                    OPENCODE_API_KEY: process.env.OPENCODE,
                    FORCE_COLOR: '1',
                    PYTHONUNBUFFERED: '1'
                };
                
                const args: string[] = [
                    "-m", "market.cli",
                    "--log-level", log_level.toUpperCase(),
                    "run",
                    "--prompt", prompt,
                    "--rounds", String(rounds),
                    "--agents", String(agents),
                    "--model", model,
                    "--provider", provider,
                    "--timeout", String(timeout),
                    "--json-logs",
                    "--dashboard"
                ];
                
                const child: ChildProcess = spawn("python3", args, { env });

                let lineBuffer: string = "";
                let finalReport: string = "No report generated.";
                let dashboardUrl: string | null = null;
                let cliError: string | null = null;

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
                                
                                if (event.type === 'error') {
                                    cliError = String(event.message);
                                    log("error", `[CLI ERROR] ${cliError}`);
                                }

                                if (event.type === 'log' && typeof event.message === 'string' && event.message.startsWith('Dashboard active at ')) {
                                    dashboardUrl = event.message.replace('Dashboard active at ', '').trim();
                                    const msg = `🚀 Live tournament dashboard available at ${dashboardUrl}`;
                                    
                                    log("info", `[DASHBOARD] ${dashboardUrl}`);

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
                                }

                                if (event.type === 'final_result' && typeof event.report === 'string') {
                                    finalReport = event.report;
                                }
                            } catch (e: unknown) {
                                log("info", `[PYTHON STDOUT] ${line}`);
                            }
                        }
                    }
                });

                child.stderr?.on("data", (data: Buffer) => {
                    const msg: string = data.toString();
                    log("error", `[PYTHON STDERR] ${msg}`);
                });

                child.on("close", async (code: number | null) => {
                    let resultMsg = code !== 0
                        ? `Market crashed (Exit Code ${code})`
                        : `${finalReport}`;
                    
                    if (cliError) {
                        resultMsg = `Failed to start tournament: ${cliError}`;
                    }
                    
                    if (dashboardUrl) {
                        resultMsg += `\n\nDashboard remains active at ${dashboardUrl}`;
                    }
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
