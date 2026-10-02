import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { App } from "./App";
import { resetDemo } from "./lib/demo-source";
import { demo } from "./lib/demo";

describe("dashboard in demo mode", () => {
  beforeEach(() => {
    window.localStorage.clear();
    resetDemo();
    document.documentElement.removeAttribute("data-theme");
  });

  it("shows the demo label and the free issues", async () => {
    render(<App demo initialPath="/" />);
    expect(screen.getByText("Demo data")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: /issues, best match first/i });
    const free = demo.issues.filter((i) => i.availability === "free" || i.availability === "likely_free");
    await waitFor(() => expect(within(list).getAllByRole("listitem").length).toBeGreaterThan(0));
    expect(within(list).getAllByRole("listitem").length).toBeLessThanOrEqual(free.length);
    expect(screen.queryByText("Typo in the error message for missing tools")).not.toBeInTheDocument();
  });

  it("opens the drawer from the keyboard and shows the reasons", async () => {
    const user = userEvent.setup();
    render(<App demo initialPath="/" />);
    await screen.findByRole("list", { name: /issues, best match first/i });
    await user.keyboard("j");
    await user.keyboard("o");
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Why it is free (or not)")).toBeInTheDocument();
    expect(within(dialog).getByText("Before you start")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("filters instantly", async () => {
    const user = userEvent.setup();
    render(<App demo initialPath="/" />);
    await screen.findByRole("list", { name: /issues, best match first/i });
    await user.click(screen.getByRole("button", { name: "Pro" }));
    const list = screen.getByRole("list", { name: /issues, best match first/i });
    for (const item of within(list).getAllByRole("listitem")) {
      expect(within(item).getByRole("img", { name: "Level: Pro" })).toBeInTheDocument();
    }
  });

  it("navigates to every page", async () => {
    const user = userEvent.setup();
    render(<App demo initialPath="/" />);
    for (const [link, heading] of [
      ["Repos", "Repos"],
      ["My PRs", "My pull requests"],
      ["Profile", "Profile"],
      ["Digest", "Digest"],
      ["Insights", "Insights"],
      ["Settings", "Settings"],
    ]) {
      await user.click(screen.getByRole("link", { name: link }));
      expect(await screen.findByRole("heading", { level: 1, name: heading })).toBeInTheDocument();
    }
  });

  it("shows a nudge draft on the PR board", async () => {
    render(<App demo initialPath="/prs" />);
    expect(await screen.findByText("Nudge draft")).toBeInTheDocument();
    expect(screen.getByText(/Nothing is posted for you/)).toBeInTheDocument();
  });

  it("opens the command palette with Ctrl+K", async () => {
    const user = userEvent.setup();
    render(<App demo initialPath="/" />);
    await user.keyboard("{Control>}k{/Control}");
    const palette = await screen.findByRole("dialog");
    await user.type(within(palette).getByRole("combobox"), "insights");
    await user.keyboard("{Enter}");
    expect(await screen.findByRole("heading", { level: 1, name: "Insights" })).toBeInTheDocument();
  });

  it("explains how to start when the API is not running", async () => {
    vi.spyOn(globalThis, "fetch").mockRejectedValue(new TypeError("failed"));
    render(<App demo={false} initialPath="/" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("firstpr serve");
    expect(screen.getByRole("button", { name: /demo mode instead/i })).toBeInTheDocument();
    vi.restoreAllMocks();
  });
});
