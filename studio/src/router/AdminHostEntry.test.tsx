import { render, screen } from "@testing-library/react";
import { describe, expect, it, afterEach } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AdminHostEntry } from "./AdminHostEntry";

// বাংলা মন্তব্য: jsdom-এ window.location রিডঅনলি — api.test.ts-এর একই defineProperty প্যাটার্ন।
const setLocation = (hostname: string, pathname = "/") => {
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: { hostname, host: hostname, protocol: "https:", pathname },
  });
};

const ORIGINAL_LOCATION = window.location;

afterEach(() => {
  Object.defineProperty(window, "location", {
    configurable: true,
    writable: true,
    value: ORIGINAL_LOCATION,
  });
});

// Mirrors the real App.tsx wiring: AdminHostEntry wraps the route graph; on the
// admin host every stray route must LAND on /admin (not merely "not render").
function renderAt(initialPath: string, hostname: string) {
  setLocation(hostname, initialPath);
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/admin/*" element={<div data-testid="admin-landing">admin-console</div>} />
        <Route
          path="/login"
          element={
            <AdminHostEntry>
              <div data-testid="login-landing">login</div>
            </AdminHostEntry>
          }
        />
        <Route
          path="*"
          element={
            <AdminHostEntry>
              <div data-testid="child">child-content</div>
            </AdminHostEntry>
          }
        />
      </Routes>
    </MemoryRouter>
  );
}

describe("AdminHostEntry (#1468 admin portal host routing)", () => {
  it("is a transparent pass-through on the user portal host", () => {
    renderAt("/features", "supremeai-a.web.app");
    expect(screen.getByTestId("child")).toBeInTheDocument();
    expect(screen.queryByTestId("admin-landing")).not.toBeInTheDocument();
  });

  it("is a transparent pass-through on localhost (dev + jsdom default)", () => {
    renderAt("/", "localhost");
    expect(screen.getByTestId("child")).toBeInTheDocument();
  });

  it("lands the admin-host root on /admin", () => {
    renderAt("/", "supremeai-admin.web.app");
    expect(screen.getByTestId("admin-landing")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("lands stray user routes on the admin host on /admin", () => {
    renderAt("/features", "supremeai-admin.web.app");
    expect(screen.getByTestId("admin-landing")).toBeInTheDocument();
    expect(screen.queryByTestId("child")).not.toBeInTheDocument();
  });

  it("lets /login through on the admin host (guard chain needs it)", () => {
    renderAt("/login", "supremeai-admin.web.app");
    expect(screen.getByTestId("login-landing")).toBeInTheDocument();
  });
});
