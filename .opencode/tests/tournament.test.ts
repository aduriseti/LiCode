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
  exec: vi.fn().mockImplementation((_cmd: string, cb: Function) => { if (cb) cb(null); }),
}));

vi.mock("@opencode-ai/plugin", () => {
  const schemaItem = () => ({
    default: schemaItem,
    describe: schemaItem,
    optional: schemaItem,
  });
  return {
    tool: Object.assign(vi.fn((config) => config), {
      schema: {
        string: schemaItem,
        number: schemaItem,
      }
    })
  };
});

vi.mock("child_process", () => ({
  spawn: mocks.spawn,
  exec: mocks.exec
}));

vi.mock("open", () => ({
  default: mocks.open
}));

vi.mock("net", async () => {
  const { EventEmitter } = await import("events");
  class MockSocket extends EventEmitter {
    connect(port: number, host: string, cb?: () => void) {
        if (cb) cb();
        process.nextTick(() => this.emit('connect'));
        return this;
    }
    setTimeout = vi.fn().mockReturnThis();
    destroy = vi.fn().mockReturnThis();
  }

  return {
    createServer: vi.fn(() => ({
      listen: vi.fn((port, cb) => cb && cb()),
      address: vi.fn(() => ({ port: 8001 })),
      close: vi.fn((cb) => cb && cb()),
      on: vi.fn()
    })),
    Socket: MockSocket
  };
});

// Import the tool (plugin)
import { tournamentPlugin } from "../plugins/tournament";

