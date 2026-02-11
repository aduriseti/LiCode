import { Server, Socket } from "socket.io";
import * as fs from "fs";
import { spawn, ChildProcess } from "child_process";

interface AgentMeta {
    api_url: string;
    session_id: string;
    arena_dir: string;
}

export class TerminalManager {
    private agentMetadata = new Map<string, AgentMeta>();
    private agentTerminals = new Map<string, ChildProcess>();
    private spawningAgents = new Set<string>();

    constructor(private io: Server) {
        this.io.on("connection", (socket: Socket) => {
            socket.on("terminal.init", ({ agent_id }: { agent_id: string }) => {
                if (this.spawningAgents.has(agent_id)) return;
                this.spawnTerminal(socket, agent_id);
            });

            socket.on("terminal.resize", () => {
                // Resize not supported in standard spawn, but we ignore to prevent crashes
            });
        });
    }

    public registerAgent(agentId: string, apiUrl: string, sessionId: string, arenaDir?: string) {
        this.agentMetadata.set(agentId, { api_url: apiUrl, session_id: sessionId, arena_dir: arenaDir || "" });
    }

    private spawnTerminal(socket: Socket, agentId: string, attempt: number = 1) {
        const meta = this.agentMetadata.get(agentId);
        if (!meta) {
            console.error(`Terminal init failed: No metadata for agent ${agentId}`);
            return;
        }

        this.spawningAgents.add(agentId);

        if (attempt === 1 && this.agentTerminals.has(agentId)) {
            const existing = this.agentTerminals.get(agentId);
            try { existing?.kill(); } catch(e) {}
            this.agentTerminals.delete(agentId);
        }

        console.log(`[TERMINAL] Spawning for ${agentId} -> ${meta.api_url} (Attempt ${attempt}/5)`);

        try {
            const opencodeBin = "/home/codespace/.opencode/bin/opencode";
            const targetUrl = meta.api_url.replace("localhost", "127.0.0.1");
            const args = ["attach", targetUrl, "-s", meta.session_id, "--print-logs"];
            const startTime = Date.now();

            // FALLBACK TO STANDARD SPAWN TO BYPASS IOCTL ISSUES
            const child = spawn(opencodeBin, args, {
                cwd: meta.arena_dir || process.cwd(),
                env: {
                    ...process.env,
                    TERM: "xterm-256color",
                    FORCE_COLOR: "1",
                    PYTHONUNBUFFERED: "1"
                }
            });

            console.log(`[TERMINAL][${agentId}] Process Spawned (PID: ${child.pid})`);

            child.stdout?.on("data", (data: Buffer) => {
                socket.emit("terminal.output", { agent_id: agentId, data: data.toString() });
            });
            child.stderr?.on("data", (data: Buffer) => {
                socket.emit("terminal.output", { agent_id: agentId, data: data.toString() });
            });

            child.on("exit", (code, signal) => {
                this.spawningAgents.delete(agentId);
                const duration = (Date.now() - startTime) / 1000;
                console.log(`[TERMINAL-EXIT][${agentId}] PID: ${child.pid}, Code: ${code}, Signal: ${signal}, Duration: ${duration.toFixed(1)}s`);
                this.agentTerminals.delete(agentId);

                if (duration < 3 && attempt < 5) {
                    console.log(`[TERMINAL] ${agentId} failed quickly, retrying in 2s...`);
                    setTimeout(() => this.spawnTerminal(socket, agentId, attempt + 1), 2000);
                }
            });

            this.agentTerminals.set(agentId, child);
        } catch (err: any) {
            this.spawningAgents.delete(agentId);
            console.error(`[PTY-ERROR][${agentId}] Failed to spawn: ${err.message}`);
        }
    }

    public close() {
        this.agentTerminals.forEach(term => {
            try { term.kill(); } catch(e) {}
        });
        this.agentTerminals.clear();
    }
}
