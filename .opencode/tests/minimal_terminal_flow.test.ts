import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { EventEmitter } from "events";
import { io as ClientIO, Socket as ClientSocket } from "socket.io-client";
import { type ToolContext } from "@opencode-ai/plugin/tool";

interface MockPtyInstance {
    onData: ReturnType<typeof vi.fn>;
    onExit: ReturnType<typeof vi.fn>;
    write: ReturnType<typeof vi.fn>;
    kill: ReturnType<typeof vi.fn>;
    resize: ReturnType<typeof vi.fn>;
}

const mocks = vi.hoisted(() => ({
    spawn: vi.fn(),
    ptySpawn: vi.fn().mockImplementation(() => ({
        onData: vi.fn(),
        onExit: vi.fn(),
        write: vi.fn(),
        kill: vi.fn(),
        resize: vi.fn()
    }))
}));

vi.mock("child_process", () => ({
    spawn: mocks.spawn
}));

vi.mock("node-pty", () => ({
    spawn: mocks.ptySpawn
}));

vi.mock("open", () => ({
    default: vi.fn().mockResolvedValue(undefined)
}));

describe("Minimal Terminal Flow (Real PTY)", () => {
    let clientSocket: ClientSocket;
    let mockChild: EventEmitter & { stdout: EventEmitter, stderr: EventEmitter };

    beforeEach(() => {
        vi.clearAllMocks();
        mockChild = Object.assign(new EventEmitter(), {
            stdout: new EventEmitter(),
            stderr: new EventEmitter()
        }) as unknown as EventEmitter & { stdout: EventEmitter, stderr: EventEmitter };
        mocks.spawn.mockReturnValue(mockChild);
    });

    afterEach(() => {
        if (clientSocket) clientSocket.disconnect();
    });

    it("should spawn a terminal and proxy output correctly", async () => {
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

        // DO NOT AWAIT
        const execPromise = tournamentTool.execute({
            prompt: "Test", rounds: 1, agents: 1, model: "m", provider: "p"
        }, { sessionID: "main" } as ToolContext);

        await new Promise(resolve => setTimeout(resolve, 4000));
        expect(dashboardUrl).not.toBe("");

        clientSocket = ClientIO(dashboardUrl, { transports: ["polling"] });
        await new Promise<void>(resolve => clientSocket.on("connect", resolve));

        const initEvent = {
            type: "agent_init",
            agent_id: "agent_real_pty",
            session_id: "ses_123",
            api_url: "http://127.0.0.1:9999",
            arena_dir: "/mock/arena"
        };
        mockChild.stdout.emit("data", Buffer.from(JSON.stringify(initEvent) + "\n"));

        // Give plugin time to process agent_init
        await new Promise(resolve => setTimeout(resolve, 1000));

        clientSocket.emit("terminal.init", { agent_id: "agent_real_pty" });

        // Wait for pty.spawn to be called
        await vi.waitFor(() => {
            if (mocks.ptySpawn.mock.calls.length === 0) throw new Error("pty.spawn not called yet");
        });

        const ptyInstance = mocks.ptySpawn.mock.results[0].value as MockPtyInstance;
        const ptyDataHandler = ptyInstance.onData.mock.calls[0][0] as (data: string) => void;

        const outputPromise = new Promise<string>((resolve) => {
            clientSocket.on("terminal.output", ({ agent_id, data }: { agent_id: string, data: string }) => {
                if (agent_id === "agent_real_pty") {
                    resolve(data); 
                }
            });
        });

        // Simulate PTY data
        ptyDataHandler("MINIMAL_FLOW_DATA");

        const data = await outputPromise;
        expect(data).toBe("MINIMAL_FLOW_DATA");

        mockChild.emit("close", 0);
        await execPromise;
    }, 20000);
});
