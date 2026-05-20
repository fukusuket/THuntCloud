import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AwsGroupNode } from "../components/AwsGroupNode";
import { RankDirContext } from "../components/RankDirContext";
import { CollapseContext } from "../components/CollapseContext";

// Mock reactflow: Handle requires zustand provider context, which is unavailable in isolation
vi.mock("reactflow", () => ({
  Handle: ({ type, position }: { type: string; position: string }) => (
    <div data-testid={`handle-${type}-${position}`} />
  ),
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
}));

// BF-11: AwsGroupNode renders with dashed border and label
describe("AwsGroupNode", () => {
  const props = {
    id: "vpc-123",
    data: {
      resource_id: "vpc-123",
      resource_type: "AWS::EC2::VPC",
      resource_name: "my-vpc",
      aws_region: "us-east-1",
      is_container: true,
    },
    selected: false,
  };

  it("renders with the resource name as label", () => {
    render(<AwsGroupNode {...props} />);
    expect(screen.getByText("my-vpc")).toBeInTheDocument();
  });

  it("renders with dashed border style", () => {
    render(<AwsGroupNode {...props} />);
    const container = screen.getByTestId("aws-group-node");
    // Tailwind border-dashed or inline style with dashed border
    expect(container.className).toMatch(/dashed|group-node/i);
  });

  it("falls back to resource_id when resource_name is null", () => {
    render(
      <AwsGroupNode
        {...props}
        data={{ ...props.data, resource_name: null }}
      />
    );
    expect(screen.getByText("vpc-123")).toBeInTheDocument();
  });

  it("renders the resource type", () => {
    render(<AwsGroupNode {...props} />);
    expect(screen.getByText(/AWS::EC2::VPC/i)).toBeInTheDocument();
  });

  it("renders as a container (has handles for connections)", () => {
    render(<AwsGroupNode {...props} />);
    // Container node must still mount without errors
    expect(screen.getByTestId("aws-group-node")).toBeInTheDocument();
  });

  // Fix: container div must fill its React Flow wrapper so that children
  // nodes (Subnet, NetworkACL, etc.) rendered within the wrapper appear
  // visually inside the VPC / group border.  Without width/height 100% the
  // visual dashed rectangle stays at its minWidth/minHeight while dagre sets
  // a much larger wrapper size, pushing children outside the border.
  it("root div has width 100% and height 100% to fill the React Flow wrapper (VPC-in-VPC fix)", () => {
    render(<AwsGroupNode {...props} />);
    const container = screen.getByTestId("aws-group-node");
    expect(container.style.width).toBe("100%");
    expect(container.style.height).toBe("100%");
  });

  it("highlights when selected", () => {
    render(<AwsGroupNode {...props} selected />);
    const container = screen.getByTestId("aws-group-node");
    expect(container.className).toMatch(/selected|ring|border-blue/i);
  });

  // Phase B-3: each group node has a toggle button so users can fold large
  // sections of the graph out of view.
  describe("collapse toggle (B-3)", () => {
    it("renders a collapse toggle button", () => {
      render(<AwsGroupNode {...props} />);
      expect(screen.getByRole("button", { name: /collapse|expand/i })).toBeInTheDocument();
    });

    it("shows an expand icon when the group is collapsed", () => {
      render(
        <CollapseContext.Provider
          value={{ collapsedIds: new Set(["vpc-123"]), toggleCollapse: () => {} }}
        >
          <AwsGroupNode {...props} />
        </CollapseContext.Provider>,
      );
      expect(screen.getByRole("button", { name: /expand/i })).toBeInTheDocument();
    });

    it("shows a collapse icon when the group is expanded", () => {
      render(
        <CollapseContext.Provider
          value={{ collapsedIds: new Set(), toggleCollapse: () => {} }}
        >
          <AwsGroupNode {...props} />
        </CollapseContext.Provider>,
      );
      expect(screen.getByRole("button", { name: /collapse/i })).toBeInTheDocument();
    });

    it("calls toggleCollapse with the group id when toggle is clicked", async () => {
      const user = userEvent.setup();
      const toggle = vi.fn();
      render(
        <CollapseContext.Provider value={{ collapsedIds: new Set(), toggleCollapse: toggle }}>
          <AwsGroupNode {...props} />
        </CollapseContext.Provider>,
      );
      await user.click(screen.getByRole("button", { name: /collapse|expand/i }));
      expect(toggle).toHaveBeenCalledWith("vpc-123");
    });
  });

  // Phase A-2: handle positions follow rankdir for cleaner edge routing.
  describe("handle position by rankdir (A-2)", () => {
    it("uses Top/Bottom handles for TB rankdir", () => {
      render(
        <RankDirContext.Provider value="TB">
          <AwsGroupNode {...props} />
        </RankDirContext.Provider>,
      );
      expect(screen.getByTestId("handle-target-top")).toBeInTheDocument();
      expect(screen.getByTestId("handle-source-bottom")).toBeInTheDocument();
    });

    it("uses Left/Right handles for LR rankdir", () => {
      render(
        <RankDirContext.Provider value="LR">
          <AwsGroupNode {...props} />
        </RankDirContext.Provider>,
      );
      expect(screen.getByTestId("handle-target-left")).toBeInTheDocument();
      expect(screen.getByTestId("handle-source-right")).toBeInTheDocument();
    });
  });
});


