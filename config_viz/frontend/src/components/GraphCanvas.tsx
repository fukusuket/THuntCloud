import { useCallback, useEffect } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "reactflow";
import "reactflow/dist/style.css";

import { MINIMAP_LEAF_COLOR, serviceColorOf } from "../utils/serviceColors";
import { RankDirContext } from "./RankDirContext";

// Phase A-1: shared visual constants for edge rendering.
const EDGE_STROKE = "#9CA3AF";
const EDGE_STROKE_WIDTH = 1.5;

// Phase A-3: paint group nodes with their service color on the MiniMap;
// leaf nodes get a uniform light gray so groups remain the dominant signal.
function _minimapNodeColor(node: Node): string {
  if (node.type === "awsGroupNode") {
    const rt = (node.data as { resource_type?: string } | undefined)?.resource_type ?? "";
    return serviceColorOf(rt);
  }
  return MINIMAP_LEAF_COLOR;
}

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
        type: "smoothstep",
        style: { stroke: EDGE_STROKE, strokeWidth: EDGE_STROKE_WIDTH },
        markerEnd: {
          type: MarkerType.ArrowClosed,
          width: 14,
          height: 14,
          color: EDGE_STROKE,
        },
        labelStyle: { fill: "#4B5563", fontSize: 10 },
        labelBgStyle: { fill: "#FFFFFF", fillOpacity: 0.85 },
        labelBgPadding: [4, 2],
        labelBgBorderRadius: 2,
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
    <RankDirContext.Provider value={rankdir}>
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
          <Background variant={BackgroundVariant.Dots} gap={20} size={1} color="#E5E7EB" />
          <Controls />
          <MiniMap
            nodeStrokeWidth={3}
            nodeColor={_minimapNodeColor}
            maskColor="rgba(31,41,55,0.6)"
            pannable
            zoomable
          />
        </ReactFlow>
      </div>
    </RankDirContext.Provider>
  );
}

