import { describe, it, expect } from "vitest";
import { applyDagreLayout } from "../utils/layout";
import type { Node, Edge } from "reactflow";

// BF-08: applyDagreLayout assigns position to all nodes (compound graph support)
describe("applyDagreLayout", () => {
  it("assigns numeric position to all nodes", () => {
    const nodes: Node[] = [
      { id: "a", position: { x: 0, y: 0 }, data: {} },
      { id: "b", position: { x: 0, y: 0 }, data: {} },
    ];
    const edges: Edge[] = [{ id: "e1", source: "a", target: "b" }];
    const result = applyDagreLayout(nodes, edges);

    expect(result).toHaveLength(2);
    for (const n of result) {
      expect(typeof n.position.x).toBe("number");
      expect(typeof n.position.y).toBe("number");
      expect(isNaN(n.position.x)).toBe(false);
      expect(isNaN(n.position.y)).toBe(false);
    }
  });

  it("handles compound graph — child has parentNode set", () => {
    const nodes: Node[] = [
      { id: "vpc", type: "awsGroupNode", position: { x: 0, y: 0 }, data: {} },
      {
        id: "ec2",
        type: "awsNode",
        position: { x: 0, y: 0 },
        data: {},
        parentNode: "vpc",
      },
    ];
    const edges: Edge[] = [];
    const result = applyDagreLayout(nodes, edges);

    expect(result).toHaveLength(2);
    for (const n of result) {
      expect(typeof n.position.x).toBe("number");
      expect(typeof n.position.y).toBe("number");
    }
  });

  it("accepts rankdir LR and still assigns positions", () => {
    const nodes: Node[] = [
      { id: "x", position: { x: 0, y: 0 }, data: {} },
      { id: "y", position: { x: 0, y: 0 }, data: {} },
    ];
    const edges: Edge[] = [{ id: "e1", source: "x", target: "y" }];
    const result = applyDagreLayout(nodes, edges, "LR");

    expect(result).toHaveLength(2);
    for (const n of result) {
      expect(typeof n.position.x).toBe("number");
      expect(typeof n.position.y).toBe("number");
    }
  });

  it("returns original node when dagre has no computed position", () => {
    // Edge without corresponding nodes should not crash
    const nodes: Node[] = [{ id: "solo", position: { x: 42, y: 99 }, data: {} }];
    const edges: Edge[] = [];
    const result = applyDagreLayout(nodes, edges);

    expect(result).toHaveLength(1);
    expect(typeof result[0].position.x).toBe("number");
  });

  // Three-level compound graph: service-group → VPC → Subnet/NetworkACL
  it("three-level compound: VPC gets style.width/height large enough to contain Subnet and ACL", () => {
    const nodes: Node[] = [
      { id: "__svc__EC2", type: "awsGroupNode", position: { x: 0, y: 0 }, data: {} },
      {
        id: "vpc-001",
        type: "awsGroupNode",
        position: { x: 0, y: 0 },
        data: {},
        parentNode: "__svc__EC2",
        extent: "parent",
      },
      {
        id: "subnet-001",
        type: "awsNode",
        position: { x: 0, y: 0 },
        data: {},
        parentNode: "vpc-001",
        extent: "parent",
      },
      {
        id: "acl-001",
        type: "awsNode",
        position: { x: 0, y: 0 },
        data: {},
        parentNode: "vpc-001",
        extent: "parent",
      },
    ] as Node[];

    const result = applyDagreLayout(nodes, []);
    const vpc = result.find((n) => n.id === "vpc-001")!;
    const subnet = result.find((n) => n.id === "subnet-001")!;
    const acl = result.find((n) => n.id === "acl-001")!;

    const vpcW = (vpc.style as { width?: number })?.width ?? 0;
    const vpcH = (vpc.style as { height?: number })?.height ?? 0;

    expect(vpcW).toBeGreaterThan(0);
    expect(vpcH).toBeGreaterThan(0);

    expect(subnet.position.x + 200).toBeLessThanOrEqual(vpcW);
    expect(subnet.position.y + 56).toBeLessThanOrEqual(vpcH);
    expect(acl.position.x + 200).toBeLessThanOrEqual(vpcW);
    expect(acl.position.y + 56).toBeLessThanOrEqual(vpcH);
  });

  // Phase A-4: tuned spacing — connected LR siblings must sit far enough apart
  it("places two LR-connected leaf nodes at least 240px apart", () => {
    const nodes: Node[] = [
      { id: "a", type: "awsNode", position: { x: 0, y: 0 }, data: {} },
      { id: "b", type: "awsNode", position: { x: 0, y: 0 }, data: {} },
    ];
    const edges: Edge[] = [{ id: "e", source: "a", target: "b" }];
    const result = applyDagreLayout(nodes, edges, "LR");

    const a = result.find((n) => n.id === "a")!;
    const b = result.find((n) => n.id === "b")!;
    expect(Math.abs(a.position.x - b.position.x)).toBeGreaterThanOrEqual(240);
  });

  // FE-HG-01: 4-level compound graph (service → VPC → Subnet → Instance × 2).
  // Verifies that deep nesting does not break layout and children fit inside
  // their immediate parent (Subnet) container box.
  it("four-level compound: layout is valid and instances fit inside Subnet", () => {
    const nodes: Node[] = [
      { id: "__svc__EC2", type: "awsGroupNode", position: { x: 0, y: 0 }, data: {} },
      {
        id: "vpc-001",
        type: "awsGroupNode",
        position: { x: 0, y: 0 },
        data: {},
        parentNode: "__svc__EC2",
        extent: "parent",
      },
      {
        id: "subnet-001",
        type: "awsGroupNode",
        position: { x: 0, y: 0 },
        data: {},
        parentNode: "vpc-001",
        extent: "parent",
      },
      {
        id: "i-001",
        type: "awsNode",
        position: { x: 0, y: 0 },
        data: {},
        parentNode: "subnet-001",
        extent: "parent",
      },
      {
        id: "i-002",
        type: "awsNode",
        position: { x: 0, y: 0 },
        data: {},
        parentNode: "subnet-001",
        extent: "parent",
      },
    ] as Node[];

    const result = applyDagreLayout(nodes, []);

    expect(result).toHaveLength(5);
    for (const n of result) {
      expect(typeof n.position.x).toBe("number");
      expect(typeof n.position.y).toBe("number");
      expect(isNaN(n.position.x)).toBe(false);
      expect(isNaN(n.position.y)).toBe(false);
    }

    // Subnet must receive explicit dimensions from the layout engine.
    const subnet = result.find((n) => n.id === "subnet-001")!;
    const subnetW = (subnet.style as { width?: number })?.width ?? 0;
    const subnetH = (subnet.style as { height?: number })?.height ?? 0;
    expect(subnetW).toBeGreaterThan(0);
    expect(subnetH).toBeGreaterThan(0);

    // Children (NODE_W=200, NODE_H=56) must fit within the Subnet box.
    const i001 = result.find((n) => n.id === "i-001")!;
    const i002 = result.find((n) => n.id === "i-002")!;
    expect(i001.position.x + 200).toBeLessThanOrEqual(subnetW);
    expect(i001.position.y + 56).toBeLessThanOrEqual(subnetH);
    expect(i002.position.x + 200).toBeLessThanOrEqual(subnetW);
    expect(i002.position.y + 56).toBeLessThanOrEqual(subnetH);
  });
});
