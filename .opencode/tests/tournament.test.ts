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
  _unused: null
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

// Stores the latest mock server so tests can trigger server.close()
let mockServer: any = null;

vi.mock("../lib/dashboard.app", () => ({
  createDashboardApp: vi.fn(() => {
    const serverListeners = new Map<string, Function[]>();
    const socketListeners: Array<{ disconnect: Function }> = [];
    mockServer = {
      listen: mocks.serverListen,
      address: mocks.serverAddress,
      close: (...args: any[]) => {
        mocks.serverClose(...args);
        (serverListeners.get('close') || []).forEach(fn => fn());
      },
      on: (event: string, fn: Function) => {
        if (!serverListeners.has(event)) serverListeners.set(event, []);
        serverListeners.get(event)!.push(fn);
      }
    };
    return {
      app: { get: mocks.expressGet },
      server: mockServer,
      io: {
        emit: mocks.socketIoEmit,
        on: (event: string, fn: Function) => {
          mocks.socketIoOn(event, fn);
          if (event === 'connection') {
            // Store the connection handler so we can simulate socket disconnect
            socketListeners.push({ disconnect: fn });
          }
        },
        engine: { clientsCount: 0 }
      },
      setupTerminalProxy: vi.fn()
    };
  })
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

    // spawn is called for both python (tournament) and node (pty-helper).
    // Return different mock processes based on the command.
    mocks.spawn.mockImplementation((cmd: string, args: string[]) => {
        if (cmd === "node" && args[0]?.includes("pty-helper")) {
            const helperProc = Object.assign(new EventEmitter(), {
                stdout: new EventEmitter(),
                stderr: new EventEmitter(),
                kill: vi.fn(),
                unref: vi.fn(),
                pid: 9999
            });
            // Simulate helper becoming ready after a tick
            setTimeout(() => {
                helperProc.stdout.emit("data", Buffer.from('{"port":54321}\n'));
            }, 10);
            return helperProc;
        }
        return mockChildProcess;
    });

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
    // Promise stays pending until dashboard server closes
    mockServer.close();
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

  it("should spawn detached PTY helper for terminal sessions", async () => {
    const executionPromise = tournamentTool.execute({
      prompt: "Terminal Test", rounds: 1, agents: 1, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 4000));

    const initEvent = {
      type: "agent_init",
      agent_id: "agent_0",
      session_id: "ses_123",
      api_url: "http://localhost:9999"
    };
    mockChildProcess.stdout.emit("data", Buffer.from(JSON.stringify(initEvent) + "\n"));

    // Wait for helper to "start" and emit port
    await new Promise(resolve => setTimeout(resolve, 200));

    // Verify a helper process was spawned (node pty-helper.js ...)
    const helperCall = mocks.spawn.mock.calls.find(
      (c: string[]) => c[0] === "node" && c[1]?.[0]?.includes("pty-helper")
    );
    expect(helperCall).toBeDefined();
    expect(helperCall[1]).toEqual(expect.arrayContaining([
      expect.stringContaining("pty-helper"),
      "/home/codespace/.opencode/bin/opencode",
      "http://127.0.0.1:9999",
      "ses_123"
    ]));

    // Verify terminal.ready was emitted
    expect(mocks.socketIoEmit).toHaveBeenCalledWith("terminal.ready", { agent_id: "agent_0" });

    mockChildProcess.emit("close", 0);
    mockServer.close();
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
    mockServer.close();
    await executionPromise;
  });

  it("should keep dashboard alive after tournament ends until server closes", async () => {
    const executionPromise = tournamentTool.execute({
      prompt: "Linger Test", rounds: 1, agents: 1, model: "m", provider: "p", log_level: "E", timeout: 1
    }, mockContext);

    await new Promise(resolve => setTimeout(resolve, 4000));

    // Tournament finishes
    mockChildProcess.emit("close", 0);

    // Promise should NOT have resolved yet (dashboard still alive)
    let resolved = false;
    executionPromise.then(() => { resolved = true; });
    await new Promise(resolve => setTimeout(resolve, 200));
    expect(resolved).toBe(false);

    // Now close the dashboard server (simulates all clients disconnecting)
    mockServer.close();
    await executionPromise;
    // Promise resolves only after server closes
    resolved = true;
    expect(resolved).toBe(true);
  });
});
