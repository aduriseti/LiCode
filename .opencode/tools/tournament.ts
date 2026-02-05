import { tool } from "@opencode-ai/plugin"
import { spawn } from "child_process";
import fs from "fs/promises";

export default tool({
  description: "Runs a Logical Induction Market tournament. ALWAYS use 'opencode' provider and 'gemini-3-flash' model to utilize available credits.",
  args: {
    prompt: tool.schema.string().describe("The coding task"),
    rounds: tool.schema.number().default(2),
    agents: tool.schema.number().default(3),
    model: tool.schema.string().default("gemini-3-flash").describe("The LLM model ID. Defaults to 'gemini-3-flash'."),
    provider: tool.schema.string().default("opencode").describe("The LLM provider ID. MUST be 'opencode' to use credits."),
    target_file: tool.schema.string().optional().describe("Optional: Path to an existing file to refactor/fix."),
    log_level: tool.schema.string().default("ERROR").describe("Logging level (DEBUG, INFO, WARNING, ERROR). Defaults to ERROR."),
    timeout: tool.schema.number().default(300.0).describe("Timeout for each agent's response in seconds. Increase for complex tasks.")
  },
  async execute({ prompt, rounds, agents, model, provider, target_file, log_level, timeout }) {
    console.log(`Starting tournament for: "${prompt}" (Log Level: ${log_level})`);
    
    return new Promise((resolve, reject) => {
        const env = { 
            ...process.env, 
            OPENCODE_API_KEY: process.env.OPENCODE,
            FORCE_COLOR: '1',
            PYTHONUNBUFFERED: '1'
        };
        
        const args = [
            "-m", "market.cli",
            "--log-level", log_level,
            "run",
            "--prompt", prompt,
            "--rounds", String(rounds),
            "--agents", String(agents),
            "--model", model,
            "--provider", provider,
            "--timeout", String(timeout)
        ];
        
        if (target_file) {
            args.push("--target-file", target_file);
        }

        // Use spawn for streaming
        const child = spawn("python3", args, { env });

        let stdoutBuffer = "";
        let stderrBuffer = "";

        // Stream stderr (UI) to console immediately
        child.stderr.on("data", (data) => {
            process.stderr.write(data);
            stderrBuffer += data.toString();
        });

        // Collect stdout (JSON State)
        child.stdout.on("data", (data) => {
            stdoutBuffer += data.toString();
        });

                child.on("close", async (code) => {

                    if (code !== 0) {

                        resolve(`Market crashed (Exit Code ${code}):\n${stderrBuffer}`);

                        return;

                    }

        

                    try {

                        const result = JSON.parse(stdoutBuffer.trim());

                        // The CLI now returns { state: ..., report: "..." }

                        resolve(result.report || "Tournament finished but no report was generated.");

                        

                    } catch (e: any) {

                        resolve(`Tournament ran, but output parsing failed: ${e.message}\nOutput start: ${stdoutBuffer.substring(0, 100)}...`);

                    }

                });

        child.on("error", (err) => {
            resolve(`Failed to start market process: ${err.message}`);
        });
    });
  }
})