import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Sidebar } from "../components/Sidebar";

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// BF-01: Sidebar fetches snapshot list from GET /api/snapshots and renders it
// BF-07: Changing resource type filter triggers graph API re-fetch  (via onFilterChange)
// BF-10: TB/LR layout toggle calls onRankdirChange with correct rankdir
describe("Sidebar", () => {
  it("fetches and renders snapshot list (BF-01)", async () => {
    render(
      <Sidebar
        selectedSnapshotId={null}
        onSnapshotSelect={() => {}}
        onFilterChange={() => {}}
        onRankdirChange={() => {}}
        rankdir="TB"
      />,
      { wrapper }
    );

    // Loading state
    expect(screen.getByText(/loading/i)).toBeInTheDocument();

    // After data loads
    await waitFor(() => {
      expect(screen.getByText("snap-001")).toBeInTheDocument();
    });
    expect(screen.getByText("snap-002")).toBeInTheDocument();
  });

  it("calls onSnapshotSelect when a snapshot is clicked", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();

    render(
      <Sidebar
        selectedSnapshotId={null}
        onSnapshotSelect={onSelect}
        onFilterChange={() => {}}
        onRankdirChange={() => {}}
        rankdir="TB"
      />,
      { wrapper }
    );

    await waitFor(() => screen.getByText("snap-001"));
    await user.click(screen.getByText("snap-001"));
    expect(onSelect).toHaveBeenCalledWith("snap-001");
  });

  it("calls onFilterChange when resource type filter changes (BF-07)", async () => {
    const user = userEvent.setup();
    const onFilterChange = vi.fn();

    render(
      <Sidebar
        selectedSnapshotId="snap-001"
        onSnapshotSelect={() => {}}
        onFilterChange={onFilterChange}
        onRankdirChange={() => {}}
        rankdir="TB"
      />,
      { wrapper }
    );

    // Wait for resource type options to load (not just the combobox itself)
    await waitFor(() =>
      screen.getByRole("option", { name: "AWS::EC2::Instance" })
    );
    const select = screen.getByRole("combobox");
    await user.selectOptions(select, "AWS::EC2::Instance");
    expect(onFilterChange).toHaveBeenCalledWith("AWS::EC2::Instance");
  });

  it("calls onRankdirChange with LR when LR button is clicked (BF-10)", async () => {
    const user = userEvent.setup();
    const onRankdirChange = vi.fn();

    render(
      <Sidebar
        selectedSnapshotId={null}
        onSnapshotSelect={() => {}}
        onFilterChange={() => {}}
        onRankdirChange={onRankdirChange}
        rankdir="TB"
      />,
      { wrapper }
    );

    const lrBtn = screen.getByRole("button", { name: /LR/i });
    await user.click(lrBtn);
    expect(onRankdirChange).toHaveBeenCalledWith("LR");
  });

  it("calls onRankdirChange with TB when TB button is clicked (BF-10)", async () => {
    const user = userEvent.setup();
    const onRankdirChange = vi.fn();

    render(
      <Sidebar
        selectedSnapshotId={null}
        onSnapshotSelect={() => {}}
        onFilterChange={() => {}}
        onRankdirChange={onRankdirChange}
        rankdir="LR"
      />,
      { wrapper }
    );

    const tbBtn = screen.getByRole("button", { name: /TB/i });
    await user.click(tbBtn);
    expect(onRankdirChange).toHaveBeenCalledWith("TB");
  });
});


