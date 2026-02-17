import { describe, it, expect, vi, beforeEach } from "vitest";
import { EventEmitter } from "events";
import { Server } from "http";
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

describe("Realistic Terminal Flow", () => {
  let mockPythonProcess: EventEmitter & { stdout: EventEmitter, stderr: EventEmitter };
  let sseServer: Server;
  let ssePort: number;

  beforeEach(async () => {
    vi.clearAllMocks();
    
    mockPythonProcess = Object.assign(new EventEmitter(), {
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
      return mockPythonProcess;
    });
  });

  it("should spawn helper process with correct args for terminal attachment", async () => {
    const express = (await import("express")).default;
    const app = express();
    sseServer = app.listen(0);
    const addr = sseServer.address();
    ssePort = typeof addr === 'string' ? 0 : (addr?.port || 0);

    app.get("/events", (req, res) => {
      res.setHeader('Content-Type', 'text/event-stream');
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
           const match = call.body.message.match(/http:\/\/(localhost|127\.0\.0\.1):\d+/);
           if (match) dashboardUrl = match[0];
        })
      },
      session: { promptAsync: vi.fn() },
      app: { log: vi.fn().mockResolvedValue({}) }
    } as unknown as any;

    const { tournamentPlugin } = await import("../plugins/tournament");
    const hooks = await tournamentPlugin({
      client: mockClient,
      project: {} as Record<string, unknown>,
      directory: "/dir",
      worktree: "/wt",
      serverUrl: new URL("http://localhost"),
      $: vi.fn() as unknown as any
    });

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

    await new Promise(resolve => setTimeout(resolve, 500));

    // Verify helper process was spawned with correct arguments
    const helperCall = mocks.spawn.mock.calls.find(
      (c: string[]) => c[0] === "node" && c[1]?.[0]?.includes("pty-helper")
    );
    expect(helperCall).toBeDefined();
    expect(helperCall[1]).toEqual(expect.arrayContaining([
      expect.stringContaining("pty-helper"),
      "/home/codespace/.opencode/bin/opencode",
      `http://127.0.0.1:${ssePort}`,
      "ses_real_sse",
      "/mock/arena"
    ]));

    clientSocket.disconnect();
    sseServer.close();
    mockPythonProcess.emit("close", 0);
    await execPromise;
  }, 30000);
});
