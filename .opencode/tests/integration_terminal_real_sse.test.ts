import { describe, it, expect, vi, beforeEach } from "vitest";
import { EventEmitter } from "events";
import { Server } from "http";
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
  ptySpawn: vi.fn().mockImplementation(() => ({
    onData: vi.fn(),
    onExit: vi.fn(),
    write: vi.fn(),
    kill: vi.fn(),
    resize: vi.fn()
  })),
  spawn: vi.fn()
}));

vi.mock("node-pty", () => ({
  spawn: mocks.ptySpawn
}));

vi.mock("child_process", () => ({
  spawn: mocks.spawn
}));

vi.mock("open", () => ({
  default: vi.fn().mockResolvedValue(undefined)
}));

describe("Realistic Terminal Flow", () => {
  let mockPythonProcess: EventEmitter & { stdout: EventEmitter, stderr: EventEmitter };
  let sseServer: Server;
  let ssePort: number;

  beforeEach(async () => {
    vi.clearAllMocks();
    
    // Mock Python backend
    mockPythonProcess = Object.assign(new EventEmitter(), {
      stdout: new EventEmitter(),
      stderr: new EventEmitter()
    }) as unknown as EventEmitter & { stdout: EventEmitter, stderr: EventEmitter };
    mocks.spawn.mockReturnValue(mockPythonProcess);
  });

  it("should connect the dashboard to a realistic SSE session and verify PTY attachment params", async () => {
    const express = (await import("express")).default;
    const app = express();
    sseServer = app.listen(0);
    const addr = sseServer.address();
    ssePort = typeof addr === 'string' ? 0 : (addr?.port || 0);

    app.get("/events", (req, res) => {
      res.setHeader('Content-Type', 'text/event-stream');
      res.setHeader('Cache-Control', 'no-cache');
      res.setHeader('Connection', 'keep-alive');
      res.flushHeaders();
      
      const data = JSON.stringify({
        type: 'message.part.updated',
        properties: { delta: "RealSSE", part: { sessionID: "ses_real_sse" } }
      });
      res.write(`data: ${data}\n\n`);
    });

    let dashboardUrl = "";
    const mockClient = {
      tui: {
        showToast: vi.fn().mockImplementation(async (call: { body: { message: string } }) => {
           const msg = call.body.message;
           const match = msg.match(/http:\/\/(localhost|127\.0\.0\.1):\d+/);
           if (match) dashboardUrl = match[0];
        })
      },
      session: { promptAsync: vi.fn() },
      app: { log: vi.fn().mockResolvedValue({}) }
    } as unknown as any; // Temporary until we have full SDK types

    const { tournamentPlugin } = await import("../plugins/tournament");
    const hooks = await tournamentPlugin({
      client: mockClient,
      project: {} as Record<string, unknown>,
      directory: "/dir",
      worktree: "/wt",
      serverUrl: new URL("http://localhost"),
      $: vi.fn() as unknown as any
    });

    // DO NOT AWAIT
    const execPromise = hooks.tool.tournament.execute({
      prompt: "Test", rounds: 1, agents: 1, model: "m", provider: "p"
    }, { sessionID: "main_ses" } as ToolContext);

    await new Promise(resolve => setTimeout(resolve, 4000));
    expect(dashboardUrl).not.toBe("");

    const clientSocket: ClientSocket = ClientIO(dashboardUrl, { transports: ["polling"] });
    await new Promise<void>(resolve => clientSocket.on("connect", resolve));

    const initEvent = {
      type: "agent_init",
      agent_id: "agent_real_sse",
      session_id: "ses_real_sse",
      api_url: `http://127.0.0.1:${ssePort}`,
      arena_dir: "/mock/arena"
    };
    mockPythonProcess.stdout.emit("data", Buffer.from(JSON.stringify(initEvent) + "\n"));

    // Give plugin time to process agent_init
    await new Promise(resolve => setTimeout(resolve, 1000));

    clientSocket.emit("terminal.init", { agent_id: "agent_real_sse" });

    await new Promise(resolve => setTimeout(resolve, 2000));
    expect(mocks.ptySpawn).toHaveBeenCalledWith(
      "/home/codespace/.opencode/bin/opencode",
      ["attach", `http://127.0.0.1:${ssePort}`, "-s", "ses_real_sse", "--print-logs"],
      expect.objectContaining({
          cwd: "/mock/arena",
          env: expect.objectContaining({
              TERM: "xterm-256color"
          })
      })
    );

    clientSocket.disconnect();
    sseServer.close();
    mockPythonProcess.emit("close", 0);
    await execPromise;
  }, 30000);
});
