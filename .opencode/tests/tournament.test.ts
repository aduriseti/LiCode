import { describe, it, expect, vi, beforeEach } from "vitest";
import { EventEmitter } from "events";
import http from "http";

// Use vi.hoisted for variables used in vi.mock
const mocks = vi.hoisted(() => ({
  spawn: vi.fn(),
  expressGet: vi.fn(),
  serverListen: vi.fn(),
  serverClose: vi.fn(),
  serverAddress: vi.fn(),
  socketIoEmit: vi.fn(),
  socketIoOn: vi.fn(),
  promptAsync: vi.fn(),
  showToast: vi.fn(),
  appLog: vi.fn(),
  shellHelper: vi.fn().mockReturnValue({ text: vi.fn().mockResolvedValue("output") }),
  open: vi.fn().mockResolvedValue(undefined),
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
  spawn: mocks.spawn
}));

vi.mock("open", () => ({
  default: mocks.open
}));

vi.mock("express", () => {
  return {
    default: Object.assign(vi.fn(() => ({
      get: mocks.expressGet,
    })), {
      json: vi.fn(),
      static: vi.fn()
    })
  };
});

vi.mock("http", () => ({
  default: {
    createServer: vi.fn(() => ({
      listen: mocks.serverListen,
      address: mocks.serverAddress,
      close: mocks.serverClose
    }))
  }
}));

vi.mock("socket.io", () => {
  return {
    Server: function() {
      return {
        emit: mocks.socketIoEmit,
        on: mocks.socketIoOn
      };
    }
  };
});

vi.mock("../plugins/dashboard.app", () => ({
  createDashboardApp: vi.fn(() => ({
    app: { get: mocks.expressGet },
    server: {
      listen: mocks.serverListen,
      address: mocks.serverAddress,
      close: mocks.serverClose
    },
    io: {
      emit: mocks.socketIoEmit,
      on: mocks.socketIoOn
    }
  }))
}));

// Import the tool (plugin)
import { tournamentPlugin } from "../plugins/tournament";

describe("Tournament Tool", () => {
  let mockContext: any;
  let mockChildProcess: any;
  let tournamentTool: any;

  beforeEach(async () => {
    vi.clearAllMocks();

    const mockClient: any = {
        session: {
          promptAsync: mocks.promptAsync,
        },
        tui: {
          showToast: mocks.showToast
        },
        app: {
          log: mocks.appLog
        }
    };

    // 1. Initialize Plugin
    const hooks = await tournamentPlugin({
        client: mockClient,
        project: {} as any,
        directory: "/dir",
        worktree: "/wt",
        serverUrl: new URL("http://localhost"),
        $: mocks.shellHelper
    });
    
    tournamentTool = hooks.tool!.tournament;

    // Setup Mock Context
    mockContext = {
      sessionID: "test-session-123",
    };

    // Setup Mock Child Process
    mockChildProcess = Object.assign(new EventEmitter(), {
        stdout: new EventEmitter(),
        stderr: new EventEmitter()
    });
    mocks.spawn.mockReturnValue(mockChildProcess);

    // Setup Mock Server Address
    mocks.serverAddress.mockReturnValue({ port: 5001 });
    
    // Setup Mock Server Listen to call callback immediately
    mocks.serverListen.mockImplementation((port: number, cb: () => void) => {
      console.log("Mock server listening called");
      if (cb) cb();
    });
  });

  it("should start dashboard and report URL via multiple channels", async () => {
    // 1. Start the tool execution
    const executionPromise = tournamentTool.execute({
      prompt: "Test Task",
      rounds: 2,
      agents: 3,
      model: "gemini-3-flash",
      provider: "opencode",
      log_level: "INFO",
      timeout: 10
    }, mockContext);

    // 2. Wait a tick for async server startup + message delays
    await new Promise(resolve => setTimeout(resolve, 4000));

    // 3. Verify browser was opened
    expect(mocks.open).toHaveBeenCalledWith("http://localhost:5001");

    // 4. Verify URL Reporting via promptAsync (Chat Message)
    expect(mocks.promptAsync).toHaveBeenCalledWith(expect.objectContaining({
      path: { id: "test-session-123" },
      body: expect.objectContaining({
        parts: [expect.objectContaining({
          text: expect.stringContaining("http://localhost:5001")
        })]
      })
    }));

    // 5. Verify URL Reporting via showToast (TUI Overlay)
    expect(mocks.showToast).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({
        message: expect.stringContaining("http://localhost:5001"),
        variant: "info"
      })
    }));

    // 6. Verify Python Process Spawn
    expect(mocks.spawn).toHaveBeenCalledWith(
      "python3",
      expect.arrayContaining(["--prompt", "Test Task"]),
      expect.any(Object)
    );

    // 7. Simulate Python Output (JSON Logs)
    const logEvent = { type: "log", message: "Processing round 1" };
    mockChildProcess.stdout.emit("data", Buffer.from(JSON.stringify(logEvent) + "\n"));
    
    // Verify it was emitted to Socket.io
    expect(mocks.socketIoEmit).toHaveBeenCalledWith("log", logEvent);

    // 8. Simulate Final Result
    const finalReport = "Final Analysis Report";
    const resultEvent = { type: "final_result", report: finalReport };
    mockChildProcess.stdout.emit("data", Buffer.from(JSON.stringify(resultEvent) + "\n"));
    
    // 9. Simulate Process Exit
    mockChildProcess.emit("close", 0);

    // 10. Await Result
    const result = await executionPromise;
    expect(result).toBe(finalReport);

    // 11. Verify Server Cleanup
    expect(mocks.serverClose).toHaveBeenCalled();
  });

  it("should handle partial JSON chunks correctly", async () => {
    const executionPromise = tournamentTool.execute({
        prompt: "Test", rounds: 1, agents: 2, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);
    
    await new Promise(resolve => setTimeout(resolve, 4000));

    const part1 = '{"type": "log", "mess';
    const part2 = 'age": "Split JSON"}\n';

    mockChildProcess.stdout.emit("data", Buffer.from(part1));
    expect(mocks.socketIoEmit).not.toHaveBeenCalled();

    mockChildProcess.stdout.emit("data", Buffer.from(part2));
    expect(mocks.socketIoEmit).toHaveBeenCalledWith("log", { type: "log", message: "Split JSON" });

    mockChildProcess.emit("close", 0);
    await executionPromise;
  });
});