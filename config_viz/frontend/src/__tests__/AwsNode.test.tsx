import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AwsNode } from "../components/AwsNode";

// Mock reactflow: Handle requires zustand provider context, which is unavailable in isolation
vi.mock("reactflow", () => ({
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
}));

// BF-04: AwsNode shows tooltip on hover (ID / Name / Type)
describe("AwsNode", () => {
  const data = {
    resource_id: "ec2-456",
    resource_type: "AWS::EC2::Instance",
    resource_name: "my-instance",
    aws_region: "us-east-1",
    is_container: false,
  };

  it("renders the resource name", () => {
    render(<AwsNode id="ec2-456" data={data} />);
    expect(screen.getByText("my-instance")).toBeInTheDocument();
  });

  it("falls back to resource_id when resource_name is null", () => {
    render(<AwsNode id="ec2-456" data={{ ...data, resource_name: null }} />);
    expect(screen.getByText("ec2-456")).toBeInTheDocument();
  });

  it("shows tooltip with ID, Name and Type on hover", async () => {
    const user = userEvent.setup();
    render(<AwsNode id="ec2-456" data={data} />);

    const node = screen.getByTestId("aws-node");
    await user.hover(node);

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip).toBeInTheDocument();
    // Verify tooltip contains the key fields
    expect(within(tooltip).getByText("ec2-456")).toBeInTheDocument();
    expect(within(tooltip).getByText("my-instance")).toBeInTheDocument();
    expect(within(tooltip).getByText(/AWS::EC2::Instance/)).toBeInTheDocument();
  });

  it("hides tooltip on mouse leave", async () => {
    const user = userEvent.setup();
    render(<AwsNode id="ec2-456" data={data} />);

    const node = screen.getByTestId("aws-node");
    await user.hover(node);
    expect(screen.getByRole("tooltip")).toBeInTheDocument();

    await user.unhover(node);
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
  });
});




