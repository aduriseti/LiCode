import { describe, it, expect, mock } from "bun:test";

// Mock child_process before importing the tool if possible, or just test the logic that doesn't run exec immediately
// Since default export is the tool definition, we can inspect its properties without running it.

import tournamentTool from "../tools/tournament";

describe("Tournament Tool Definition", () => {
  it("should have correct name and description", () => {
    expect(tournamentTool.description).toContain("Logical Induction Market");
    expect(tournamentTool.description).toContain("ALWAYS use 'opencode'");
  });

  it("should have correct arguments", () => {
    const args = tournamentTool.args;
    expect(args.prompt).toBeDefined();
    expect(args.rounds).toBeDefined();
    expect(args.agents).toBeDefined();
    expect(args.model).toBeDefined();
    expect(args.provider).toBeDefined();
  });
  
  // Testing the execute function requires mocking execAsync which is internal to the module.
  // In a real setup we'd use a rewiring tool or dependency injection.
  // For now, this verifies the schema definition which was the source of the crash.
});
