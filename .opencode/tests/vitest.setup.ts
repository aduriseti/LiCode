import { vi } from "vitest";

// Globally mock the 'open' library to prevent real windows from opening in ANY test
vi.mock("open", () => ({
  default: vi.fn().mockResolvedValue(undefined)
}));

// Add any other global browser mocks here if needed
