import { describe, it, expect, afterEach } from "vitest";
import { spawn, ChildProcess } from "child_process";
import { chromium, Browser } from "playwright";

describe("Workspace Verification (Headless Browser)", () => {
    let ocProcess: ChildProcess | null = null;
    let browser: Browser | null = null;

    afterEach(async () => {
        if (browser) await browser.close().catch(() => {});
        if (ocProcess?.pid) {
            try { process.kill(-ocProcess.pid, "SIGKILL"); } catch (e) {}
        }
    });

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

        // Extract dashboard URL from output
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

        // Open dashboard in headless Chromium
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage();
        await page.goto(dashboardUrl, { waitUntil: "networkidle", timeout: 30000 });

        // Wait for a terminal tab and click it
        await page.waitForSelector(".tab-button", { timeout: 60000 });
        const firstTab = await page.$(".tab-button");
        expect(firstTab).not.toBeNull();
        await firstTab!.click();

        // Wait for xterm.js rows to appear
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
