/**
 * Service-level color palette shared between group node borders, leaf icons,
 * and the MiniMap. Keep a single source of truth so MiniMap colors match
 * what users see on the canvas.
 *
 * Colors follow the AWS brand palette per service category.
 */

const SERVICE_PRIMARY: Record<string, string> = {
  AppConfig: "#EE3524",
  Athena: "#527FFF",
  AutoScaling: "#FF9900",
  Backup: "#3F8624",
  Cassandra: "#527FFF",
  CloudFormation: "#E7157B",
  CloudFront: "#FF9900",
  CloudTrail: "#E7157B",
  CodeDeploy: "#EE3524",
  Config: "#E7157B",
  DataZone: "#527FFF",
  DynamoDB: "#527FFF",
  EC2: "#FF9900",
  ECR: "#FF9900",
  ECS: "#FF9900",
  EKS: "#FF9900",
  ElasticLoadBalancing: "#8C4FFF",
  ElasticLoadBalancingV2: "#8C4FFF",
  Events: "#FF4F8B",
  Glue: "#EE3524",
  IAM: "#DD344C",
  KMS: "#DD344C",
  Lambda: "#FF9900",
  Logs: "#FF9900",
  RDS: "#527FFF",
  S3: "#3F8624",
  SNS: "#FF4F8B",
  SQS: "#FF4F8B",
  Scheduler: "#FF4F8B",
  SecretsManager: "#DD344C",
  StepFunctions: "#FF4F8B",
  WAFv2: "#DD344C",
};

/** Neutral color used when a service has no mapped palette entry. */
export const NEUTRAL_COLOR = "#6B7280";

/** MiniMap color for plain leaf (non-group) nodes — lighter than service tones. */
export const MINIMAP_LEAF_COLOR = "#D1D5DB";

/**
 * Extract the service namespace from a resource type string.
 *   "AWS::EC2::Instance"  → "EC2"
 *   "__service__IAM"      → "IAM"
 *   ""                    → ""
 */
function _extractService(resourceType: string): string {
  if (!resourceType) return "";
  if (resourceType.startsWith("__service__")) {
    return resourceType.slice("__service__".length);
  }
  const parts = resourceType.split("::");
  return parts.length >= 2 ? parts[1] : "";
}

/**
 * Return the primary hex color associated with a given AWS resource type.
 * Falls back to {@link NEUTRAL_COLOR} when the service is unknown.
 */
export function serviceColorOf(resourceType: string): string {
  const svc = _extractService(resourceType);
  return SERVICE_PRIMARY[svc] ?? NEUTRAL_COLOR;
}
