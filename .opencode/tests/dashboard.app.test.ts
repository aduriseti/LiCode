import { describe, it, expect, vi } from "vitest";
import { createDashboardApp } from "../plugins/dashboard.app";
import request from "supertest";

describe("Dashboard App", () => {
  it("should serve the dashboard HTML on the root route", async () => {
    const { app } = createDashboardApp();
    const response = await request(app).get("/");
    expect(response.status).toBe(200);
    expect(response.text).toContain("Logical Induction Market");
  });

  it("should have a socket.io server attached", () => {
    const { io } = createDashboardApp();
    expect(io).toBeDefined();
    expect(typeof io.emit).toBe("function");
  });
});
