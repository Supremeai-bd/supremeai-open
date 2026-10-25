import { describe, expect, it } from "vitest";
import { ADMIN_HOSTS, isAdminHost } from "./portalHosts";

describe("portalHosts (#1468)", () => {
  it("has no hardcoded legacy web.app admin hosts (Zero-Firebase)", () => {
    expect(ADMIN_HOSTS).not.toContain("supremeai-admin.web.app");
    expect(isAdminHost("supremeai-admin.web.app")).toBe(false);
  });

  it("treats the public portal and localhost as non-admin", () => {
    expect(isAdminHost("supremeai-studio.pages.dev")).toBe(false);
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
