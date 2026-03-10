import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

// --- Mocks Setup ---
const mocks = vi.hoisted(() => ({
    app: {
        use: vi.fn(),
        post: vi.fn(),
        get: vi.fn(),
    },
    server: {
        listen: vi.fn((...args) => {
            const cb = args.find(a => typeof a === 'function');
            if (cb) cb();
        }),
        address: vi.fn(() => ({ port: 8080 })),
        close: vi.fn((cb) => { if(cb) cb(); }),
        on: vi.fn(),
    },
    io: {
        on: vi.fn(),
        emit: vi.fn(),
        engine: { clientsCount: 0 },
    },
    terminalManager: {
        registerAgent: vi.fn(),
        spawnTerminal: vi.fn(),
        close: vi.fn(),
    },
    setupTerminalProxy: vi.fn(),
    exec: vi.fn((cmd, cb) => cb && cb(null)),
    spawn: vi.fn().mockReturnValue({
        stdout: { on: vi.fn() },
        stderr: { on: vi.fn() },
        on: vi.fn(),
        unref: vi.fn(),
        kill: vi.fn(),
    }),
    processExit: vi.fn(),
    EventSource: vi.fn(),
}));

// Mock modules BEFORE importing the SUT

vi.mock("express", () => ({
    default: Object.assign(() => mocks.app, { json: vi.fn() }),
}));

vi.mock("eventsource", () => ({
    EventSource: mocks.EventSource,
}));

vi.mock("child_process", () => ({
    exec: mocks.exec,
    spawn: mocks.spawn
}));

vi.mock("../lib/dashboard.app", () => ({
    createDashboardApp: vi.fn(() => ({
        app: mocks.app,
        server: mocks.server,
        io: mocks.io,
        setupTerminalProxy: mocks.setupTerminalProxy,
    })),
}));

// Fix for Constructor Mock - Use regular function
vi.mock("../lib/terminal.manager", () => {
    return {
        TerminalManager: vi.fn().mockImplementation(function() { 
            return mocks.terminalManager; 
        })
    };
});

// Mock process.exit
// @ts-ignore
process.exit = mocks.processExit;

describe("Dashboard Server Logic", () => {
    
    beforeEach(() => {
        vi.clearAllMocks();
        mocks.io.engine.clientsCount = 0;
        vi.resetModules();
    });

    const getHandler = (path: string) => {
        const calls = mocks.app.post.mock.calls;
        const call = calls.find((c: any[]) => c[0] === path);
        return call ? call[1] : null;
    };

    it("should initialize server and listen on a port", async () => {
        await import("../lib/dashboard-server");
        expect(mocks.server.listen).toHaveBeenCalled();
        const { TerminalManager } = await import("../lib/terminal.manager");
        expect(TerminalManager).toHaveBeenCalled();
    });

    it("should handle /api/log requests and broadcast via socket.io", async () => {
        await import("../lib/dashboard-server");
        const handler = getHandler("/api/log");
        expect(handler).toBeDefined();

        const req = { body: { type: "log", message: "Hello" } };
        const res = { sendStatus: vi.fn() };

        handler(req, res);

        expect(mocks.io.emit).toHaveBeenCalledWith("log", req.body);
        expect(res.sendStatus).toHaveBeenCalledWith(200);
    });

    it("should handle batched log requests", async () => {
        await import("../lib/dashboard-server");
        const handler = getHandler("/api/log");
        
        const events = [
            { type: 'log', message: 'one' },
            { type: 'log', message: 'two' }
        ];
        const req = { body: { type: 'batch', events } };
        const res = { sendStatus: vi.fn() };

        handler(req, res);

        expect(mocks.io.emit).toHaveBeenCalledTimes(2);
        expect(mocks.io.emit).toHaveBeenNthCalledWith(1, "log", events[0]);
        expect(mocks.io.emit).toHaveBeenNthCalledWith(2, "log", events[1]);
        expect(res.sendStatus).toHaveBeenCalledWith(200);
    });

    it("should register agents via /api/agent and setup streaming", async () => {
        await import("../lib/dashboard-server");
        const handler = getHandler("/api/agent");
        expect(handler).toBeDefined();

        const agentData = {
            api_url: "http://localhost:5000",
            session_id: "ses_1",
            agent_id: "agent_0",
            arena_dir: "/tmp/arena"
        };
        const req = { body: agentData };
        const res = { sendStatus: vi.fn(), status: vi.fn().mockReturnThis(), send: vi.fn() };

        // Mock EventSource instance
        const mockES = { onmessage: null, onerror: null, close: vi.fn() };
        mocks.EventSource.mockImplementation(function() { return mockES; });

        handler(req, res);

        expect(mocks.terminalManager.registerAgent).toHaveBeenCalledWith(
            "agent_0", "http://localhost:5000", "ses_1", "/tmp/arena"
        );
        expect(mocks.terminalManager.spawnTerminal).toHaveBeenCalledWith("agent_0");

        expect(mocks.EventSource).toHaveBeenCalledWith("http://localhost:5000/event");
        
        const sseEvent = {
            type: "message.part.updated",
            properties: {
                part: { sessionID: "ses_1" },
                delta: "Chunk"
            }
        };
        
        // Wait for parallel setup
        await new Promise(resolve => setTimeout(resolve, 50));

        if (mockES.onmessage) {
            (mockES.onmessage as any)({ data: JSON.stringify(sseEvent) });
        }

        expect(mocks.io.emit).toHaveBeenCalledWith("log", expect.objectContaining({
            type: "agent_stream",
            agent_id: "agent_0",
            text: "Chunk"
        }));

        expect(res.sendStatus).toHaveBeenCalledWith(200);
    });

    it("should trigger cleanup when all clients disconnect AFTER parent exits", async () => {
        vi.useFakeTimers();
        
        // Mock stdin.on to capture the 'end' handler
        const stdinOnMock = vi.spyOn(process.stdin, 'on');
        
        await import("../lib/dashboard-server");

        // 1. Get the 'end' handler for stdin
        const endCall = stdinOnMock.mock.calls.find(c => c[0] === 'end');
        const endHandler = endCall![1];

        // 2. Setup socket.io disconnect handler
        const connectionCall = mocks.io.on.mock.calls.find((c: any[]) => c[0] === 'connection');
        const connectionHandler = connectionCall[1];
        const mockSocket = { on: vi.fn() };
        connectionHandler(mockSocket);
        const disconnectHandler = mockSocket.on.mock.calls.find((c: any[]) => c[0] === 'disconnect')![1];
        
        // 3. Disconnect while parent is ALIVE
        mocks.io.engine.clientsCount = 0;
        disconnectHandler();
        vi.advanceTimersByTime(15000);
        
        // Should NOT be closed yet
        expect(mocks.server.close).not.toHaveBeenCalled();

        // 4. Simulate Parent Exit
        endHandler();
        
        // 5. Trigger disconnect or wait for the 60s timer
        vi.advanceTimersByTime(65000);

        expect(mocks.terminalManager.close).toHaveBeenCalled();
        expect(mocks.server.close).toHaveBeenCalled();
        expect(mocks.processExit).toHaveBeenCalledWith(0);

        vi.useRealTimers();
    });
});
