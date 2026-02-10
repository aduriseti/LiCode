import { describe, it, expect, vi, beforeEach } from "vitest";
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";

describe("Dashboard Multi-Round Updates", () => {
  let dom: JSDOM;
  let window: any;
  let document: any;
  let mockSocket: any;

  beforeEach(async () => {
    let html = fs.readFileSync(path.join(__dirname, "../plugins/dashboard.html"), "utf8");
    html = html.replace(/<script src="https:\/\/cdn.tailwindcss.com"><\/script>/, "");
    html = html.replace(/<script src="https:\/\/cdn.jsdelivr.net\/npm\/chart.js"><\/script>/, "");
    html = html.replace('<script src="/socket.io/socket.io.js"></script>', "");

    mockSocket = { on: vi.fn(), emit: vi.fn() };

    dom = new JSDOM(html, { 
        runScripts: "dangerously", 
        url: "http://localhost",
        beforeParse(window) {
            window.io = () => mockSocket;
            const MockChart = function(ctx: any, config: any) {
                const inst = {
                    data: config.data,
                    update: vi.fn(),
                    destroy: vi.fn(),
                };
                if (!window.__charts) window.__charts = [];
                window.__charts.push(inst);
                return inst;
            };
            (MockChart as any).defaults = { font: {}, plugins: {}, elements: {}, scales: {} };
            window.Chart = MockChart as any;
            window.HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ measureText: () => ({ width: 0 }) }));
            Object.defineProperty(window.HTMLCanvasElement.prototype, 'ownerDocument', {
                get: function() { return window.document; }
            });
        }
    });
    window = dom.window;
    document = window.document;
    await new Promise(resolve => setTimeout(resolve, 200));
  });

  it("should update state and charts correctly across multiple rounds", async () => {
    const logHandler = mockSocket.on.mock.calls.find(c => c[0] === 'log')[1];

    // --- ROUND 1 ---
    logHandler({
      type: "state",
      round_num: 1,
      whale_wealth: 1000,
      liquidity_b: 100,
      assets: { "cand_0": { type: "CANDIDATE", q_yes: 0, q_no: 0 } },
      agents: { "agent_0": { agent_id: "agent_0", wealth: 100 } }
    });

    expect(document.getElementById("round-info").textContent).toContain("ROUND 1");
    expect(window.__charts[0].data.labels).toContain("R1");
    expect(window.__charts[0].data.datasets[0].data).toHaveLength(1);
    expect(window.__charts[0].data.datasets[0].data[0]).toBe(0.5); // Initial price

    // --- ROUND 2 ---
    logHandler({
      type: "state",
      round_num: 2,
      whale_wealth: 950,
      liquidity_b: 100,
      assets: { "cand_0": { type: "CANDIDATE", q_yes: 50, q_no: 0 } },
      agents: { "agent_0": { agent_id: "agent_0", wealth: 150 } }
    });

    expect(document.getElementById("round-info").textContent).toContain("ROUND 2");
    expect(window.__charts[0].data.labels).toContain("R2");
    expect(window.__charts[0].data.datasets[0].data).toHaveLength(2);
    // Price should have increased (q_yes: 50, q_no: 0, b: 100) -> P = 1 / (1 + e^-0.5) approx 0.622
    expect(window.__charts[0].data.datasets[0].data[1]).toBeGreaterThan(0.6);

    // --- ROUND 3 (with a new asset appearing) ---
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

    expect(document.getElementById("round-info").textContent).toContain("ROUND 3");
    expect(window.__charts[0].data.labels).toHaveLength(3);
    
    // cand_0 should have 3 data points
    const cand0Ds = window.__charts[0].data.datasets.find(d => d.label === "cand_0");
    expect(cand0Ds.data).toHaveLength(3);

    // v_new should have 3 data points (padded with null for previous rounds)
    const vNewDs = window.__charts[0].data.datasets.find(d => d.label === "v_new");
    expect(vNewDs.data).toHaveLength(3);
    expect(vNewDs.data[0]).toBeNull();
    expect(vNewDs.data[1]).toBeNull();
    expect(vNewDs.data[2]).toBeDefined();

    // Verify Traders table shows all
    const agentTable = document.getElementById("agents-table");
    expect(agentTable.innerHTML).toContain("$900"); // Whale
    expect(agentTable.innerHTML).toContain("$200"); // Agent 0
  });
});
