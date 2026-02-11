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
  let window: DOMWindow & { [key: string]: unknown, term: { write: (data: string) => void }, selectAgent: (id: string) => void };
  let document: Document;
  let mockSocket: MockSocket;

  beforeEach(async () => {
    const html = fs.readFileSync(path.join(__dirname, "../plugins/dashboard.html"), "utf8");
    
    // Minimal cleanup for JSDOM
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
            // Mock Chart.js
            const MockChart = function() { return { data: { labels: [], datasets: [] }, update: vi.fn(), destroy: vi.fn() }; };
            (MockChart as any).defaults = { font: {}, plugins: {}, elements: {}, scales: {} };
            (window as any).Chart = MockChart;
            
            // Mock Xterm Terminal
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

            window.HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ measureText: () => ({ width: 0 }) })) as any;
            Object.defineProperty(window.HTMLCanvasElement.prototype, 'ownerDocument', { get: function() { return window.document; } });
        }
    });
    window = dom.window as unknown as typeof window;
    document = window.document;
    // Wait for internal script execution
    await new Promise(resolve => setTimeout(resolve, 200));
  });

  it("should request terminal init when an agent is selected", async () => {
    const logHandler = mockSocket.on.mock.calls.find((c: unknown[]) => (c as string[])[0] === 'log')![1];
    
    // Simulate receiving market state
    logHandler({
      type: "state",
      round_num: 1,
      whale_wealth: 1000,
      liquidity_b: 100,
      assets: {},
      agents: { "agent_unit": { agent_id: "agent_unit", wealth: 100 } }
    });

    // Interaction: User clicks on the agent row
    const agentRow = document.querySelector('tr[onclick*="agent_unit"]');
    expect(agentRow).toBeDefined();
    (agentRow as HTMLElement).click();

    // Verify: Dashboard emits terminal.init event
    expect(mockSocket.emit).toHaveBeenCalledWith("terminal.init", { agent_id: "agent_unit" });
  });

  it("should write data to terminal when receiving terminal.output", async () => {
    // Select agent first
    const selectAgentFn = window.selectAgent;
    selectAgentFn("agent_unit");

    const outputHandler = mockSocket.on.mock.calls.find((c: unknown[]) => (c as string[])[0] === 'terminal.output')![1];
    const termWriteSpy = vi.spyOn(window.term, 'write');

    outputHandler({ agent_id: "agent_unit", data: "UNIT_TEST_OUTPUT" });

    expect(termWriteSpy).toHaveBeenCalledWith("UNIT_TEST_OUTPUT");
  });
});