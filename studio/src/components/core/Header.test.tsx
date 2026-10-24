import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { Header } from "./Header";

describe("Header component", () => {
  it("renders title, role toggle pills, and swarm radar", () => {
    render(
      <MemoryRouter initialEntries={["/workspace"]}>
        <Header
          title="SupremeAI Studio"
          onToggleSidebar={() => {}}
          onToggleTheme={() => {}}
          theme="dark"
        />
      </MemoryRouter>
    );

    expect(screen.getByText("SupremeAI Studio")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "User" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Admin" })).toBeInTheDocument();
    expect(screen.getByTestId("swarm-radar")).toHaveTextContent("Swarm Online");
  });

  it("triggers search event when Search button is clicked", () => {
    const dispatchSpy = vi.spyOn(window, "dispatchEvent");
    render(
      <MemoryRouter initialEntries={["/admin"]}>
        <Header
          title="SupremeAI Studio"
          onToggleSidebar={() => {}}
          onToggleTheme={() => {}}
          theme="dark"
        />
      </MemoryRouter>
    );

    const searchBtn = screen.getByLabelText("Search");
    fireEvent.click(searchBtn);

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: "supremeai-open-command-palette" })
    );
    dispatchSpy.mockRestore();
  });
});
