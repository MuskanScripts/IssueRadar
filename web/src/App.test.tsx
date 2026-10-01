import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";
import { brand } from "./lib/brand";
import { demo } from "./lib/demo";

describe("App shell in demo mode", () => {
  beforeEach(() => {
    document.documentElement.removeAttribute("data-theme");
    window.localStorage.clear();
  });

  it("labels the data as demo data", () => {
    render(<App />);
    expect(screen.getByText(brand.demo_label)).toBeInTheDocument();
  });

  it("lists only free and likely-free issues", () => {
    render(<App />);
    const list = screen.getByRole("list", { name: /free issues/i });
    const rankable = demo.issues.filter((i) => i.availability === "free" || i.availability === "likely_free");
    expect(within(list).getAllByRole("listitem")).toHaveLength(rankable.length);
    expect(screen.queryByText("Typo in the error message for missing tools")).not.toBeInTheDocument();
  });

  it("shows level as three dots with an accessible name", () => {
    render(<App />);
    expect(screen.getAllByRole("img", { name: "Level: Beginner" }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("img", { name: "Level: Pro" }).length).toBeGreaterThan(0);
  });

  it("switches theme from the keyboard", async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("radio", { name: "Dark" }));
    expect(document.documentElement).toHaveAttribute("data-theme", "dark");
    await user.click(screen.getByRole("radio", { name: "System" }));
    expect(document.documentElement).not.toHaveAttribute("data-theme");
  });

  it("shows the API budget in the footer", () => {
    render(<App />);
    expect(screen.getByText(/API budget used/)).toBeInTheDocument();
  });
});
