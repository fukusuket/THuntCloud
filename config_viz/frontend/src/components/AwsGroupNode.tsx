import { Handle, Position } from "reactflow";
import type { NodeData } from "../types";
import { getIconUrl } from "../utils/icons";
import { NEUTRAL_COLOR, serviceColorOf } from "../utils/serviceColors";
import { useRankDir } from "./RankDirContext";

interface AwsGroupNodeProps {
  id: string;
  data: NodeData & { member_count?: number };
  selected?: boolean;
}

// Tinted background and text shades keyed off the primary service color.
// Borders come from {@link serviceColorOf} so they always match the MiniMap.
const SERVICE_SECONDARY: Record<string, { bg: string; text: string }> = {
  "#FF9900": { bg: "#FFF8EE", text: "#7A4500" }, // amber: EC2 / Lambda / ECS / EKS / Logs
  "#DD344C": { bg: "#FFF0F2", text: "#7A1020" }, // red: IAM / KMS / Secrets / WAF
  "#3F8624": { bg: "#F0FAF0", text: "#1A4A0A" }, // green: S3 / Backup
  "#527FFF": { bg: "#EDF2FF", text: "#1E3A8A" }, // blue: RDS / DynamoDB / Athena
  "#E7157B": { bg: "#FDF0F7", text: "#7A0845" }, // magenta: CloudTrail / Config
  "#EE3524": { bg: "#FEF0EE", text: "#7A1510" }, // coral: CodeDeploy / Glue
  "#FF4F8B": { bg: "#FFF0F6", text: "#7A1545" }, // pink: SNS / SQS / Events
  "#8C4FFF": { bg: "#F1ECFF", text: "#3A1E7A" }, // purple: ELB
};

const DEFAULT_STYLE = { border: NEUTRAL_COLOR, bg: "#F9FAFB", text: "#374151" };

function _getStyle(resourceType: string) {
  const border = serviceColorOf(resourceType);
  if (border === NEUTRAL_COLOR) return DEFAULT_STYLE;
  const secondary = SERVICE_SECONDARY[border];
  return secondary ? { border, ...secondary } : DEFAULT_STYLE;
}

/**
 * Custom React Flow node for container AWS resources (service groups, VPCs, Subnets…).
 * Renders a labeled dashed-border rectangle that can visually contain child nodes.
 * Service-group virtual nodes (id starts with "__svc__") use a bold colored header.
 */
export function AwsGroupNode({ id, data, selected }: AwsGroupNodeProps) {
  const label = data.resource_name ?? id;
  const isServiceGroup = data.resource_type?.startsWith("__service__");
  const style = _getStyle(data.resource_type ?? "");
  const rankdir = useRankDir();
  const targetPos = rankdir === "LR" ? Position.Left : Position.Top;
  const sourcePos = rankdir === "LR" ? Position.Right : Position.Bottom;

  return (
    <div
      data-testid="aws-group-node"
      style={{
        borderColor: selected ? "#3B82F6" : style.border,
        backgroundColor: style.bg,
        minWidth: isServiceGroup ? 240 : 180,
        minHeight: isServiceGroup ? 140 : 100,
      }}
      className={[
        "group-node relative rounded-lg border-2 border-dashed",
        "p-2",
        selected ? "ring-2 ring-blue-400" : "",
      ].join(" ")}
    >
      <Handle type="target" position={targetPos} className="!w-2 !h-2 opacity-50" />

      {/* Header */}
      <div
        className="flex items-center gap-1.5 mb-1 pb-1"
        style={{
          borderBottom: isServiceGroup ? `1px solid ${style.border}40` : "none",
        }}
      >
        <img
          src={getIconUrl(data.resource_type ?? "")}
          alt={data.resource_type ?? ""}
          className="shrink-0"
          style={{ width: isServiceGroup ? 20 : 16, height: isServiceGroup ? 20 : 16 }}
          onError={(e) => {
            (e.currentTarget as HTMLImageElement).src = "/icons/default.png";
          }}
        />
        <span
          className="truncate font-semibold leading-tight"
          style={{
            color: style.text,
            fontSize: isServiceGroup ? "12px" : "10px",
          }}
        >
          {label}
        </span>
        {isServiceGroup && data.member_count !== undefined && (
          <span
            className="ml-auto shrink-0 rounded-full px-1.5 py-0.5 text-[9px] font-bold"
            style={{ backgroundColor: `${style.border}20`, color: style.border }}
          >
            {data.member_count}
          </span>
        )}
      </div>

      {!isServiceGroup && (
        <div className="text-[9px] truncate" style={{ color: `${style.text}99` }}>
          {data.resource_type}
        </div>
      )}

      <Handle type="source" position={sourcePos} className="!w-2 !h-2 opacity-50" />
    </div>
  );
}
