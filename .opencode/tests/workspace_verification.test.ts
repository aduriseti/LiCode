import { describe, it, expect, afterEach } from "vitest";
import { spawn, execSync, ChildProcess } from "child_process";
import { chromium, Browser, Page } from "playwright";

describe("Workspace Verification (Headless Browser)", () => {
    let ocProcess: ChildProcess | null = null;
    let browser: Browser | null = null;

    afterEach(async () => {
        if (browser) await browser.close().catch(() => {});
        if (ocProcess?.pid) {
            try { process.kill(-ocProcess.pid, "SIGKILL"); } catch (e) {}
        }
        // Kill any orphaned opencode serve processes spawned by the tournament
        try { execSync("pkill -f 'opencode serve' 2>/dev/null || true"); } catch (e) {}
    });

    async function launchBrowser(): Promise<Browser> {
        return chromium.launch({
            headless: true,
            args: [
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-sandbox",
            ],
        });
    }

    it("should show fibonacci code in the dashboard terminal", async () => {
        ocProcess = spawn(
            "/home/codespace/.opencode/bin/opencode",
            ["run", "--print-logs", "run a tournament with 1 agent for 2 rounds to implement a function that returns the nth fibonacci number. Set log level to INFO."],
            {
                cwd: "/workspaces/LiCode",
                stdio: ["ignore", "pipe", "pipe"],
                detached: true,
                env: { ...process.env, TERM: "dumb" }
            }
        );

        // Extract dashboard URL from --print-logs output
        // client.app.log messages appear as: INFO ... service=tournament-tool [DASHBOARD] http://...
        const dashboardUrl = await new Promise<string>((resolve, reject) => {
            const timeout = setTimeout(() => reject(new Error("Dashboard URL not found in output within 60s")), 60000);
            let buf = "";
            const scan = (chunk: Buffer) => {
                buf += chunk.toString();
                const match = buf.match(/\[DASHBOARD\] (http:\/\/[^\s]+)/);
                if (match) {
                    clearTimeout(timeout);
                    resolve(match[1]);
                }
            };
            ocProcess!.stdout!.on("data", scan);
            ocProcess!.stderr!.on("data", scan);
        });

        browser = await launchBrowser();
        const page = await browser.newPage();
        page.on("crash", () => { throw new Error("Dashboard page crashed in Chromium"); });
        await page.goto(dashboardUrl, { waitUntil: "domcontentloaded", timeout: 30000 });

        // Wait for an agent terminal tab (not the SYSTEM tab) to appear
        const agentTab = await page.waitForSelector(".tab-button:not(#tab-system)", { timeout: 90000 });
        expect(agentTab).not.toBeNull();
        await agentTab!.click();

        // Wait for xterm.js rows to render in the active terminal
        await page.waitForSelector(".terminal-container.active .xterm-rows", { timeout: 30000 });

        // Poll until fibonacci content appears in the terminal
        let terminalText = "";
        const deadline = Date.now() + 90000;
        while (Date.now() < deadline) {
            terminalText = await page.evaluate(() => {
                const rows = document.querySelector(".terminal-container.active .xterm-rows");
                return rows ? rows.textContent || "" : "";
            });
            const lower = terminalText.toLowerCase();
            if (lower.includes("fibonacci") || lower.includes("def fib") || lower.includes("a, b = b, a + b")) {
                break;
            }
            await page.waitForTimeout(2000);
        }

        const lower = terminalText.toLowerCase();
        expect(
            lower.includes("fibonacci") || lower.includes("def fib") || lower.includes("a, b = b, a + b"),
            `Expected fibonacci content in terminal. Got ${terminalText.length} chars: ${terminalText.substring(0, 200)}`
        ).toBe(true);
    }, 180000);
});
