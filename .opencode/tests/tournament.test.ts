import { describe, it, expect, vi, beforeEach } from "vitest";
import { EventEmitter } from "events";
import { type ToolContext } from "@opencode-ai/plugin/tool";

interface MockEventSource {
    url: string;
    onmessage: ((event: { data: string }) => void) | null;
    onerror: ((event: unknown) => void) | null;
    close: ReturnType<typeof vi.fn>;
}

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
  appLog: vi.fn().mockResolvedValue({}),
  shellHelper: vi.fn().mockReturnValue({ text: vi.fn().mockResolvedValue("output") }),
  open: vi.fn(),
  capturedES: [] as MockEventSource[],
  MockES: vi.fn().mockImplementation(function(url: string) {
    const inst: MockEventSource = {
      url,
      onmessage: null,
      onerror: null,
      close: vi.fn(),
    };
    mocks.capturedES.push(inst);
    return inst;
  }),
  ptySpawn: vi.fn().mockImplementation(() => ({
    onData: vi.fn(),
    onExit: vi.fn(),
    write: vi.fn(),
    resize: vi.fn(),
    kill: vi.fn()
  }))
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

vi.mock("node-pty", () => ({
  spawn: mocks.ptySpawn
}));

vi.mock("eventsource", () => {
  return { 
    EventSource: mocks.MockES,
    __esModule: true
  };
});
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

vi.mock("../lib/dashboard.app", () => ({
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
  let mockContext: ToolContext;
  let mockChildProcess: EventEmitter & { stdout: EventEmitter, stderr: EventEmitter };
  let tournamentTool: { execute: (args: Record<string, unknown>, ctx: ToolContext) => Promise<string> };

  beforeEach(async () => {
    vi.clearAllMocks();
    mocks.capturedES.length = 0;

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

    // Setup Mock Child Process
    mockChildProcess = Object.assign(new EventEmitter(), {
        stdout: new EventEmitter(),
        stderr: new EventEmitter()
    }) as any;
    mocks.spawn.mockReturnValue(mockChildProcess);

    // Setup Mock Server Address
    mocks.serverAddress.mockReturnValue({ port: 8001 });
    
    // Setup Mock Server Listen to call callback immediately
    mocks.serverListen.mockImplementation((port: number, cb: () => void) => {
      if (cb) cb();
    });
  });

  it("should start dashboard and report URL via multiple channels", async () => {
    const executionPromise = tournamentTool.execute({
      prompt: "Test Task", rounds: 2, agents: 3, model: "m", provider: "p", log_level: "I", timeout: 10
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 4000));
    expect(mocks.open).toHaveBeenCalledWith("http://localhost:8001");
    expect(mocks.promptAsync).toHaveBeenCalled();
    expect(mocks.showToast).toHaveBeenCalled();
    expect(mocks.spawn).toHaveBeenCalled();

    const logEvent = { type: "log", message: "Processing round 1" };
    mockChildProcess.stdout.emit("data", Buffer.from(JSON.stringify(logEvent) + "\n"));
    expect(mocks.socketIoEmit).toHaveBeenCalledWith("log", logEvent);

    const resultEvent = { type: "final_result", report: "Done" };
    mockChildProcess.stdout.emit("data", Buffer.from(JSON.stringify(resultEvent) + "\n"));
    mockChildProcess.emit("close", 0);
    await executionPromise;
  });

  it("should proxy live agent streams from OpenCode SSE to dashboard", async () => {
    tournamentTool.execute({
      prompt: "Streaming Test", rounds: 1, agents: 1, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 4000));

    const mockApiUrl = "http://localhost:9999";
    const initEvent = {
      type: "agent_init",
      agent_id: "agent_0",
      session_id: "ses_123",
      api_url: mockApiUrl
    };
    mockChildProcess.stdout.emit("data", Buffer.from(JSON.stringify(initEvent) + "\n"));

    await new Promise(resolve => setTimeout(resolve, 500));

    const esInstance = mocks.capturedES.find(es => es.url === `${mockApiUrl}/event`);
    expect(esInstance).toBeDefined();

    const sseEvent = {
        type: 'message.part.updated',
        properties: {
            delta: "Hello",
            part: { sessionID: "ses_123" }
        }
    };
    
    if (esInstance && esInstance.onmessage) {
        esInstance.onmessage({ data: JSON.stringify(sseEvent) });
    }

    expect(mocks.socketIoEmit).toHaveBeenCalledWith("log", expect.objectContaining({
        type: "agent_stream",
        agent_id: "agent_0",
        text: "Hello"
    }));

    mockChildProcess.emit("close", 0);
  });

  it("should handle interactive terminal sessions via socket.io and node-pty", async () => {
    // 1. Setup
    const executionPromise = tournamentTool.execute({
      prompt: "Terminal Test", rounds: 1, agents: 1, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 4000));

    // Get the socket connection handler
    const connectionHandler = mocks.socketIoOn.mock.calls.find((c: unknown[]) => (c as string[])[0] === 'connection')![1];
    const mockSocket = {
        on: vi.fn(),
        emit: vi.fn()
    };
    connectionHandler(mockSocket);

    // 2. Initialize Agent Data
    const initEvent = {
      type: "agent_init",
      agent_id: "agent_0",
      session_id: "ses_123",
      api_url: "http://localhost:9999"
    };
    mockChildProcess.stdout.emit("data", Buffer.from(JSON.stringify(initEvent) + "\n"));

    // 3. Request Terminal
    const terminalInitHandler = mockSocket.on.mock.calls.find((c: unknown[]) => (c as string[])[0] === 'terminal.init')![1];
    terminalInitHandler({ agent_id: "agent_0" });

    // Verify pty.spawn was called with direct binary execution
    expect(mocks.ptySpawn).toHaveBeenCalledWith(
        "/home/codespace/.opencode/bin/opencode", 
        ["attach", "http://localhost:9999", "-s", "ses_123", "--print-logs"], 
        expect.any(Object)
    );

    const ptyInstance = mocks.ptySpawn.mock.results[0].value;
    const ptyDataHandler = ptyInstance.onData.mock.calls[0][0];

    // 4. Verify Output Proxying
    ptyDataHandler("Hello Terminal");
    expect(mockSocket.emit).toHaveBeenCalledWith("terminal.output", { agent_id: "agent_0", data: "Hello Terminal" });

    mockChildProcess.emit("close", 0);
    await executionPromise;
  });

  it("should handle partial JSON chunks correctly", async () => {
    const executionPromise = tournamentTool.execute({
        prompt: "Test", rounds: 1, agents: 2, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);
    
    await new Promise(resolve => setTimeout(resolve, 4000));

    const part1 = '{"type": "log", "mess';
    const part2 = 'age": "Split JSON"}\n';

    mockChildProcess.stdout.emit("data", Buffer.from(part1));
    mockChildProcess.stdout.emit("data", Buffer.from(part2));
    expect(mocks.socketIoEmit).toHaveBeenCalledWith("log", { type: "log", message: "Split JSON" });

    mockChildProcess.emit("close", 0);
    await executionPromise;
  });
});
