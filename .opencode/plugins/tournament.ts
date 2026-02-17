import { type Plugin } from "@opencode-ai/plugin";
import { tool, type ToolContext } from "@opencode-ai/plugin/tool";
import { spawn, type ChildProcess } from "child_process";
import { createDashboardApp } from "../lib/dashboard.app";
import { type LogEvent } from "../lib/types";
import open from "open";
import { EventSource } from "eventsource";
import { TerminalManager } from "../lib/terminal.manager";

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
            // 1. Start Dashboard Server
            const { server, io, setupTerminalProxy } = createDashboardApp();

            // Track active sessions for streaming
            const sessionToAgent = new Map<string, string>();
            const activeStreams = new Map<string, EventSource>();
            
            // Terminal Manager
            const terminalManager = new TerminalManager(io, { verbose: true });
            setupTerminalProxy(terminalManager);
            
            // Cleanup handler for when dashboard closes
            let dashboardClosed = false;
            const cleanup = () => {
                if (dashboardClosed) return;
                dashboardClosed = true;
                console.log("Dashboard closed, cleaning up resources...");
                activeStreams.forEach(es => es.close());
                terminalManager.close();
                server.close();
            };
            
            server.on('close', cleanup);
            io.on('connection', (socket) => {
                socket.on('disconnect', () => {
                    // If all clients disconnect, cleanup after a delay
                    setTimeout(() => {
                        if (io.engine.clientsCount === 0) {
                            cleanup();
                        }
                    }, 5000);
                });
            });

            const portPromise: Promise<string> = new Promise((resolve) => {
                server.listen(0, () => {
                    const addr = server.address();
                    const port = typeof addr === 'string' ? 0 : addr?.port;
                    resolve(`http://localhost:${port}`);
                });
            });

            const dashboardUrl: string = await portPromise;
            console.log(`[DASHBOARD] ${dashboardUrl}`);
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
                                    io.emit('log', { type: 'log', message: 'Tournament Finished. Processing results...' });
                                } else if (event.type === 'agent_init') {
                                    const { api_url, session_id, agent_id, arena_dir } = event as LogEvent;
                                    sessionToAgent.set(session_id!, agent_id!);
                                    
                                    // Register with Terminal Manager using the AGENT'S PRIVATE URL
                                    terminalManager.registerAgent(agent_id!, api_url!, session_id!, arena_dir);
                                    
                                    // Spawn terminal immediately - output is broadcast via io.emit
                                    // and buffered so late-connecting dashboards get replay
                                    terminalManager.spawnTerminal(agent_id!);
                                    
                                    if (api_url && !activeStreams.has(api_url)) {
                                        const es = new EventSource(`${api_url}/event`); // OpenCode server events endpoint is /event
                                        es.onmessage = (msg: MessageEvent) => {
                                            try {
                                                const evt = JSON.parse(msg.data);
                                                if (evt.type === 'message.part.updated') {
                                                    const part = evt.properties?.part;
                                                    const delta = evt.properties?.delta;
                                                    
                                                    if (part && part.sessionID && delta) {
                                                        const aid = sessionToAgent.get(part.sessionID);
                                                        if (aid) {
                                                            io.emit('log', {
                                                                type: 'agent_stream',
                                                                agent_id: aid,
                                                                text: delta,
                                                                timestamp: new Date().toLocaleTimeString()
                                                            });
                                                        }
                                                    }
                                                }
                                            } catch (e) {}
                                        };
                                        activeStreams.set(api_url, es);
                                    }
                                    io.emit('log', event);
                                } else {
                                    io.emit('log', event);
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
                    io.emit('log', { type: 'log', message: `[STDERR] ${msg}` });
                });

                child.on("close", async (code: number | null) => {
                    activeStreams.forEach(es => es.close());
                    
                    io.emit('log', { 
                        type: 'log', 
                        message: 'Tournament finished. Dashboard and agent sessions remain active for exploration.' 
                    });

                    const resultMsg = code !== 0
                        ? `Market crashed (Exit Code ${code})\nDashboard remains active at ${dashboardUrl}`
                        : `${finalReport}\n\nDashboard remains active at ${dashboardUrl}`;
                    
                    // Keep the promise pending so opencode stays alive.
                    // Resolve only when the dashboard server closes
                    // (all browser clients disconnect or explicit shutdown).
                    server.on('close', () => resolve(resultMsg));
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
