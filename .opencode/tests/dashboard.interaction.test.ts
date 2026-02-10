import { describe, it, expect, vi, beforeEach } from "vitest";
import { JSDOM } from "jsdom";
import fs from "fs";
import path from "path";

describe("Dashboard Interactive UI", () => {
  let dom: JSDOM;
  let window: any;
  let document: any;
  let mockSocket: any;

  beforeEach(async () => {
    let html = fs.readFileSync(path.join(__dirname, "../plugins/dashboard.html"), "utf8");
    
    // Strip external scripts to prevent JSDOM from trying to load them
    html = html.replace(/<script src="https:\/\/cdn.tailwindcss.com"><\/script>/, "");
    html = html.replace(/<script src="https:\/\/cdn.jsdelivr.net\/npm\/chart.js"><\/script>/, "");
    html = html.replace('<script src="/socket.io/socket.io.js"></script>', "");

    mockSocket = {
      on: vi.fn(),
      emit: vi.fn(),
    };

    // 1. Create JSDOM with mocks injected via beforeParse
    dom = new JSDOM(html, { 
        runScripts: "dangerously", 
        resources: "usable", 
        url: "http://localhost",
        beforeParse(window) {
            // Mock Socket.io
            window.io = () => mockSocket;
            
            // Mock Chart.js constructor
            const MockChart = function(ctx: any, config: any) {
                const inst = {
                    data: config.data || { labels: [], datasets: [] },
                    options: config.options || {},
                    update: vi.fn(),
                    destroy: vi.fn(),
                };
                if (!window.__charts) window.__charts = [];
                window.__charts.push(inst);
                return inst;
            };
            (MockChart as any).defaults = { font: {}, plugins: {}, elements: {}, scales: {} };
            window.Chart = MockChart as any;
            
            // Mock Canvas and its context
            window.HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
                measureText: () => ({ width: 0 }),
                canvas: { style: { width: '100px', height: '100px' } }
            }));
            
            // Mock ownerDocument on prototype
            Object.defineProperty(window.HTMLCanvasElement.prototype, 'ownerDocument', {
                get: function() { return this.parentNode ? this.parentNode.ownerDocument : window.document; }
            });
        }
    });
    
    window = dom.window;
    document = window.document;

    // Wait for internal scripts to finish execution
    await new Promise(resolve => setTimeout(resolve, 300));
  });

  it("should render state data and handle agent inspection", async () => {
    // 1. Verify log handler was registered
    const logCall = mockSocket.on.mock.calls.find(c => c[0] === 'log');
    expect(logCall).toBeDefined();
    const logHandler = logCall[1];

    // 2. Simulate tournament state update
    logHandler({
      type: "state",
      round_num: 42,
      whale_wealth: 9999,
      liquidity_b: 50,
      assets: {
        "cand_0": { type: "CANDIDATE", q_yes: 10, q_no: 0 }
      },
      agents: {
        "agent_0": { agent_id: "agent_0", wealth: 150 }
      }
    });

    // 3. Assert UI rendered correctly
    expect(document.getElementById("round-info").textContent).toContain("ROUND 42");
    
    const assetTable = document.getElementById("tables");
    expect(assetTable.innerHTML).toContain("cand_0");
    
    const agentTable = document.getElementById("agents-table");
    expect(agentTable.innerHTML).toContain("agent_0");
    expect(agentTable.innerHTML).toContain("Whale");
    expect(agentTable.innerHTML).toContain("$9999");

    // 4. Assert Charts were updated
    expect(window.__charts).toBeDefined();
    expect(window.__charts.length).toBeGreaterThan(0);
    window.__charts.forEach((c: any) => expect(c.update).toHaveBeenCalled());

    // 5. Test Agent Explorer Modal
    // Simulate agent trace
    logHandler({
      type: "agent_trace",
      agent_id: "agent_0",
      timestamp: "10:00 AM",
      prompt: "Solve the problem",
      response: "Solution here"
    });

    // Click agent row
    const agentRow = document.querySelector('tr[onclick*="agent_0"]');
    expect(agentRow).toBeDefined();
    (agentRow as HTMLElement).click();

    // Verify modal appeared and has data
    const modal = document.getElementById("agent-modal");
    expect(modal.classList.contains("opacity-0")).toBe(false);
    expect(document.getElementById("modal-body").innerHTML).toContain("Solve the problem");
    expect(document.getElementById("modal-body").innerHTML).toContain("Solution here");
  });
});
