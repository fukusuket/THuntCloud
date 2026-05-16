import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ReactFlowProvider } from "reactflow";
import { fetchGraph } from "./api";
import { Sidebar } from "./components/Sidebar";
import { GraphCanvas } from "./components/GraphCanvas";
import { DetailPanel } from "./components/DetailPanel";
import type { RankDir } from "./types";

/**
 * Root application component.
 * Manages global state: selected snapshot, resource type filter, layout direction,
 * and currently selected node for the detail panel.
 */
export default function App() {
  const [selectedSnapshotId, setSelectedSnapshotId] = useState<string | null>(null);
  const [resourceTypeFilter, setResourceTypeFilter] = useState<string | undefined>(undefined);
  const [rankdir, setRankdir] = useState<RankDir>("TB");
  const [selectedResourceId, setSelectedResourceId] = useState<string | null>(null);

  // Fetch graph data when a snapshot is selected (BF-02)
  const { data: graphData } = useQuery({
    queryKey: ["graph", selectedSnapshotId, resourceTypeFilter],
    queryFn: () => fetchGraph(selectedSnapshotId!, resourceTypeFilter),
    enabled: !!selectedSnapshotId,
  });

  const handleSnapshotSelect = (snapshotId: string) => {
    setSelectedSnapshotId(snapshotId);
    setSelectedResourceId(null);
    setResourceTypeFilter(undefined);
  };

  const handleFilterChange = (resourceType: string | undefined) => {
    setResourceTypeFilter(resourceType);
    setSelectedResourceId(null);
  };

  // BF-05: Clicking a node opens the DetailPanel
  const handleNodeClick = (resourceId: string) => {
    setSelectedResourceId(resourceId);
  };

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-gray-100 font-sans">
      {/* Sidebar: snapshot list + filters + layout toggle */}
      <Sidebar
        selectedSnapshotId={selectedSnapshotId}
        onSnapshotSelect={handleSnapshotSelect}
        onFilterChange={handleFilterChange}
        onRankdirChange={setRankdir}
        rankdir={rankdir}
      />

      {/* Main graph area */}
      <main className="flex-1 relative overflow-hidden">
        {!selectedSnapshotId ? (
          <div className="flex h-full items-center justify-center text-gray-400 text-sm">
            Select a snapshot to explore resources.
          </div>
        ) : !graphData ? (
          <div className="flex h-full items-center justify-center text-gray-400 text-sm">
            Loading graph…
          </div>
        ) : (
          <ReactFlowProvider>
            <GraphCanvas
              nodes={graphData.nodes}
              edges={graphData.edges}
              rankdir={rankdir}
              onNodeClick={handleNodeClick}
            />
          </ReactFlowProvider>
        )}
      </main>

      {/* Detail panel (BF-05, BF-06) */}
      {selectedSnapshotId && selectedResourceId && (
        <DetailPanel
          snapshotId={selectedSnapshotId}
          resourceId={selectedResourceId}
          onClose={() => setSelectedResourceId(null)}
        />
      )}
    </div>
  );
}

