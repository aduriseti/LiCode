import { describe, it, expect, vi, beforeEach } from "vitest";
import { EventEmitter } from "events";
import { type ToolContext } from "@opencode-ai/plugin/tool";

// Mock globals
global.fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });

const mocks = vi.hoisted(() => ({
    spawn: vi.fn(),
    promptAsync: vi.fn(),
    showToast: vi.fn(),
    appLog: vi.fn().mockResolvedValue({}),
    shellHelper: vi.fn().mockReturnValue({ text: vi.fn().mockResolvedValue("output") }),
    open: vi.fn(),
    exec: vi.fn().mockImplementation((_cmd: string, cb: Function) => {
        if (cb) cb(null);
    }),
}));

vi.mock("@opencode-ai/plugin", () => {
    const schemaItem = () => ({
        default: schemaItem,
        describe: schemaItem,
        optional: schemaItem,
    });
    return {
        tool: Object.assign(
            vi.fn((config) => config),
            {
                schema: {
                    string: schemaItem,
                    number: schemaItem,
                },
            },
        ),
    };
});

vi.mock("child_process", () => ({
    spawn: mocks.spawn,
    exec: mocks.exec,
}));

vi.mock("open", () => ({
    default: mocks.open,
}));

// Import the tool (plugin)
import { tournamentPlugin } from "../plugins/tournament";

describe("Tournament Tool", () => {
    let mockContext: ToolContext;
    let mockTournamentProcess: EventEmitter & { stdout: EventEmitter; stderr: EventEmitter };
    let tournamentTool: {
        execute: (args: Record<string, unknown>, ctx: ToolContext) => Promise<string>;
    };

    beforeEach(async () => {
        vi.clearAllMocks();

        const mockClient = {
            session: {
                promptAsync: mocks.promptAsync,
            },
            tui: {
                showToast: mocks.showToast,
            },
            app: {
                log: mocks.appLog,
            },
        } as unknown as Parameters<typeof tournamentPlugin>[0]["client"];

        // 1. Initialize Plugin
        const hooks = await tournamentPlugin({
            client: mockClient,
            project: {} as Record<string, unknown>,
            directory: "/dir",
            worktree: "/wt",
            serverUrl: new URL("http://localhost"),
            $: mocks.shellHelper as any,
        });

        tournamentTool = hooks.tool!.tournament as any;

        // Setup Mock Context
        mockContext = {
            sessionID: "test-session-123",
        } as ToolContext;

        // Setup Mock Processes
        mockTournamentProcess = Object.assign(new EventEmitter(), {
            stdout: new EventEmitter(),
            stderr: new EventEmitter(),
        }) as any;

        // Mock spawn behavior
        mocks.spawn.mockImplementation((cmd: string, args: string[]) => {
            // Python Tournament
            if (cmd === "python3") {
                return mockTournamentProcess;
            }
            // Unknown
            return new EventEmitter();
        });
    });

    it("should spawn python with --dashboard flag", async () => {
        const executionPromise = tournamentTool.execute(
            {
                prompt: "Test Task",
                rounds: 2,
                agents: 3,
                model: "m",
                provider: "p",
                log_level: "I",
                timeout: 10,
            },
            mockContext,
        );

        expect(mocks.spawn).toHaveBeenCalledWith(
            "python3",
            expect.arrayContaining(["-m", "market.cli", "--prompt", "Test Task", "--dashboard"]),
            expect.any(Object),
        );

        mockTournamentProcess.emit("close", 0);
        await executionPromise;
    });

    it("should open dashboard URL when log is received", async () => {
        const executionPromise = tournamentTool.execute(
            {
                prompt: "Test Task",
                rounds: 2,
                agents: 3,
                model: "m",
                provider: "p",
                log_level: "I",
                timeout: 10,
            },
            mockContext,
        );

        const logEvent = { type: "log", message: "Dashboard active at http://localhost:12345" };
        mockTournamentProcess.stdout.emit("data", Buffer.from(JSON.stringify(logEvent) + "\n"));

        // Give promises time to resolve
        await new Promise((r) => setTimeout(r, 50));

        expect(mocks.open).toHaveBeenCalledWith("http://localhost:12345");
        expect(mocks.showToast).toHaveBeenCalled();
        expect(mocks.promptAsync).toHaveBeenCalled();
        expect(mocks.appLog).toHaveBeenCalledWith(
            expect.objectContaining({
                body: expect.objectContaining({
                    message: "[DASHBOARD] http://localhost:12345",
                }),
            }),
        );

        mockTournamentProcess.emit("close", 0);
        await executionPromise;
    });

    it("should return the final report in the resolved string", async () => {
        const executionPromise = tournamentTool.execute(
            {
                prompt: "Report Test",
                rounds: 1,
                agents: 1,
                model: "m",
                provider: "p",
                log_level: "E",
                timeout: 1,
            },
            mockContext,
        );

        const report = "## Tournament Complete\n**Winner:** cand_0";
        mockTournamentProcess.stdout.emit(
            "data",
            Buffer.from(JSON.stringify({ type: "final_result", report }) + "\n"),
        );

        // Also emit dashboard URL so we test it appends
        const logEvent = { type: "log", message: "Dashboard active at http://localhost:12345" };
        mockTournamentProcess.stdout.emit("data", Buffer.from(JSON.stringify(logEvent) + "\n"));

        mockTournamentProcess.emit("close", 0);

        const result = await executionPromise;
        expect(result).toContain("## Tournament Complete");
        expect(result).toContain("cand_0");
        expect(result).toContain("Dashboard remains active at http://localhost:12345");
    });

    it("should resolve immediately with error message on crash", async () => {
        const executionPromise = tournamentTool.execute(
            {
                prompt: "Crash Test",
                rounds: 1,
                agents: 1,
                model: "m",
                provider: "p",
                log_level: "E",
                timeout: 1,
            },
            mockContext,
        );

        const logEvent = { type: "log", message: "Dashboard active at http://localhost:9999" };
        mockTournamentProcess.stdout.emit("data", Buffer.from(JSON.stringify(logEvent) + "\n"));

        mockTournamentProcess.emit("close", 1);

        const result = await executionPromise;
        expect(result).toContain("Market crashed (Exit Code 1)");
        expect(result).toContain("Dashboard remains active at http://localhost:9999");
    });
});
