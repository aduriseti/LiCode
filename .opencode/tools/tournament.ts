import { tool } from "@opencode-ai/plugin"
import { exec } from "child_process";
import { promisify } from "util";
import fs from "fs/promises";
import path from "path";

const execAsync = promisify(exec);

export default tool({
  description: "Runs a Logical Induction Market tournament.",
  args: {
    prompt: tool.schema.string().describe("The coding task"),
    rounds: tool.schema.number().default(5),
  },
  async execute({ prompt, rounds }) {
    const workDir = path.resolve("./.arenas/market_run_" + Date.now());
    await fs.mkdir(workDir, { recursive: true });
    
    const statePath = path.join(workDir, "state.json");
    const actionsPath = path.join(workDir, "actions.json");
    
    // 1. INIT
    try {
        const { stdout } = await execAsync(`python3 -m market.cli init --prompt "${prompt}" --agents 3`);
        await fs.writeFile(statePath, stdout);
        console.log("Market Initialized.");
    } catch (e: any) {
        return `Init failed: ${e.message}`;
    }

    // 2. LOOP
    let history = [];
    for (let i = 0; i < rounds; i++) {
        console.log(`--- Round ${i+1} ---`);
        
        // A. Read State
        const stateStr = await fs.readFile(statePath, "utf-8");
        const state = JSON.parse(stateStr);
        
        // B. Simulate Agents (In real version, we'd prompt LLMs here)
        const actions = [];
        for (const aid in state.agents) {
            // Randomish belief updates to simulate trading
            const belief = 0.5 + (Math.random() - 0.5) * 0.2; // 0.4 to 0.6
            actions.push({
                agent_id: aid,
                beliefs: { [`cand_0`]: belief } 
            });
        }
        await fs.writeFile(actionsPath, JSON.stringify(actions));
        
        // C. Step Market
        try {
            const cmd = `python3 -m market.cli step --state ${statePath} --actions ${actionsPath}`;
            const { stdout, stderr } = await execAsync(cmd);
            
            // Stream the pretty summary from stderr to the terminal
            if (stderr) console.log(stderr);
            
            await fs.writeFile(statePath, stdout);
            
            // Log summary for final history
            const newState = JSON.parse(stdout);
            history.push(`Round ${newState.round_num}: Price(cand_0) = ${newState.assets["cand_0"] ? newState.assets["cand_0"].q_yes : "?"}`);
            
        } catch (e: any) {
            return `Step failed at round ${i}: ${e.message}`;
        }
    }

    return `Tournament Complete.\nHistory:\n${history.join('\n')}`;
  }
})