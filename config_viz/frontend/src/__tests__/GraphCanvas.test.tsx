import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { GraphCanvas } from "../components/GraphCanvas";
import type { ApiGraphNode, ApiGraphEdge } from "../types";

// Mock reactflow to avoid canvas / ResizeObserver issues in jsdom
const { mockReactFlow } = vi.hoisted(() => {
  const mockReactFlow = vi.fn(
    ({
      nodes = [],
      edges = [],
      children,
    }: {
      nodes: unknown[];
      edges: unknown[];
      children?: React.ReactNode;
    }) => (
      <div data-testid="react-flow">
        {(nodes as Array<{ id: string; parentNode?: string }>).map((n) => (
          <div
            key={n.id}
            data-testid={`node-${n.id}`}
            data-parent-node={n.parentNode ?? ""}
          />
        ))}
        {(
          edges as Array<{
            id: string;
            type?: string;
            label?: string;
            markerEnd?: { type?: string };
            style?: { stroke?: string; strokeWidth?: number };
          }>
        ).map((e) => (
          <div
            key={e.id}
            data-testid={`edge-${e.id}`}
            data-edge-type={e.type ?? ""}
            data-edge-label={e.label ?? ""}
            data-marker-end-type={e.markerEnd?.type ?? ""}
            data-stroke={e.style?.stroke ?? ""}
            data-stroke-width={e.style?.strokeWidth ?? ""}
          />
        ))}
        {children}
      </div>
    ),
  );
  return { mockReactFlow };
});

vi.mock("reactflow", () => ({
  // reactflow uses default export as well as named exports
  default: (props: unknown) => mockReactFlow(props as { nodes: unknown[]; edges: unknown[] }),
  ReactFlow: (props: unknown) => mockReactFlow(props as { nodes: unknown[]; edges: unknown[] }),
  ReactFlowProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  Background: (props: { variant?: string; gap?: number; color?: string }) => (
    <div
      data-testid="rf-background"
      data-variant={props.variant ?? ""}
      data-gap={props.gap ?? ""}
      data-color={props.color ?? ""}
    />
  ),
  Controls: () => null,
  MiniMap: (props: { nodeColor?: unknown }) => (
    <div
      data-testid="rf-minimap"
      data-has-node-color={typeof props.nodeColor === "function" ? "yes" : "no"}
    />
  ),
  Handle: () => null,
  Position: { Top: "top", Bottom: "bottom", Left: "left", Right: "right" },
  useNodesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
  useEdgesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
  useReactFlow: () => ({ fitView: vi.fn() }),
  MarkerType: { ArrowClosed: "arrowclosed", Arrow: "arrow" },
  BackgroundVariant: { Dots: "dots", Lines: "lines", Cross: "cross" },
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

  // Phase A-1: edges use smoothstep routing with arrow markers and a visible
  // stroke so dependency direction is readable at a glance.
  describe("edge styling (A-1)", () => {
    it("renders edges with smoothstep type", () => {
      render(<GraphCanvas nodes={nodes} edges={edges} rankdir="TB" onNodeClick={() => {}} />, {
        wrapper,
      });
      expect(screen.getByTestId("edge-e1")).toHaveAttribute("data-edge-type", "smoothstep");
    });

    it("renders edges with an arrow marker at the target end", () => {
      render(<GraphCanvas nodes={nodes} edges={edges} rankdir="TB" onNodeClick={() => {}} />, {
        wrapper,
      });
      expect(screen.getByTestId("edge-e1")).toHaveAttribute(
        "data-marker-end-type",
        "arrowclosed",
      );
    });

    it("renders edges with a stroke color and width", () => {
      render(<GraphCanvas nodes={nodes} edges={edges} rankdir="TB" onNodeClick={() => {}} />, {
        wrapper,
      });
      const edge = screen.getByTestId("edge-e1");
      expect(edge.getAttribute("data-stroke")).toMatch(/^#/);
      expect(Number(edge.getAttribute("data-stroke-width"))).toBeGreaterThan(1);
    });

    it("preserves the original edge label", () => {
      render(<GraphCanvas nodes={nodes} edges={edges} rankdir="TB" onNodeClick={() => {}} />, {
        wrapper,
      });
      expect(screen.getByTestId("edge-e1")).toHaveAttribute("data-edge-label", "uses");
    });
  });

  // Phase A-3: Background uses dots so it does not visually compete with the
  // group node dashed borders, and the MiniMap colors nodes by service.
  describe("background & minimap (A-3)", () => {
    it("renders the dots background variant", () => {
      render(<GraphCanvas nodes={nodes} edges={[]} rankdir="TB" onNodeClick={() => {}} />, {
        wrapper,
      });
      expect(screen.getByTestId("rf-background")).toHaveAttribute("data-variant", "dots");
    });

    it("passes a nodeColor function to the MiniMap", () => {
      render(<GraphCanvas nodes={nodes} edges={[]} rankdir="TB" onNodeClick={() => {}} />, {
        wrapper,
      });
      expect(screen.getByTestId("rf-minimap")).toHaveAttribute("data-has-node-color", "yes");
    });
  });
});


