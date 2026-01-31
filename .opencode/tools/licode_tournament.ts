import { tool } from "@opencode-ai/plugin";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

export default tool({
  description: "Runs the LiCode tournament to facilitate a logical induction market for code generation.",
  args: {
    prompt: tool.schema.string().describe("The coding task prompt for the agents."),
    count: tool.schema.number().describe("Number of agents to spawn.").default(3),
    budget: tool.schema.number().describe("Total budget for the tournament.").default(1000.0),
    rounds: tool.schema.number().describe("Number of rounds to run.").default(5),
  },
  async execute({ prompt, count, budget, rounds }) {
    const cmd = `python3 -m licode.cli "${prompt}" --count ${count} --budget ${budget} --rounds ${rounds}`;
    try {
        const { stdout, stderr } = await execAsync(cmd);
        if (stderr) {
            console.error(stderr);
        }
        return stdout;
    } catch (e: any) {
        return `Error executing tournament: ${e.message}\nStderr: ${e.stderr}`;
    }
  }
});
