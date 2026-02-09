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
  ctxMetadata: vi.fn(),
  promptAsync: vi.fn(),
  showToast: vi.fn(),
  appLog: vi.fn(),
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

// Import the tool AFTER mocks are defined
import tournamentTool from "../tools/tournament";

// Import types
import { type ToolContext } from "@opencode-ai/plugin";
import { type OpencodeClient } from "@opencode-ai/sdk";

// Define Mock Context Interface
interface MockContext {
  sessionID: string;
  metadata: ReturnType<typeof vi.fn>;
  client: {
    session: {
      promptAsync: ReturnType<typeof vi.fn>;
    };
    tui: {
      showToast: ReturnType<typeof vi.fn>;
    };
    app: {
      log: ReturnType<typeof vi.fn>;
    };
  };
}

describe("Tournament Tool", () => {
  let mockContext: MockContext;
  let mockChildProcess: EventEmitter & { stdout: EventEmitter; stderr: EventEmitter };

  beforeEach(() => {
    vi.clearAllMocks();

    // Setup Mock Context
    mockContext = {
      sessionID: "test-session-123",
      metadata: mocks.ctxMetadata,
      client: {
        session: {
          promptAsync: mocks.promptAsync,
        },
        tui: {
          showToast: mocks.showToast
        },
        app: {
          log: mocks.appLog
        }
      }
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
      if (cb) cb();
    });
  });

  it("should start dashboard and report URL via multiple durable channels", async () => {
    // 1. Start the tool execution
    // Cast mockContext to the expected type for execution
    const executionPromise = tournamentTool.execute({
      prompt: "Test Task",
      rounds: 2,
      agents: 3,
      model: "gemini-3-flash",
      provider: "opencode",
      log_level: "INFO",
      timeout: 10
    }, mockContext as unknown as ToolContext & { client: OpencodeClient });

    // 2. Wait a tick for async server startup + message delays
    await new Promise(resolve => setTimeout(resolve, 2500));

    // 3. Verify URL Reporting via ctx.metadata (Status Bar)
    expect(mocks.ctxMetadata).toHaveBeenCalledWith({
      title: expect.stringContaining("http://localhost:5001")
    });

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
        type: "info"
      })
    }));

    // 6. Verify Structured Logging via app.log
    expect(mocks.appLog).toHaveBeenCalledWith(expect.objectContaining({
      body: expect.objectContaining({
        service: "tournament-tool",
        level: "info",
        message: expect.stringContaining("http://localhost:5001")
      })
    }));

    // 7. Verify Python Process Spawn
    expect(mocks.spawn).toHaveBeenCalledWith(
      "python3",
      expect.arrayContaining(["--prompt", "Test Task"]),
      expect.any(Object)
    );

    // 8. Simulate Python Output (JSON Logs)
    const logEvent = { type: "log", message: "Processing round 1" };
    mockChildProcess.stdout.emit("data", Buffer.from(JSON.stringify(logEvent) + "\n"));
    
    // Verify it was emitted to Socket.io
    expect(mocks.socketIoEmit).toHaveBeenCalledWith("log", logEvent);

    // 9. Simulate Final Result
    const finalReport = "Final Analysis Report";
    const resultEvent = { type: "final_result", report: finalReport };
    mockChildProcess.stdout.emit("data", Buffer.from(JSON.stringify(resultEvent) + "\n"));
    
    // 10. Simulate Process Exit
    mockChildProcess.emit("close", 0);

    // 11. Await Result
    const result = await executionPromise;
    expect(result).toBe(finalReport);

    // 12. Verify Server Cleanup
    expect(mocks.serverClose).toHaveBeenCalled();
  });

  it("should handle partial JSON chunks correctly", async () => {
    const executionPromise = tournamentTool.execute({
        prompt: "Test", rounds: 1, agents: 2, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext as unknown as ToolContext & { client: OpencodeClient });
    
    await new Promise(resolve => setTimeout(resolve, 2500));

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
