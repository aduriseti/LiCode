import { tool, type ToolContext, type Plugin } from "@opencode-ai/plugin"
import { spawn, type ChildProcess } from "child_process";
import { createDashboardApp } from "./dashboard.app";
import { type LogEvent } from "./types";
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
            target_file: tool.schema.string().optional().describe("Optional: Path to an existing file to refactor/fix."),
            log_level: tool.schema.string().default("ERROR").describe("Logging level (DEBUG, INFO, WARNING, ERROR). Defaults to ERROR."),
            timeout: tool.schema.number().default(300.0).describe("Timeout for each agent's response in seconds. Increase for complex tasks.")
        },
        async execute({ prompt, rounds, agents, model, provider, target_file, log_level, timeout }, ctx: ToolContext) {
            // 1. Start Dashboard Server
            const { server, io } = createDashboardApp();

            const portPromise: Promise<string> = new Promise((resolve) => {
                server.listen(0, () => {
                    const addr = server.address();
                    const port = typeof addr === 'string' ? 0 : addr?.port;
                    resolve(`http://localhost:${port}`);
                });
            });

            const dashboardUrl: string = await portPromise;
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
                
                if (target_file) {
                    args.push("--target-file", target_file);
                }

                const child: ChildProcess = spawn("python3", args, { env });

                let lineBuffer: string = "";
                let finalReport: string = "No report generated.";

                child.stdout?.on("data", (data: Buffer) => {
                    const chunk: string = data.toString();
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
                            } catch (e: unknown) {
                                // Log parsing errors for debugging
                                const err = e as Error;
                                client.app.log({
                                    body: {
                                        service: "tournament-tool",
                                        level: "debug",
                                        message: `Failed to parse JSON from subprocess: ${err.message}. Line: ${line}`
                                    }
                                }).catch(() => {});
                            }
                        }
                    }
                });

                child.stderr?.on("data", (data: Buffer) => {
                    const msg: string = data.toString();
                    io.emit('log', { type: 'log', message: `[STDERR] ${msg}` });
                });

                child.on("close", async (code: number | null) => {
                    server.close();
                    if (code !== 0) {
                        resolve(`Market crashed (Exit Code ${code})`);
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
    }
  };
};

export default tournamentPlugin;