describe("Tournament Tool", () => {
  let mockContext: ToolContext;
  let mockTournamentProcess: EventEmitter & { stdout: EventEmitter, stderr: EventEmitter };
  let mockDashboardProcess: EventEmitter & { stdout: EventEmitter, stderr: EventEmitter, unref: Function, kill: Function };
  let tournamentTool: { execute: (args: Record<string, unknown>, ctx: ToolContext) => Promise<string> };

  beforeEach(async () => {
    vi.clearAllMocks();

    const mockClient = {
        session: {
          promptAsync: mocks.promptAsync,
        },
        tui: {
          showToast: mocks.showToast
        },
        app: {
          log: mocks.appLog
        }
    } as unknown as Parameters<typeof tournamentPlugin>[0]["client"];

    // 1. Initialize Plugin
    const hooks = await tournamentPlugin({
        client: mockClient,
        project: {} as Record<string, unknown>,
        directory: "/dir",
        worktree: "/wt",
        serverUrl: new URL("http://localhost"),
        $: mocks.shellHelper as any
    });
    
    tournamentTool = hooks.tool!.tournament as any;

    // Setup Mock Context
    mockContext = {
      sessionID: "test-session-123",
    } as ToolContext;

    // Setup Mock Processes
    mockTournamentProcess = Object.assign(new EventEmitter(), {
        stdout: new EventEmitter(),
        stderr: new EventEmitter()
    }) as any;

    mockDashboardProcess = Object.assign(new EventEmitter(), {
        stdout: new EventEmitter(),
        stderr: new EventEmitter(),
        unref: vi.fn(),
        kill: vi.fn(),
        pid: 8888
    }) as any;

    // Mock spawn behavior
    mocks.spawn.mockImplementation((cmd: string, args: string[]) => {
        // Dashboard Server
        if (cmd === "bun" && args && args[0] && args[0].includes("dashboard-server.ts")) {
            return mockDashboardProcess;
        }
        // Python Tournament
        if (cmd === "python3") {
            return mockTournamentProcess;
        }
        // Unknown
        return new EventEmitter();
    });
  });

  it("should start dashboard and report URL", async () => {
    const executionPromise = tournamentTool.execute({
      prompt: "Test Task", rounds: 2, agents: 3, model: "m", provider: "p", log_level: "I", timeout: 10
    }, mockContext);

    // Startup is now immediate after readiness check
    await new Promise(resolve => setTimeout(resolve, 100));

    expect(mocks.spawn).toHaveBeenCalledWith("bun", expect.arrayContaining([expect.stringContaining("dashboard-server.ts")]), expect.objectContaining({
        env: expect.objectContaining({ DASHBOARD_PORT: expect.any(String) })
    }));
    expect(mockDashboardProcess.unref).toHaveBeenCalled();
    expect(mocks.open).toHaveBeenCalledWith(expect.stringContaining("http://localhost:"));
    expect(mocks.promptAsync).toHaveBeenCalled();

    // Emit log from tournament
    const logEvent = { type: "log", message: "Processing round 1" };
    mockTournamentProcess.stdout.emit("data", Buffer.from(JSON.stringify(logEvent) + "\n"));
    
    // Wait for batch flush timer (100ms)
    await new Promise(resolve => setTimeout(resolve, 200));

    // Verify fetch call to dashboard uses batch endpoint
    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/api/log"), expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ type: 'batch', events: [logEvent] })
    }));

    // Finish
    mockTournamentProcess.emit("close", 0);
    await executionPromise;
  });

  it("should register agents via HTTP when agent_init occurs", async () => {
    tournamentTool.execute({
      prompt: "Agent Test", rounds: 1, agents: 1, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 100));

    const initEvent = {
      type: "agent_init",
      agent_id: "agent_0",
      session_id: "ses_123",
      api_url: "http://localhost:9999"
    };
    mockTournamentProcess.stdout.emit("data", Buffer.from(JSON.stringify(initEvent) + "\n"));

    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/api/agent"), expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(initEvent)
    }));
    
    mockTournamentProcess.emit("close", 0);
  });

  it("should handle partial JSON chunks correctly", async () => {
    const executionPromise = tournamentTool.execute({
        prompt: "Test", rounds: 1, agents: 2, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);
    
    await new Promise(resolve => setTimeout(resolve, 100));

    const part1 = '{"type": "log", "mess';
    const part2 = 'age": "Split JSON"}\n';

    mockTournamentProcess.stdout.emit("data", Buffer.from(part1));
    mockTournamentProcess.stdout.emit("data", Buffer.from(part2));
    
    // Wait for batch flush
    await new Promise(resolve => setTimeout(resolve, 200));

    expect(global.fetch).toHaveBeenCalledWith(expect.stringContaining("/api/log"), expect.objectContaining({
        body: JSON.stringify({ type: "batch", events: [{ type: "log", message: "Split JSON" }] })
    }));

    mockTournamentProcess.emit("close", 0);
    await executionPromise;
  });

  it("should resolve immediately when tournament ends while dashboard stays alive", async () => {
    const executionPromise = tournamentTool.execute({
      prompt: "Linger Test", rounds: 1, agents: 1, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 100));

    // Tournament finishes
    mockTournamentProcess.emit("close", 0);

    const result = await executionPromise;
    expect(result).toContain("Dashboard remains active");
  });

  it("should return the final report in the resolved string", async () => {
    const executionPromise = tournamentTool.execute({
      prompt: "Report Test", rounds: 1, agents: 1, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 100));

    const report = "## Tournament Complete\n**Winner:** cand_0";
    mockTournamentProcess.stdout.emit("data", Buffer.from(JSON.stringify({ type: "final_result", report }) + "\n"));
    mockTournamentProcess.emit("close", 0);

    const result = await executionPromise;
    expect(result).toContain("## Tournament Complete");
    expect(result).toContain("cand_0");
    expect(result).toContain("Dashboard remains active");
  });

  it("should not close the dashboard server when resolving", async () => {
    const executionPromise = tournamentTool.execute({
      prompt: "Server Alive Test", rounds: 1, agents: 1, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 100));

    mockTournamentProcess.emit("close", 0);
    await executionPromise;

    // Verify dashboard process was NOT killed
    expect(mockDashboardProcess.kill).not.toHaveBeenCalled();
  });

  it("should resolve immediately with error message on crash", async () => {
    const executionPromise = tournamentTool.execute({
      prompt: "Crash Test", rounds: 1, agents: 1, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 100));

    mockTournamentProcess.emit("close", 1);

    const result = await executionPromise;
    expect(result).toContain("Market crashed (Exit Code 1)");
    expect(result).toContain("Dashboard remains active");
    // Verify dashboard process was NOT killed even on crash
    expect(mockDashboardProcess.kill).not.toHaveBeenCalled();
  });
});