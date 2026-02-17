import { describe, it, expect, vi, beforeEach } from "vitest";
import { JSDOM, DOMWindow } from "jsdom";
import fs from "fs";
import path from "path";

interface MockSocket {
    on: ReturnType<typeof vi.fn>;
    emit: ReturnType<typeof vi.fn>;
}

describe("Dashboard New Features UI", () => {
    let dom: JSDOM;
    let window: DOMWindow & { [key: string]: unknown };
    let document: Document;
    let mockSocket: MockSocket;

    beforeEach(async () => {
        let html = fs.readFileSync(path.join(__dirname, "../plugins/dashboard.html"), "utf8");
        // Strip scripts to avoid external network calls during JSDOM execution
        html = html.replace(/<script src="https:\/\/cdn.tailwindcss.com"><\/script>/, "");
        html = html.replace(/<script src="https:\/\/cdn.jsdelivr.net\/npm\/chart.js"><\/script>/, "");
        html = html.replace('<script src="/socket.io/socket.io.js"></script>', "");
        html = html.replace(/<link.*xterm.min.css.*>/, "");
        html = html.replace(/<script.*xterm.min.js.*><\/script>/, "");
        html = html.replace(/<script.*fit.min.js.*><\/script>/, "");

        mockSocket = { on: vi.fn(), emit: vi.fn() };

        dom = new JSDOM(html, {
            runScripts: "dangerously",
            resources: "usable",
            url: "http://localhost",
            beforeParse(window) {
                (window as any).io = () => mockSocket;

                // Mock Chart.js
                const MockChart = function () {
                    return { data: { labels: [], datasets: [] }, update: vi.fn(), destroy: vi.fn() };
                };
                (MockChart as any).defaults = { font: {}, plugins: {}, elements: {}, scales: {} };
                (window as any).Chart = MockChart;

                // Mock Xterm.js
                (window as any).Terminal = function () {
                    return {
                        loadAddon: vi.fn(), open: vi.fn(), onData: vi.fn(),
                        write: vi.fn(), clear: vi.fn(), reset: vi.fn(),
                        focus: vi.fn(), refresh: vi.fn(), cols: 80, rows: 24
                    };
                };
                (window as any).FitAddon = { FitAddon: function () { return { fit: vi.fn() }; } };

                // Mock WebSocket
                const MockWebSocket = function (this: any, url: string) {
                    this.url = url; this.send = vi.fn(); this.close = vi.fn();
                    this.readyState = 1; this.onopen = null; this.onmessage = null; this.onclose = null;
                    setTimeout(() => { if (this.onopen) this.onopen(); }, 0);
                } as any;
                MockWebSocket.OPEN = 1;
                (window as any).WebSocket = MockWebSocket;

                (window as any).requestAnimationFrame = (cb: () => void) => setTimeout(cb, 0);
                window.HTMLCanvasElement.prototype.getContext = vi.fn(() => ({ measureText: () => ({ width: 0 }) })) as any;
                
                // Polyfill some things JSDOM might lack for this test
                window.dispatchEvent = vi.fn(window.dispatchEvent.bind(window));
            }
        });
        window = dom.window as unknown as typeof window;
        document = window.document;
        // Wait for script initialization
        await new Promise(resolve => setTimeout(resolve, 200));
    });

    it("should start with System tab selected", () => {
        const systemTab = document.getElementById("tab-system");
        expect(systemTab?.classList.contains("active")).toBe(true);
        
        const systemPane = document.getElementById("terminal-system");
        expect(systemPane?.classList.contains("active")).toBe(true);
    });

    it("should switch between System and Agent tabs", async () => {
        // 1. Initial state: System active
        expect(document.getElementById("tab-system")?.classList.contains("active")).toBe(true);

        // 2. Add an agent via state update
        const logHandler = mockSocket.on.mock.calls.find((c: any[]) => c[0] === 'log')![1];
        logHandler({
            type: "state", round_num: 1, whale_wealth: 1000, assets: {},
            agents: { "agent_0": { agent_id: "agent_0", wealth: 100 } }
        });
        await new Promise(resolve => setTimeout(resolve, 50));

        // 3. Find agent tab and click it
        const agentTabs = Array.from(document.querySelectorAll('.tab-button')).filter(btn => btn.textContent === 'agent_0');
        expect(agentTabs.length).toBe(1);
        (agentTabs[0] as HTMLElement).click();

        // 4. Verify agent tab active, system tab inactive
        expect(document.getElementById("tab-system")?.classList.contains("active")).toBe(false);
        expect(agentTabs[0].classList.contains("active")).toBe(true);
        expect(document.getElementById("terminal-agent_0")?.classList.contains("active")).toBe(true);
        expect(document.getElementById("terminal-system")?.classList.contains("active")).toBe(false);

        // 5. Switch back to system
        (document.getElementById("tab-system") as HTMLElement).click();
        expect(document.getElementById("tab-system")?.classList.contains("active")).toBe(true);
        expect(agentTabs[0].classList.contains("active")).toBe(false);
    });

    it("should have resizers in the DOM", () => {
        expect(document.getElementById("top-v-resizer")).not.toBeNull();
        expect(document.getElementById("main-h-resizer")).not.toBeNull();
    });

    it("should update layout on vertical resizer drag", () => {
        const vResizer = document.getElementById("top-v-resizer") as HTMLElement;
        const chartPane = document.getElementById("chart-pane") as HTMLElement;
        
        // Mock clientX for drag event
        const mouseDown = new window.MouseEvent('mousedown', { bubbles: true });
        vResizer.dispatchEvent(mouseDown);

        const mouseMove = new window.MouseEvent('mousemove', { 
            bubbles: true,
            clientX: window.innerWidth * 0.3 // Drag to 30%
        });
        document.dispatchEvent(mouseMove);

        const mouseUp = new window.MouseEvent('mouseup', { bubbles: true });
        document.dispatchEvent(mouseUp);

        expect(chartPane.style.width).toBe("30%");
        expect(window.dispatchEvent).toHaveBeenCalled(); // Should trigger resize event
    });

    it("should update layout on horizontal resizer drag", () => {
        const hResizer = document.getElementById("main-h-resizer") as HTMLElement;
        const topPane = document.getElementById("top-pane") as HTMLElement;
        
        // Mock clientY for drag event
        const mouseDown = new window.MouseEvent('mousedown', { bubbles: true });
        hResizer.dispatchEvent(mouseDown);

        // Need to account for header height in the logic
        const header = document.querySelector('header') as HTMLElement;
        // Mock offsetHeight
        Object.defineProperty(header, 'offsetHeight', { value: 50 });

        const mouseMove = new window.MouseEvent('mousemove', { 
            bubbles: true,
            clientY: 50 + (window.innerHeight - 50) * 0.4 // Drag to 40% of remaining height
        });
        document.dispatchEvent(mouseMove);

        const mouseUp = new window.MouseEvent('mouseup', { bubbles: true });
        document.dispatchEvent(mouseUp);

        expect(topPane.style.height).toBe("40%");
        expect(window.dispatchEvent).toHaveBeenCalled();
    });
});
