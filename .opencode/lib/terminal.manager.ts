import { Server, Socket } from "socket.io";
import { ChildProcess, spawn } from "child_process";
import * as path from "path";

interface AgentMeta {
    api_url: string;
    session_id: string;
    arena_dir: string;
}

interface HelperProcess {
    proc: ChildProcess;
    port: number;
}

export type LogFn = (level: "debug" | "info" | "warn" | "error", message: string) => void;

export class TerminalManager {
    private agentMetadata = new Map<string, AgentMeta>();
    private helpers = new Map<string, HelperProcess>();
    private spawningAgents = new Set<string>();
    private verbose: boolean;
    private log: LogFn;

    constructor(private io: Server, opts?: { verbose?: boolean; log?: LogFn }) {
        this.verbose = opts?.verbose ?? false;
        this.log = opts?.log ?? (() => {});
        this.io.on("connection", (socket: Socket) => {
            socket.on("terminal.init", ({ agent_id }: { agent_id: string }) => {
                if (this.helpers.has(agent_id)) {
                    socket.emit("terminal.ready", { agent_id });
                }
            });
        });
    }

    public getHelperPort(agentId: string): number | undefined {
        return this.helpers.get(agentId)?.port;
    }

    public getAgentIds(): string[] {
        return Array.from(this.helpers.keys());
    }

    public registerAgent(agentId: string, apiUrl: string, sessionId: string, arenaDir?: string) {
        this.agentMetadata.set(agentId, { api_url: apiUrl, session_id: sessionId, arena_dir: arenaDir || "" });
    }

    public spawnTerminal(agentId: string, attempt: number = 1) {
        const meta = this.agentMetadata.get(agentId);
        if (!meta) {
            this.log("error", `Terminal init failed: No metadata for agent ${agentId}`);
            return;
        }

        this.spawningAgents.add(agentId);

        if (attempt === 1 && this.helpers.has(agentId)) {
            const existing = this.helpers.get(agentId);
            try { 
                existing?.proc.kill(); 
            } catch (e) {
                this.log("warn", `[TERMINAL] Failed to kill existing helper for ${agentId}: ${e}`);
            }
            this.helpers.delete(agentId);
        }

        if (this.verbose) this.log("info", `[TERMINAL] Spawning helper for ${agentId} (Attempt ${attempt}/5)`);

        const helperPath = path.join(__dirname, "pty-helper.js");
        const opencodeBin = process.env.OPENCODE_BIN || "opencode";
        const targetUrl = meta.api_url.replace("localhost", "127.0.0.1");
        const startTime = Date.now();

        const child = spawn("node", [helperPath, opencodeBin, targetUrl, meta.session_id, meta.arena_dir || process.cwd()], {
            stdio: ["ignore", "pipe", "pipe"],
            detached: true,
            env: { ...process.env, TERM: "xterm-256color", COLORTERM: "truecolor" }
        });

        // Forward helper stderr to dashboard log
        child.stderr!.on("data", (chunk: Buffer) => {
            const msg = chunk.toString().trim();
            if (msg) this.log("debug", `[PTY-HELPER][${agentId}] ${msg}`);
        });

        let gotPort = false;
        let stdoutBuf = "";

        child.stdout!.on("data", (chunk: Buffer) => {
            if (gotPort) return;
            stdoutBuf += chunk.toString();
            const newlineIdx = stdoutBuf.indexOf("\n");
            if (newlineIdx === -1) return;

            try {
                const info = JSON.parse(stdoutBuf.substring(0, newlineIdx));
                gotPort = true;
                this.spawningAgents.delete(agentId);
                this.helpers.set(agentId, { proc: child, port: info.port });

                if (this.verbose) this.log("info", `[TERMINAL][${agentId}] Helper ready on port ${info.port}`);

                // Tell all connected dashboard clients this terminal is available
                this.io.emit("terminal.ready", { agent_id: agentId });
            } catch (e) {
                if (this.verbose) this.log("error", `[TERMINAL][${agentId}] Failed to parse helper output: ${stdoutBuf}`);
            }
        });

        child.on("exit", (code, signal) => {
            this.spawningAgents.delete(agentId);
            const duration = (Date.now() - startTime) / 1000;

            if (this.verbose) {
                this.log("info", `[TERMINAL-EXIT][${agentId}] Helper exited: code=${code}, signal=${signal}, duration=${duration.toFixed(1)}s`);
            }

            this.helpers.delete(agentId);

            if (duration < 3 && attempt < 5) {
                if (this.verbose) this.log("info", `[TERMINAL] ${agentId} helper failed quickly, retrying in 2s...`);
                setTimeout(() => this.spawnTerminal(agentId, attempt + 1), 2000);
            }
        });

        // Unref so helper doesn't prevent parent from exiting
        child.unref();
    }

    public close() {
        this.helpers.forEach((helper) => {
            try { helper.proc.kill(); } catch (e) {}
        });
        this.helpers.clear();
    }
}
