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
  // This mirrors the real AWS config hierarchy.  The VPC group must be large
  // enough (style.width / style.height) to visually contain its children so
  // that, combined with AwsGroupNode's width/height:100%, children don't
  // appear outside the VPC box.
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

    // VPC must have explicit dimensions set by layout
    expect(vpcW).toBeGreaterThan(0);
    expect(vpcH).toBeGreaterThan(0);

    // Children are positioned relative to VPC — they must fit within the VPC bounds
    // (position + node size <= vpc dimension).  NODE_W=200, NODE_H=56.
    expect(subnet.position.x + 200).toBeLessThanOrEqual(vpcW);
    expect(subnet.position.y + 56).toBeLessThanOrEqual(vpcH);
    expect(acl.position.x + 200).toBeLessThanOrEqual(vpcW);
    expect(acl.position.y + 56).toBeLessThanOrEqual(vpcH);
  });

  // Phase A-4: tuned spacing — connected LR siblings must sit far enough apart
  // (NODE_W=200 + ranksep=80 ⇒ ≥ 240 px between left edges).
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
});

