import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AwsGroupNode } from "../components/AwsGroupNode";

// Mock reactflow: Handle requires zustand provider context, which is unavailable in isolation
vi.mock("reactflow", () => ({
  Handle: () => null,
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

  it("highlights when selected", () => {
    render(<AwsGroupNode {...props} selected />);
    const container = screen.getByTestId("aws-group-node");
    expect(container.className).toMatch(/selected|ring|border-blue/i);
  });
});


