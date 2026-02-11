import { describe, it, expect, vi, beforeEach } from "vitest";
import { JSDOM, DOMWindow } from "jsdom";
import fs from "fs";
import path from "path";

interface MockSocket {
    on: ReturnType<typeof vi.fn>;
    emit: ReturnType<typeof vi.fn>;
}

describe("Dashboard Multi-Round Updates", () => {
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
            
            const MockChart = function() {
                return {
                    data: { labels: [], datasets: [] },
                    update: vi.fn(),
                    destroy: vi.fn(),
                };
            };
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
                    cols: 80,
                    rows: 24
                };
            };
            (window as any).Terminal = MockTerminal;
            const MockFitAddon = function() {
                return { fit: vi.fn() };
            };
            (window as any).FitAddon = { FitAddon: MockFitAddon };

            window.HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ measureText: () => ({ width: 0 }) })) as any;
            Object.defineProperty(window.HTMLCanvasElement.prototype, 'ownerDocument', {
                get: function() { return window.document; }
            });
        }
    });
    window = dom.window as unknown as DOMWindow & { [key: string]: unknown };
    document = window.document;
    await new Promise(resolve => setTimeout(resolve, 200));
  });

  it("should update state and charts correctly across multiple rounds", async () => {
    const logHandler = mockSocket.on.mock.calls.find((c: unknown[]) => (c as string[])[0] === 'log')![1];

    // --- ROUND 1 ---
    logHandler({
      type: "state",
      round_num: 1,
      whale_wealth: 1000,
      liquidity_b: 100,
      assets: { "cand_0": { type: "CANDIDATE", q_yes: 0, q_no: 0 } },
      agents: { "agent_0": { agent_id: "agent_0", wealth: 100 } }
    });

    expect(document.getElementById("round-info")!.textContent).toContain("ROUND 1");
    
    const assetTable = document.getElementById("tables")!;
    expect(assetTable.innerHTML).toContain("cand_0");

    // --- ROUND 2 ---
    logHandler({
      type: "state",
      round_num: 2,
      whale_wealth: 950,
      liquidity_b: 100,
      assets: { "cand_0": { type: "CANDIDATE", q_yes: 50, q_no: 0 } },
      agents: { "agent_0": { agent_id: "agent_0", wealth: 150 } }
    });

    expect(document.getElementById("round-info")!.textContent).toContain("ROUND 2");

    // --- ROUND 3 ---
    logHandler({
      type: "state",
      round_num: 3,
      whale_wealth: 900,
      liquidity_b: 100,
      assets: { 
        "cand_0": { type: "CANDIDATE", q_yes: 60, q_no: 0 },
        "v_new": { type: "VERIFIER", q_yes: 10, q_no: 0 } 
      },
      agents: { "agent_0": { agent_id: "agent_0", wealth: 200 } }
    });

    expect(document.getElementById("round-info")!.textContent).toContain("ROUND 3");
    
    const agentTable = document.getElementById("agents-table")!;
    expect(agentTable.innerHTML).toContain("$900"); // Whale
    expect(agentTable.innerHTML).toContain("$200"); // Agent 0
  });
});
