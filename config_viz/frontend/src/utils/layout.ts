import Dagre from "@dagrejs/dagre";
import type { Node, Edge } from "reactflow";
import type { RankDir } from "../types";

const NODE_W = 172;
const NODE_H = 50;
const PADDING = 24; // inner padding inside group nodes
const MIN_GROUP_W = 220;
const MIN_GROUP_H = 80;

function nodeDims(node: Node): { w: number; h: number } {
  if (node.type === "awsGroupNode") return { w: MIN_GROUP_W, h: MIN_GROUP_H };
  return { w: NODE_W, h: NODE_H };
}

/**
 * Run flat dagre on a list of nodes using pre-computed sizes.
 * Does NOT call g.setParent — avoids the "Cannot set properties of undefined
 * (setting 'rank')" crash in @dagrejs/dagre compound-graph support.
 *
 * Returns positions normalised so the bounding-box top-left is at (0, 0).
 */
function runFlatDagre(
  nodes: Node[],
  edges: Edge[],
  rankdir: RankDir,
  sizeOverrides: Map<string, { w: number; h: number }>
): { positions: Map<string, { x: number; y: number }>; totalW: number; totalH: number } {
  if (nodes.length === 0) return { positions: new Map(), totalW: 0, totalH: 0 };

  const g = new Dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir, ranksep: 60, nodesep: 40, marginx: PADDING, marginy: PADDING });

  const idSet = new Set(nodes.map((n) => n.id));

  for (const node of nodes) {
    const s = sizeOverrides.get(node.id) ?? nodeDims(node);
    g.setNode(node.id, { width: s.w, height: s.h });
  }
  for (const e of edges) {
    if (idSet.has(e.source) && idSet.has(e.target)) {
      g.setEdge(e.source, e.target);
    }
  }

  Dagre.layout(g);

  const positions = new Map<string, { x: number; y: number }>();
  let minX = Infinity;
  let minY = Infinity;

  for (const node of nodes) {
    const n = g.node(node.id);
    if (!n) continue;
    const s = sizeOverrides.get(node.id) ?? nodeDims(node);
    const w = isFinite(n.width) ? n.width : s.w;
    const h = isFinite(n.height) ? n.height : s.h;
    const x = n.x - w / 2;
    const y = n.y - h / 2;
    positions.set(node.id, { x, y });
    minX = Math.min(minX, x);
    minY = Math.min(minY, y);
  }

  // Normalise so top-left of bounding box = (0, 0)
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const [id, pos] of positions) {
    const s = sizeOverrides.get(id) ?? nodeDims(nodes.find((n) => n.id === id)!);
    positions.set(id, { x: pos.x - minX, y: pos.y - minY });
    maxX = Math.max(maxX, pos.x - minX + s.w);
    maxY = Math.max(maxY, pos.y - minY + s.h);
  }

  return {
    positions,
    totalW: isFinite(maxX) ? maxX + PADDING : MIN_GROUP_W,
    totalH: isFinite(maxY) ? maxY + PADDING : MIN_GROUP_H,
  };
}

/**
 * Apply dagre auto-layout to a list of React Flow nodes and edges.
 *
 * Two-pass strategy (avoids dagre compound crash):
 *   1. Bottom-up: recursively lay out children inside each group to compute
 *      the group's required size.
 *   2. Top-down: lay out root-level nodes using those computed sizes.
 *
 * Child node positions are relative to their parent (required by React Flow
 * when `extent: "parent"` is set).
 *
 * @param nodes   - React Flow node array (may include `parentNode`)
 * @param edges   - React Flow edge array
 * @param rankdir - "TB" (top→bottom) or "LR" (left→right)
 * @returns New node array with updated `position` (and `style` for groups)
 */
export function applyDagreLayout(
  nodes: Node[],
  edges: Edge[],
  rankdir: RankDir = "TB"
): Node[] {
  if (nodes.length === 0) return nodes;

  // ── Build parent ↔ children maps ──────────────────────────────────────────
  const parentOf = new Map<string, string>();
  const childrenOf = new Map<string, Node[]>();

  for (const node of nodes) {
    const pn = (node as Node & { parentNode?: string }).parentNode;
    if (pn) {
      parentOf.set(node.id, pn);
      if (!childrenOf.has(pn)) childrenOf.set(pn, []);
      childrenOf.get(pn)!.push(node);
    }
  }

  // ── Computed sizes and relative positions (populated bottom-up) ───────────
  const computedSizes = new Map<string, { w: number; h: number }>();
  const relativePos = new Map<string, { x: number; y: number }>();

  /**
   * Recursively lay out children of `groupId` and return the required
   * dimensions for the group node itself.
   */
  function computeGroup(groupId: string): { w: number; h: number } {
    const children = childrenOf.get(groupId);
    if (!children || children.length === 0) {
      const base = nodeDims(nodes.find((n) => n.id === groupId) ?? ({ type: "awsGroupNode" } as Node));
      return { w: Math.max(base.w, MIN_GROUP_W), h: Math.max(base.h, MIN_GROUP_H) };
    }

    // Recurse first so child sizes are known
    for (const child of children) {
      if (childrenOf.has(child.id)) {
        const s = computeGroup(child.id);
        computedSizes.set(child.id, s);
      }
    }

    // Lay out the children flat inside this group
    const childEdges = edges.filter(
      (e) => children.some((c) => c.id === e.source) && children.some((c) => c.id === e.target)
    );
    const { positions, totalW, totalH } = runFlatDagre(
      children,
      childEdges,
      rankdir,
      computedSizes
    );

    for (const [id, pos] of positions) {
      // Offset by padding so children don't bleed into the group border
      relativePos.set(id, { x: pos.x + PADDING, y: pos.y + PADDING });
    }

    return {
      w: Math.max(totalW + PADDING * 2, MIN_GROUP_W),
      h: Math.max(totalH + PADDING * 2, MIN_GROUP_H),
    };
  }

  // ── Pass 1: bottom-up size computation for every root group ───────────────
  const rootNodes = nodes.filter((n) => !parentOf.has(n.id));

  for (const node of rootNodes) {
    if (childrenOf.has(node.id)) {
      const s = computeGroup(node.id);
      computedSizes.set(node.id, s);
    }
  }

  // ── Pass 2: lay out root nodes using computed sizes ───────────────────────
  // Root-level uses "LR" regardless of user preference so that disconnected
  // service groups (no edges between them) stack vertically instead of being
  // placed in a single horizontal row by dagre's same-rank assignment.
  const rootEdges = edges.filter(
    (e) =>
      rootNodes.some((n) => n.id === e.source) && rootNodes.some((n) => n.id === e.target)
  );
  const { positions: rootPositions } = runFlatDagre(
    rootNodes,
    rootEdges,
    "LR",
    computedSizes
  );

  // ── Build final node list ─────────────────────────────────────────────────
  return nodes.map((node) => {
    const isGroup = node.type === "awsGroupNode";
    const size = computedSizes.get(node.id);

    if (rootPositions.has(node.id)) {
      const pos = rootPositions.get(node.id)!;
      return {
        ...node,
        position: pos,
        ...(isGroup && size
          ? { style: { ...((node.style as object) ?? {}), width: size.w, height: size.h } }
          : {}),
      };
    }

    if (relativePos.has(node.id)) {
      const pos = relativePos.get(node.id)!;
      return {
        ...node,
        position: pos,
        ...(isGroup && size
          ? { style: { ...((node.style as object) ?? {}), width: size.w, height: size.h } }
          : {}),
      };
    }

    return node;
  });
}
