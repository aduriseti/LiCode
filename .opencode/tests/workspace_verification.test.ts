import { describe, it, expect, onTestFinished } from "vitest";
import { spawn, ChildProcess } from "child_process";
import { chromium, Browser } from "playwright";

describe("Workspace Verification (Headless Browser)", () => {
    async function launchBrowser(): Promise<Browser> {
        return chromium.launch({
            headless: true,
            args: ["--disable-dev-shm-usage", "--disable-gpu", "--no-sandbox"],
        });
    }

    const testCases = [
        {
            name: "simple fibonacci prompt",
            prompt: "run a tournament with 1 agent for 2 rounds to implement a function that returns the nth fibonacci number. Set log level to INFO.",
            expectedContent: ["fibonacci", "def fib", "a, b = b, a + b"],
            timeout: 60000,
        },
        {
            name: "complex prompt with newlines and quotes",
            prompt: `run a tournament with 3 agents for 3 rounds to implement ' You are given an integer array nums and an integer k.

Your task is to partition nums into exactly k subarrays and return an integer denoting the minimum possible score among all valid partitions.

The score of a partition is the sum of the values of all its subarrays.

The value of a subarray is defined as sumArr * (sumArr + 1) / 2, where sumArr is the sum of its elements.' - use python`,
            expectedContent: [], // We just want to ensure it starts up and shows an agent tab
            timeout: 60000,
        },
    ];

    testCases.forEach(({ name, prompt, expectedContent, timeout }) => {
        it(
            `should handle ${name}`,
            async () => {
                let ocProcess: ChildProcess | null = null;
                let browser: Browser | null = null;
                let fullOutput = "";
                let exitCode: number | null = null;

                onTestFinished(async () => {
                    if (browser) await browser.close().catch(() => {});
                    if (ocProcess?.pid) {
                        try {
                            process.kill(-ocProcess.pid, "SIGKILL");
                        } catch (_e) {
                            /* ignore */
                        }
                    }
                });

                console.log(`[TEST] Spawning opencode for case: ${name}...`);

                ocProcess = spawn(
                    "/home/codespace/.opencode/bin/opencode",
                    ["run", "--print-logs", prompt],
                    {
                        cwd: "/workspaces/LiCode",
                        stdio: ["ignore", "pipe", "pipe"],
                        detached: true,
                        env: { ...process.env, TERM: "dumb" },
                    },
                );

                ocProcess.stdout?.on("data", (d) => (fullOutput += d.toString()));
                ocProcess.stderr?.on("data", (d) => (fullOutput += d.toString()));
                ocProcess.on("exit", (code) => {
                    exitCode = code;
                    console.log(
                        `[TEST] opencode process exited with code ${code} for case: ${name}`,
                    );
                });

                // Extract dashboard URL
                const dashboardUrl = await new Promise<string>((resolve, reject) => {
                    const checkInterval = setInterval(() => {
                        if (exitCode !== null && exitCode !== 0) {
                            clearInterval(checkInterval);
                            console.error(
                                `[TEST FAIL] Process exited early with code ${exitCode}. Full log output:\n${fullOutput}`,
                            );
                            reject(new Error(`Process exited early with code ${exitCode}.`));
                        }
                        const match = fullOutput.match(/\[DASHBOARD\] (http:\/\/[^\s]+)/);
                        if (match) {
                            clearInterval(checkInterval);
                            resolve(match[1]);
                        }
                    }, 500);

                    setTimeout(() => {
                        clearInterval(checkInterval);
                        console.error(
                            `[TEST FAIL] Dashboard URL not found within 30s. Full log output:\n${fullOutput}`,
                        );
                        reject(new Error(`Dashboard URL not found within 30s for prompt: ${name}`));
                    }, 30000);
                });

                console.log(`[TEST] Connecting to dashboard: ${dashboardUrl}`);

                browser = await launchBrowser();
                const page = await browser.newPage();

                page.on("crash", () => {
                    throw new Error("Dashboard page crashed in Chromium");
                });
                await page.goto(dashboardUrl, { waitUntil: "domcontentloaded", timeout: 20000 });

                // Wait for an agent terminal tab to appear (indicates success startup)
                try {
                    // If the process exits, we should stop waiting
                    const agentTab = (await Promise.race([
                        page.waitForSelector(".tab-button:not(#tab-system)", { timeout: 30000 }),
                        new Promise((_, reject) => {
                            const check = setInterval(() => {
                                if (exitCode !== null) {
                                    clearInterval(check);
                                    reject(
                                        new Error(
                                            `Tournament process exited with code ${exitCode} while waiting for agents.`,
                                        ),
                                    );
                                }
                            }, 500);
                        }),
                    ])) as any;

                    expect(agentTab).not.toBeNull();
                    if (expectedContent.length > 0) {
                        await agentTab!.click();
                    }
                } catch (_e) {
                    console.error(
                        `[TEST FAIL] Failure while waiting for agent tab (${name}). Full log output:\n${fullOutput}`,
                    );
                    throw _e;
                }

                // If we have expected content, verify it
                if (expectedContent.length > 0) {
                    await page.waitForSelector(".terminal-container.active .xterm-rows", {
                        timeout: 20000,
                    });

                    let terminalText = "";
                    const deadline = Date.now() + 30000;
                    while (Date.now() < deadline) {
                        terminalText = await page.evaluate(() => {
                            const rows = document.querySelector(
                                ".terminal-container.active .xterm-rows",
                            );
                            return rows ? rows.textContent || "" : "";
                        });
                        const lower = terminalText.toLowerCase();
                        if (expectedContent.some((s) => lower.includes(s.toLowerCase()))) {
                            break;
                        }
                        await page.waitForTimeout(2000);
                    }

                    const lower = terminalText.toLowerCase();
                    const found = expectedContent.some((s) => lower.includes(s.toLowerCase()));
                    if (!found) {
                        console.error(
                            `[TEST FAIL] Terminal content mismatch for case: ${name}. Full log output:\n${fullOutput}`,
                        );
                    }
                    expect(
                        found,
                        `Expected terminal to contain one of [${expectedContent}] but got: ${terminalText.substring(0, 200)}...`,
                    ).toBe(true);
                }
            },
            timeout,
        );
    });
});
