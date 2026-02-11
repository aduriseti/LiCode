import { describe, it, expect } from "vitest";
import { execSync } from "child_process";

describe("Opencode Runtime Load Verification", () => {
    it("should load plugins without TypeError: Cannot call a class constructor without |new|", () => {
        const opencodeBin = "/home/codespace/.opencode/bin/opencode";
        
        try {
            // We run a simple command that triggers plugin loading.
            execSync(`${opencodeBin} run "ping" --print-logs --log-level DEBUG`, {
                stdio: 'pipe',
                env: { ...process.env, OPENCODE_API_KEY: "fake" }
            });
            // If execSync doesn't throw, it exited with code 0.
        } catch (error: unknown) {
            const execError = error as { status?: number, stdout?: Buffer, stderr?: Buffer };
            const stderr = execError.stderr?.toString() || "";
            const stdout = execError.stdout?.toString() || "";
            const fullOutput = stdout + stderr;
            
            if (fullOutput.includes("Cannot call a class constructor without |new|")) {
                throw new Error("Regression Detected: Class constructor called without 'new' in Opencode runtime!");
            }
            
            // If it's a TypeError, we fail regardless of the exit code.
            if (fullOutput.includes("TypeError")) {
                 throw new Error(`Regression Detected: TypeError in Opencode runtime: ${fullOutput}`);
            }

            // If it loaded plugins, we consider it a structural success for this test
            if (fullOutput.includes("loading plugin")) {
                return; 
            }
            
            // If it reached the point of trying to run but failed due to auth/network (code 1), that's fine
            if (execError.status === 1 && fullOutput.includes("service=default")) {
                return;
            }

            throw error;
        }
    }, 30000); // 30s timeout for real binary run
});
