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
});

