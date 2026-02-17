import { describe, it, expect, vi, beforeEach } from "vitest";
import { JSDOM, DOMWindow } from "jsdom";
import fs from "fs";
import path from "path";

interface MockSocket {
    on: ReturnType<typeof vi.fn>;
    emit: ReturnType<typeof vi.fn>;
}

describe("Dashboard Interactive Console", () => {
  let dom: JSDOM;
  let window: DOMWindow & { [key: string]: unknown };
  let document: Document;
  let mockSocket: MockSocket;

  beforeEach(async () => {
    let html = fs.readFileSync(path.join(__dirname, "../plugins/dashboard.html"), "utf8");
    html = html.replace(/<script src="https:\/\/cdn.tailwindcss.com"><\/script>/, "");
    html = html.replace(/<script src="https:\/\/cdn.jsdelivr.net\/npm\/chart.js"><\/script>/, "");
    html = html.replace('<script src="/socket.io/socket.io.js"></script>', "");
    html = html.replace(/<link.*xterm.min.css.*>/, "");
    html = html.replace(/<script.*xterm.min.js.*><\/script>/, "");
    html = html.replace(/<script.*fit.min.js.*><\/script>/, "");

    mockSocket = { on: vi.fn(), emit: vi.fn() };

    dom = new JSDOM(html, { 
        runScripts: "dangerously", 
        url: "http://localhost",
        beforeParse(window) {
            (window as any).io = () => mockSocket;
            // Mock Chart
            const MockChart = function() { return { data: { labels: [], datasets: [] }, update: vi.fn(), destroy: vi.fn() }; };
            (MockChart as any).defaults = { font: {}, plugins: {}, elements: {}, scales: {} };
            (window as any).Chart = MockChart;
            
            // Mock Terminal
            const MockTerminal = function() {
                return {
                    loadAddon: vi.fn(),
                    open: vi.fn(),
                    onData: vi.fn(),
                    write: vi.fn(),
                    clear: vi.fn(),
                    reset: vi.fn(),
                    focus: vi.fn(),
                    cols: 80,
                    rows: 24,
                    refresh: vi.fn()
                };
            };
            (window as any).Terminal = MockTerminal;
            (window as any).FitAddon = { FitAddon: function() { return { fit: vi.fn() }; } };

            // Mock WebSocket
            (window as any).WebSocket = function(this: any, url: string) {
                this.url = url; this.send = vi.fn(); this.close = vi.fn();
                this.readyState = 1; this.onopen = null; this.onmessage = null; this.onclose = null;
            };
            (window as any).WebSocket.OPEN = 1;

            (window as any).requestAnimationFrame = (cb: () => void) => setTimeout(cb, 0);
            window.HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ measureText: () => ({ width: 0 }) })) as any;
            Object.defineProperty(window.HTMLCanvasElement.prototype, 'ownerDocument', { get: function() { return window.document; } });
        }
    });
    window = dom.window as unknown as DOMWindow & { [key: string]: unknown };
    document = window.document;
    await new Promise(resolve => setTimeout(resolve, 200));
  });

  it("should initialize terminal and emit init event when agent is clicked", async () => {
    const logHandler = mockSocket.on.mock.calls.find((c: unknown[]) => (c as string[])[0] === 'log')![1];

    // 1. Initial State
    logHandler({
      type: "state",
      round_num: 1,
      whale_wealth: 1000,
      assets: {},
      agents: { "agent_0": { agent_id: "agent_0", wealth: 100 } }
    });

    // 2. Select Agent
    const agentRow = document.querySelector('tr[onclick*="agent_0"]');
    expect(agentRow).toBeDefined();
    (agentRow as HTMLElement).click();

    // 3. Verify Socket Event - terminal.init is emitted during createTerminalForAgent->initializeTerminal
    expect(mockSocket.emit).toHaveBeenCalledWith("terminal.init", { agent_id: "agent_0" });
    
    // 4. Verify UI Update
    expect(document.getElementById("explorer-status")!.textContent).toContain("agent_0");
  });

  it("should keep bankrupt agents visible in the traders table", async () => {
    const logHandler = mockSocket.on.mock.calls.find((c: unknown[]) => (c as string[])[0] === 'log')![1];

    // Round 1: agent_0 is alive with wealth
    logHandler({
      type: "state",
      round_num: 1,
      whale_wealth: 1000,
      assets: {},
      agents: { "agent_0": { agent_id: "agent_0", wealth: 100 } }
    });

    let agentRow = document.querySelector('tr[onclick*="agent_0"]');
    expect(agentRow).not.toBeNull();

    // Round 2: agent_0 went bankrupt (removed from agents dict by orchestrator)
    logHandler({
      type: "state",
      round_num: 2,
      whale_wealth: 1100,
      assets: {},
      agents: {}
    });

    // agent_0 should still appear in the traders table with $0
    agentRow = document.querySelector('tr[onclick*="agent_0"]');
    expect(agentRow).not.toBeNull();
    expect(agentRow!.textContent).toContain("$0");

    // Terminal tab should also still exist
    const tabButtons = document.querySelectorAll('.tab-button');
    const agentTab = Array.from(tabButtons).find(btn => btn.textContent === 'agent_0');
    expect(agentTab).toBeDefined();
  });
});