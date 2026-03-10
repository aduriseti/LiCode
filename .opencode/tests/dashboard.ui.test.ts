import { describe, it, expect, vi, beforeEach } from "vitest";
import { JSDOM, DOMWindow } from "jsdom";
import fs from "fs";
import path from "path";

interface MockSocket {
    on: ReturnType<typeof vi.fn>;
    emit: ReturnType<typeof vi.fn>;
}

describe("Dashboard UI", () => {
    let dom: JSDOM;
    let window: DOMWindow & { [key: string]: unknown };
    let document: Document;
    let mockSocket: MockSocket;

    beforeEach(async () => {
        let html = fs.readFileSync(path.join(__dirname, "../plugins/dashboard.html"), "utf8");
        html = html.replace(/<script src="https:\/\/cdn.tailwindcss.com"><\/script>/, "");
        html = html.replace(
            /<script src="https:\/\/cdn.jsdelivr.net\/npm\/chart.js"><\/script>/,
            "",
        );
        html = html.replace('<script src="/socket.io/socket.io.js"></script>', "");
        html = html.replace(/<link.*xterm.min.css.*>/, "");
        html = html.replace(/<script.*xterm.min.js.*><\/script>/, "");
        html = html.replace(/<script.*fit.min.js.*><\/script>/, "");

        mockSocket = { on: vi.fn(), emit: vi.fn() };

        const wsInstances: any[] = [];

        dom = new JSDOM(html, {
            runScripts: "dangerously",
            url: "http://localhost",
            beforeParse(window) {
                (window as any).io = () => mockSocket;

                const MockChart = function () {
                    return {
                        data: { labels: [], datasets: [] },
                        update: vi.fn(),
                        destroy: vi.fn(),
                    };
                };
                (MockChart as any).defaults = { font: {}, plugins: {}, elements: {}, scales: {} };
                (window as any).Chart = MockChart;

                (window as any).Terminal = function () {
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
                        rows: 24,
                    };
                };
                (window as any).FitAddon = {
                    FitAddon: function () {
                        return { fit: vi.fn() };
                    },
                };

                const MockWebSocket = function (this: any, url: string) {
                    this.url = url;
                    this.send = vi.fn();
                    this.close = vi.fn();
                    this.readyState = 1;
                    this.onopen = null;
                    this.onmessage = null;
                    this.onclose = null;
                    wsInstances.push(this);
                    setTimeout(() => {
                        if (this.onopen) this.onopen();
                    }, 0);
                } as any;
                MockWebSocket.OPEN = 1;
                MockWebSocket._instances = wsInstances;
                (window as any).WebSocket = MockWebSocket;

                (window as any).requestAnimationFrame = (cb: () => void) => setTimeout(cb, 0);
                window.HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
                    measureText: () => ({ width: 0 }),
                })) as any;
                Object.defineProperty(window.HTMLCanvasElement.prototype, "ownerDocument", {
                    get: function () {
                        return window.document;
                    },
                });
            },
        });
        window = dom.window as unknown as typeof window;
        document = window.document;
        await new Promise((resolve) => setTimeout(resolve, 200));
    });

    function getLogHandler() {
        return mockSocket.on.mock.calls.find((c: unknown[]) => (c as string[])[0] === "log")![1];
    }

    it("should emit terminal.init when an agent row is clicked", () => {
        const logHandler = getLogHandler();
        logHandler({
            type: "state",
            round_num: 1,
            whale_wealth: 1000,
            assets: {},
            agents: { agent_0: { agent_id: "agent_0", wealth: 100 } },
        });

        const agentRow = document.querySelector('tr[onclick*="agent_0"]');
        expect(agentRow).toBeDefined();
        (agentRow as HTMLElement).click();

        expect(mockSocket.emit).toHaveBeenCalledWith("terminal.init", { agent_id: "agent_0" });
        expect(document.getElementById("explorer-status")!.textContent).toContain("agent_0");
    });

    it("should create terminal and connect WebSocket on terminal.ready", async () => {
        const readyHandler = mockSocket.on.mock.calls.find(
            (c: unknown[]) => (c as string[])[0] === "terminal.ready",
        )![1];
        readyHandler({ agent_id: "agent_0" });

        await new Promise((resolve) => setTimeout(resolve, 50));

        const wsInstances = (window as any).WebSocket._instances;
        expect(wsInstances.length).toBeGreaterThan(0);
        expect(wsInstances[0].url).toBe("ws://localhost/terminal/agent_0");

        const container = document.getElementById("terminal-agent_0");
        expect(container).toBeDefined();
    });

    it("should keep bankrupt agents visible in the traders table with $0", () => {
        const logHandler = getLogHandler();

        logHandler({
            type: "state",
            round_num: 1,
            whale_wealth: 1000,
            assets: {},
            agents: { agent_0: { agent_id: "agent_0", wealth: 100 } },
        });
        expect(document.querySelector('tr[onclick*="agent_0"]')).not.toBeNull();

        // Agent goes bankrupt (removed from agents dict by orchestrator)
        logHandler({
            type: "state",
            round_num: 2,
            whale_wealth: 1100,
            assets: {},
            agents: {},
        });

        const agentRow = document.querySelector('tr[onclick*="agent_0"]');
        expect(agentRow).not.toBeNull();
        expect(agentRow!.textContent).toContain("$0");

        const agentTab = Array.from(document.querySelectorAll(".tab-button")).find(
            (btn) => btn.textContent === "agent_0",
        );
        expect(agentTab).toBeDefined();
    });

    it("should update state correctly across multiple rounds", () => {
        const logHandler = getLogHandler();

        logHandler({
            type: "state",
            round_num: 1,
            whale_wealth: 1000,
            liquidity_b: 100,
            assets: { cand_0: { type: "CANDIDATE", q_yes: 0, q_no: 0 } },
            agents: { agent_0: { agent_id: "agent_0", wealth: 100 } },
        });
        expect(document.getElementById("round-info")!.textContent).toContain("ROUND 1");
        expect(document.getElementById("tables")!.innerHTML).toContain("cand_0");

        logHandler({
            type: "state",
            round_num: 2,
            whale_wealth: 950,
            liquidity_b: 100,
            assets: { cand_0: { type: "CANDIDATE", q_yes: 50, q_no: 0 } },
            agents: { agent_0: { agent_id: "agent_0", wealth: 150 } },
        });
        expect(document.getElementById("round-info")!.textContent).toContain("ROUND 2");

        logHandler({
            type: "state",
            round_num: 3,
            whale_wealth: 900,
            liquidity_b: 100,
            assets: {
                cand_0: { type: "CANDIDATE", q_yes: 60, q_no: 0 },
                v_new: { type: "VERIFIER", q_yes: 10, q_no: 0 },
            },
            agents: { agent_0: { agent_id: "agent_0", wealth: 200 } },
        });
        expect(document.getElementById("round-info")!.textContent).toContain("ROUND 3");
        expect(document.getElementById("agents-table")!.innerHTML).toContain("$900");
        expect(document.getElementById("agents-table")!.innerHTML).toContain("$200");
    });
});
