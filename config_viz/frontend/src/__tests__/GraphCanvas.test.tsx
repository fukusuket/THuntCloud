import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GraphCanvas } from "../components/GraphCanvas";
import type { ApiGraphNode, ApiGraphEdge } from "../types";

// Mock reactflow to avoid canvas / ResizeObserver issues in jsdom
const { mockReactFlow } = vi.hoisted(() => {
  const mockReactFlow = vi.fn(({ nodes = [], edges = [] }: { nodes: unknown[]; edges: unknown[] }) => (
    <div data-testid="react-flow">
      {(nodes as Array<{ id: string; parentNode?: string }>).map((n) => (
        <div
          key={n.id}
          data-testid={`node-${n.id}`}
          data-parent-node={n.parentNode ?? ""}
        />
      ))}
      {(edges as Array<{ id: string }>).map((e) => (
        <div key={e.id} data-testid={`edge-${e.id}`} />
      ))}
    </div>
  ));
  return { mockReactFlow };
});

vi.mock("reactflow", () => ({
  // reactflow uses default export as well as named exports
  default: (props: unknown) => mockReactFlow(props as { nodes: unknown[]; edges: unknown[] }),
  ReactFlow: (props: unknown) => mockReactFlow(props as { nodes: unknown[]; edges: unknown[] }),
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
  useNodesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
  useEdgesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
  useReactFlow: () => ({ fitView: vi.fn() }),
}));

function wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// BF-03: GraphCanvas renders correct number of nodes and edges
// BF-12: Nodes with parentId are rendered inside their parent container
describe("GraphCanvas", () => {
  const nodes: ApiGraphNode[] = [
    {
      id: "vpc-123",
      type: "awsGroupNode",
      position: { x: 0, y: 0 },
      parentId: null,
      data: {
        resource_id: "vpc-123",
        resource_type: "AWS::EC2::VPC",
        resource_name: "my-vpc",
        aws_region: "us-east-1",
        is_container: true,
      },
    },
    {
      id: "ec2-456",
      type: "awsNode",
      position: { x: 0, y: 0 },
      parentId: "vpc-123",
      data: {
        resource_id: "ec2-456",
        resource_type: "AWS::EC2::Instance",
        resource_name: "my-instance",
        aws_region: "us-east-1",
        is_container: false,
      },
    },
  ];

  const edges: ApiGraphEdge[] = [
    { id: "e1", source: "ec2-456", target: "s3-789", label: "uses" },
  ];

  it("renders correct number of nodes", () => {
    render(<GraphCanvas nodes={nodes} edges={[]} rankdir="TB" onNodeClick={() => {}} />, {
      wrapper,
    });
    expect(screen.getByTestId("node-vpc-123")).toBeInTheDocument();
    expect(screen.getByTestId("node-ec2-456")).toBeInTheDocument();
  });

  it("renders correct number of edges", () => {
    render(<GraphCanvas nodes={nodes} edges={edges} rankdir="TB" onNodeClick={() => {}} />, {
      wrapper,
    });
    expect(screen.getByTestId("edge-e1")).toBeInTheDocument();
  });

  it("maps parentId to parentNode for React Flow (BF-12)", () => {
    render(<GraphCanvas nodes={nodes} edges={[]} rankdir="TB" onNodeClick={() => {}} />, {
      wrapper,
    });
    // ec2-456 has parentId="vpc-123" → should be passed as parentNode="vpc-123" to ReactFlow
    const ec2Node = screen.getByTestId("node-ec2-456");
    expect(ec2Node).toHaveAttribute("data-parent-node", "vpc-123");
  });

  it("node without parentId has empty parentNode", () => {
    render(<GraphCanvas nodes={nodes} edges={[]} rankdir="TB" onNodeClick={() => {}} />, {
      wrapper,
    });
    const vpcNode = screen.getByTestId("node-vpc-123");
    expect(vpcNode).toHaveAttribute("data-parent-node", "");
  });
});


