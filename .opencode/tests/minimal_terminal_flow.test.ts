import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { EventEmitter } from "events";
import { io as ClientIO, Socket as ClientSocket } from "socket.io-client";
import { type ToolContext } from "@opencode-ai/plugin/tool";

const mocks = vi.hoisted(() => ({
    spawn: vi.fn()
}));

vi.mock("child_process", () => ({
    spawn: mocks.spawn
}));

vi.mock("open", () => ({
    default: vi.fn().mockResolvedValue(undefined)
}));

describe("Minimal Terminal Flow (Helper Process)", () => {
    let clientSocket: ClientSocket;
    let mockChild: EventEmitter & { stdout: EventEmitter, stderr: EventEmitter };

    beforeEach(() => {
        vi.clearAllMocks();
        mockChild = Object.assign(new EventEmitter(), {
            stdout: new EventEmitter(),
            stderr: new EventEmitter()
        }) as unknown as EventEmitter & { stdout: EventEmitter, stderr: EventEmitter };

        mocks.spawn.mockImplementation((cmd: string, args: string[]) => {
            if (cmd === "node" && args[0]?.includes("pty-helper")) {
                const helperProc = Object.assign(new EventEmitter(), {
                    stdout: new EventEmitter(),
                    stderr: new EventEmitter(),
                    kill: vi.fn(),
                    unref: vi.fn(),
                    pid: 9999
                });
                setTimeout(() => {
                    helperProc.stdout.emit("data", Buffer.from('{"port":54321}\n'));
                }, 10);
                return helperProc;
            }
            return mockChild;
        });
    });

    afterEach(() => {
        if (clientSocket) clientSocket.disconnect();
    });

    it("should spawn a helper process and emit terminal.ready with port", async () => {
        const { tournamentPlugin } = await import("../plugins/tournament");
        const mockClient = {
            tui: { showToast: vi.fn() },
            session: { promptAsync: vi.fn() },
            app: { log: vi.fn().mockResolvedValue({}) }
        } as unknown as Parameters<typeof tournamentPlugin>[0]["client"];

        const hooks = await tournamentPlugin({
            client: mockClient,
            project: {} as Record<string, unknown>,
            directory: "/dir",
            worktree: "/wt",
            serverUrl: new URL("http://localhost"),
            $: vi.fn() as unknown as Parameters<typeof tournamentPlugin>[0]["$"]
        });

        const tournamentTool = hooks.tool!.tournament;

        let dashboardUrl = "";
        vi.spyOn(mockClient.tui, "showToast").mockImplementation(async (call: { body: { message: string } }) => {
            const match = call.body.message.match(/http:\/\/(localhost|127\.0\.0\.1):\d+/);
            if (match) dashboardUrl = match[0];
        });

        const execPromise = tournamentTool.execute({
            prompt: "Test", rounds: 1, agents: 1, model: "m", provider: "p"
        }, { sessionID: "main" } as ToolContext);

        await new Promise(resolve => setTimeout(resolve, 4000));
        expect(dashboardUrl).not.toBe("");

        clientSocket = ClientIO(dashboardUrl, { transports: ["polling"] });
        await new Promise<void>(resolve => clientSocket.on("connect", resolve));

        // Listen for terminal.ready event
        const readyPromise = new Promise<{ agent_id: string }>((resolve) => {
            clientSocket.on("terminal.ready", resolve);
        });

        const initEvent = {
            type: "agent_init",
            agent_id: "agent_real_pty",
            session_id: "ses_123",
            api_url: "http://127.0.0.1:9999",
            arena_dir: "/mock/arena"
        };
        mockChild.stdout.emit("data", Buffer.from(JSON.stringify(initEvent) + "\n"));

        const ready = await readyPromise;
        expect(ready.agent_id).toBe("agent_real_pty");

        // Verify helper was spawned with correct args
        const helperCall = mocks.spawn.mock.calls.find(
            (c: string[]) => c[0] === "node" && c[1]?.[0]?.includes("pty-helper")
        );
        expect(helperCall).toBeDefined();

        mockChild.emit("close", 0);
        // Disconnect the socket client so dashboard server shuts down
        clientSocket.disconnect();
        await new Promise(resolve => setTimeout(resolve, 6000));
        await execPromise;
    }, 30000);
});
