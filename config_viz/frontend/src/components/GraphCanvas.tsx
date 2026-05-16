import { useCallback, useEffect } from "react";
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "reactflow";
import "reactflow/dist/style.css";

import { applyDagreLayout } from "../utils/layout";
import { AwsNode } from "./AwsNode";
import { AwsGroupNode } from "./AwsGroupNode";
import type { ApiGraphNode, ApiGraphEdge, RankDir } from "../types";

const nodeTypes = {
  awsNode: AwsNode,
  awsGroupNode: AwsGroupNode,
};

interface GraphCanvasProps {
  nodes: ApiGraphNode[];
  edges: ApiGraphEdge[];
  rankdir: RankDir;
  onNodeClick: (resourceId: string) => void;
}

/**
 * Topologically sort nodes so parents always precede children.
 * React Flow requires this when `parentNode` / `extent: "parent"` are used.
 */
function topoSort(nodes: Node[]): Node[] {
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const visited = new Set<string>();
  const result: Node[] = [];

  function visit(id: string) {
    if (visited.has(id)) return;
    visited.add(id);
    const node = byId.get(id);
    if (!node) return;
    const pn = (node as Node & { parentNode?: string }).parentNode;
    if (pn) visit(pn); // ensure parent is output first
    result.push(node);
  }

  for (const node of nodes) visit(node.id);
  return result;
}

/**
 * Renders the AWS resource graph using React Flow.
 * Maps API nodes (parentId) → React Flow nodes (parentNode).
 * Applies dagre auto-layout before rendering.
 */
export function GraphCanvas({ nodes: apiNodes, edges: apiEdges, rankdir, onNodeClick }: GraphCanvasProps) {
  // Map API nodes to React Flow nodes (parentId -> parentNode), parents first
  const toRfNodes = useCallback(
    (src: ApiGraphNode[]): Node[] => {
      const mapped = src.map((n) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        parentNode: n.parentId ?? undefined,
        extent: n.parentId ? ("parent" as const) : undefined,
        data: n.data,
      }));
      return topoSort(mapped);
    },
    []
  );

  const toRfEdges = useCallback(
    (src: ApiGraphEdge[]): Edge[] =>
      src.map((e) => ({
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
        animated: false,
      })),
    []
  );

  const layoutedNodes = applyDagreLayout(toRfNodes(apiNodes), toRfEdges(apiEdges), rankdir);

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(toRfEdges(apiEdges));

  // Re-layout whenever input data or rankdir changes
  useEffect(() => {
    const rfNodes = toRfNodes(apiNodes);
    const rfEdges = toRfEdges(apiEdges);
    setNodes(applyDagreLayout(rfNodes, rfEdges, rankdir));
    setEdges(rfEdges);
  }, [apiNodes, apiEdges, rankdir, toRfNodes, toRfEdges, setNodes, setEdges]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      const resourceId = (node.data as { resource_id: string }).resource_id;
      // Skip clicks on virtual service-group nodes (no real resource to fetch)
      if (resourceId.startsWith("__svc__")) return;
      onNodeClick(resourceId);
    },
    [onNodeClick]
  );

  return (
    <div className="w-full h-full" data-testid="graph-canvas">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={handleNodeClick}
        fitView
        attributionPosition="bottom-right"
      >
        <Background />
        <Controls />
        <MiniMap nodeStrokeWidth={3} />
      </ReactFlow>
    </div>
  );
}

