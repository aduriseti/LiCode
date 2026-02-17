import { describe, it, expect, vi, beforeEach } from "vitest";
import { JSDOM, DOMWindow } from "jsdom";
import fs from "fs";
import path from "path";

interface MockSocket {
    on: ReturnType<typeof vi.fn>;
    emit: ReturnType<typeof vi.fn>;
}

describe("Dashboard Terminal Unit Logic", () => {
  let dom: JSDOM;
  let window: DOMWindow & { [key: string]: unknown };
  let document: Document;
  let mockSocket: MockSocket;

  beforeEach(async () => {
    const html = fs.readFileSync(path.join(__dirname, "../plugins/dashboard.html"), "utf8");
    
    const cleanHtml = html
        .replace(/<script src="https:\/\/cdn.tailwindcss.com"><\/script>/, "")
        .replace(/<script src="https:\/\/cdn.jsdelivr.net\/npm\/chart.js"><\/script>/, "")
        .replace('<script src="/socket.io/socket.io.js"></script>', "")
        .replace(/<link.*xterm.min.css.*>/, "")
        .replace(/<script.*xterm.min.js.*><\/script>/, "")
        .replace(/<script.*fit.min.js.*><\/script>/, "");

    mockSocket = { on: vi.fn(), emit: vi.fn() };

    dom = new JSDOM(cleanHtml, { 
        runScripts: "dangerously", 
        url: "http://localhost",
        beforeParse(window) {
            (window as any).io = () => mockSocket;
            const MockChart = function() { return { data: { labels: [], datasets: [] }, update: vi.fn(), destroy: vi.fn() }; };
            (MockChart as any).defaults = { font: {}, plugins: {}, elements: {}, scales: {} };
            (window as any).Chart = MockChart;
            
            const MockTerminal = function() {
                return {
                    loadAddon: vi.fn(),
                    open: vi.fn(),
                    onData: vi.fn(),
                    write: vi.fn(),
                    clear: vi.fn(),
                    reset: vi.fn(),
                    focus: vi.fn(),
                    refresh: vi.fn(),
                    cols: 80,
                    rows: 24
                };
            };
            (window as any).Terminal = MockTerminal;
            (window as any).FitAddon = { FitAddon: function() { return { fit: vi.fn() }; } };
            // Mock WebSocket - track instances for assertions
            const wsInstances: any[] = [];
            const MockWebSocket = function(this: any, url: string) {
                this.url = url;
                this.send = vi.fn();
                this.close = vi.fn();
                this.readyState = 1;
                this.onopen = null;
                this.onmessage = null;
                this.onclose = null;
                wsInstances.push(this);
                setTimeout(() => { if (this.onopen) this.onopen(); }, 0);
            } as any;
            MockWebSocket.OPEN = 1;
            MockWebSocket._instances = wsInstances;
            (window as any).WebSocket = MockWebSocket;

            (window as any).requestAnimationFrame = (cb: () => void) => setTimeout(cb, 0);
            window.HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ measureText: () => ({ width: 0 }) })) as any;
            Object.defineProperty(window.HTMLCanvasElement.prototype, 'ownerDocument', { get: function() { return window.document; } });
        }
    });
    window = dom.window as unknown as typeof window;
    document = window.document;
    await new Promise(resolve => setTimeout(resolve, 200));
  });

  it("should request terminal init when an agent is selected", async () => {
    const logHandler = mockSocket.on.mock.calls.find((c: unknown[]) => (c as string[])[0] === 'log')![1];
    
    logHandler({
      type: "state",
      round_num: 1,
      whale_wealth: 1000,
      liquidity_b: 100,
      assets: {},
      agents: { "agent_unit": { agent_id: "agent_unit", wealth: 100 } }
    });

    const agentRow = document.querySelector('tr[onclick*="agent_unit"]');
    expect(agentRow).toBeDefined();
    (agentRow as HTMLElement).click();

    expect(mockSocket.emit).toHaveBeenCalledWith("terminal.init", { agent_id: "agent_unit" });
  });

  it("should create terminal and connect via WebSocket on terminal.ready", async () => {
    const readyHandler = mockSocket.on.mock.calls.find((c: unknown[]) => (c as string[])[0] === 'terminal.ready')![1];

    readyHandler({ agent_id: "agent_unit" });

    await new Promise(resolve => setTimeout(resolve, 50));

    // Verify WebSocket was created connecting through the proxy
    const wsInstances = (window as any).WebSocket._instances;
    expect(wsInstances.length).toBeGreaterThan(0);
    expect(wsInstances[0].url).toBe("ws://localhost/terminal/agent_unit");

    // Verify terminal container was created
    const container = document.getElementById("terminal-agent_unit");
    expect(container).toBeDefined();
  });
});
