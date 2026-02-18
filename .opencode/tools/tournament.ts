import { tool } from "@opencode-ai/plugin"
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

export default tool({
  description: "Spawns N parallel agents in git worktrees and runs an adversarial market to find the best code.",
  args: {
    prompt: tool.schema.string().describe("The coding task"),
    count: tool.schema.number().default(3),
  },
  async execute({ prompt, count }) {
    const timestamp = Date.now();
    console.log(`Starting tournament with ${count} participants...`);

    // 1. Create N sandboxed worktrees
    const sandboxes: string[] = [];
    try {
        // We do this sequentially or use a loop to ensure we capture the paths correctly
        // Promise.all is fine but we need to make sure the loop index corresponds to the directory
        const promises = Array.from({ length: count }).map(async (_, i) => {
            const path = `./.arenas/sandbox_${timestamp}_${i}`;
            // Use -b to create a new branch.
            // git worktree add <path> <branch>
            const cmd = `git worktree add ${path} -b arena_${timestamp}_${i}`;
            await execAsync(cmd);
            return path;
        });
        
        const paths = await Promise.all(promises);
        sandboxes.push(...paths);

    } catch (e: any) {
        return `Failed to create sandboxes: ${e.message}`;
    }

    // 2. RUN GENERATORS IN PARALLEL
    console.log("⚔️ Spawning Agents...");
    // We assume 'opencode' is in the PATH.
    await Promise.all(sandboxes.map(s => 
        execAsync(`cd ${s} && opencode run --temp 1.0 "${prompt}"`)
            .catch(e => console.error(`Agent in ${s} failed: ${e.message}`))
    ));

    // 3. RUN ADVERSARIAL VALIDATORS
    const results = await Promise.all(sandboxes.map(async s => {
        try {
            const { stdout } = await execAsync(`python3 ./scripts/market_verify.py ${s}/main.py`);
            return stdout.trim();
        } catch (e: any) {
            // Check if it's a file not found error vs script error
            return `Validation failed for ${s}: ${e.message}`;
        }
    }));

    return `Tournament Complete. Results:\n${results.join('\n')}`;
  }
})
