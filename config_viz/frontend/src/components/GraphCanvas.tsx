import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Controls,
  MarkerType,
  MiniMap,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Node,
  type Edge,
  type NodeMouseHandler,
} from "reactflow";
import "reactflow/dist/style.css";

import { MINIMAP_LEAF_COLOR, serviceColorOf } from "../utils/serviceColors";
import { getVisibleNodes, rewireEdges } from "../utils/collapse";
import { CollapseContext } from "./CollapseContext";
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
  searchTerm?: string;
  collapsedIds?: Set<string>;
  onToggleCollapse?: (id: string) => void;
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
export function GraphCanvas({
  nodes: apiNodes,
  edges: apiEdges,
  rankdir,
  onNodeClick,
  searchTerm = "",
  collapsedIds = new Set<string>(),
  onToggleCollapse = () => {},
}: GraphCanvasProps) {
  const { fitView } = useReactFlow();
  // Store fitView in a ref so the effect below does not re-run when the
  // React Flow instance re-initialises between renders.
  const fitViewRef = useRef(fitView);
  fitViewRef.current = fitView;
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

  // Phase B-3: filter out descendants of collapsed groups before layout so
  // dagre does not allocate space for invisible nodes.
  const visibleApiNodes = useMemo(
    () => getVisibleNodes(apiNodes, collapsedIds),
    [apiNodes, collapsedIds],
  );
  const visibleApiEdges = useMemo(
    () => rewireEdges(apiEdges, collapsedIds, apiNodes),
    [apiEdges, collapsedIds, apiNodes],
  );

  const layoutedNodes = applyDagreLayout(
    toRfNodes(visibleApiNodes),
    toRfEdges(visibleApiEdges),
    rankdir,
  );

  const [nodes, setNodes, onNodesChange] = useNodesState(layoutedNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(toRfEdges(visibleApiEdges));

  // Re-layout whenever visible data or rankdir changes.
  useEffect(() => {
    const rfNodes = toRfNodes(visibleApiNodes);
    const rfEdges = toRfEdges(visibleApiEdges);
    setNodes(applyDagreLayout(rfNodes, rfEdges, rankdir));
    setEdges(rfEdges);
  }, [visibleApiNodes, visibleApiEdges, rankdir, toRfNodes, toRfEdges, setNodes, setEdges]);

  // Phase B-4: re-fit the viewport after layout settles so the full graph
  // stays visible after snapshot switches, filter changes, and rankdir toggles.
  useEffect(() => {
    fitViewRef.current({ padding: 0.2, duration: 300 });
  }, [apiNodes, apiEdges, rankdir]);

  // Phase B-1: track which node the user last clicked so connected peers can
  // be emphasised and unrelated elements dimmed.
  const [highlightedId, setHighlightedId] = useState<string | null>(null);

  const displayNodes = useMemo(() => {
    const term = searchTerm.toLowerCase();

    // B-1: build the set of nodes connected to the highlighted node.
    const connected = highlightedId ? new Set<string>([highlightedId]) : null;
    if (connected) {
      for (const e of edges) {
        if (e.source === highlightedId) connected.add(e.target);
        if (e.target === highlightedId) connected.add(e.source);
      }
    }

    return nodes.map((n) => {
      let updated: typeof n = n;

      // B-1: dim unconnected nodes when something is highlighted.
      if (connected && !connected.has(n.id)) {
        updated = { ...updated, style: { ...((updated.style as object) ?? {}), opacity: 0.25 } };
      }

      // B-2: mark nodes that match the search term.
      if (term) {
        const d = n.data as { resource_id?: string; resource_name?: string | null };
        const matches =
          d.resource_id?.toLowerCase().includes(term) ||
          d.resource_name?.toLowerCase().includes(term);
        if (matches) {
          updated = {
            ...updated,
            className: ((updated.className ?? "") + " search-match").trim(),
          };
        }
      }

      return updated;
    });
  }, [nodes, edges, highlightedId, searchTerm]);

  const displayEdges = useMemo(() => {
    if (!highlightedId) return edges;
    return edges.map((e) =>
      e.source === highlightedId || e.target === highlightedId
        ? { ...e, animated: true, style: { ...e.style, stroke: "#3B82F6", strokeWidth: 2 } }
        : { ...e, style: { ...e.style, opacity: 0.2 } },
    );
  }, [edges, highlightedId]);

  const handleNodeClick: NodeMouseHandler = useCallback(
    (_event, node) => {
      setHighlightedId(node.id);
      const resourceId = (node.data as { resource_id: string }).resource_id;
      // Only open the detail panel for real resources, not virtual group headers.
      if (!resourceId.startsWith("__svc__")) {
        onNodeClick(resourceId);
      }
    },
    [onNodeClick]
  );

  const handlePaneClick = useCallback(() => {
    setHighlightedId(null);
  }, []);

  return (
    <CollapseContext.Provider value={{ collapsedIds, toggleCollapse: onToggleCollapse }}>
    <RankDirContext.Provider value={rankdir}>
      <div className="w-full h-full" data-testid="graph-canvas">
        <ReactFlow
          nodes={displayNodes}
          edges={displayEdges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={handleNodeClick}
          onPaneClick={handlePaneClick}
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
    </CollapseContext.Provider>
  );
}

