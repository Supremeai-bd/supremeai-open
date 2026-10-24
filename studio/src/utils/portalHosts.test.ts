import { describe, expect, it } from "vitest";
import { ADMIN_HOSTS, isAdminHost } from "./portalHosts";

describe("portalHosts (#1468)", () => {
  it("recognizes the built-in admin hosting target", () => {
    expect(ADMIN_HOSTS).toContain("supremeai-admin.web.app");
    expect(isAdminHost("supremeai-admin.web.app")).toBe(true);
  });

  it("treats the user portal and localhost as non-admin", () => {
    expect(isAdminHost("supremeai-a.web.app")).toBe(false);
    expect(isAdminHost("localhost")).toBe(false);
    expect(isAdminHost("supremeai-studio.vercel.app")).toBe(false);
  });

  it("is SSR-safe — no window and no hostname means non-admin", () => {
    expect(isAdminHost()).toBe(false);
  });

  it("is false for near-miss hostnames (no sloppy suffix matching)", () => {
    expect(isAdminHost("fake-supremeai-admin.web.app")).toBe(false);
    expect(isAdminHost("supremeai-admin.web.app.evil.example.com")).toBe(false);
  });
});
