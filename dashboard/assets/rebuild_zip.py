#!/usr/bin/env python3
"""Rebuild cloudtrail_default.zip in Superset v1 export format.

Superset v1 import requires the following ZIP structure (NO top-level subdir):
  metadata.yaml
  dashboards/<slug>.yaml
  charts/<slice_name>.yaml
  datasets/<db_name>/<table_name>.yaml
  databases/<db_name>.yaml
"""
import zipfile
import os
import shutil

BASE = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(BASE, "cloudtrail_default")
OUTPUT_ZIP = os.path.join(BASE, "cloudtrail_default.zip")

# Map: source path (relative to SOURCE_DIR) -> arc path inside ZIP
FILE_MAP = {
    "metadata.yaml":                              "metadata.yaml",
    "dashboard.yaml":                             "dashboards/cloudtrail_threat_hunting.yaml",
    "databases/CloudTrail_DuckDB.yaml":           "databases/CloudTrail_DuckDB.yaml",
    "datasets/cloudtrail_events.yaml":            "datasets/CloudTrail_DuckDB/cloudtrail_events.yaml",
    # Original charts (DSH-01 ~ DSH-05)
    "charts/event_timeseries.yaml":               "charts/CloudTrail_Events_Over_Time.yaml",
    "charts/top_api_calls.yaml":                  "charts/Top_20_API_Calls.yaml",
    "charts/iam_entity_activity.yaml":            "charts/IAM_Entity_Activity.yaml",
    "charts/error_trend.yaml":                    "charts/Error_Event_Trend.yaml",
    "charts/source_ip_requests.yaml":             "charts/Top_Source_IP_Addresses.yaml",
    # Threat hunting charts (DSH-08 ~ DSH-14, excl. DSH-10 removed)
    "charts/console_login_activity.yaml":         "charts/Console_Login_Activity.yaml",
    "charts/access_denied_top_actions.yaml":      "charts/Top_Access_Denied_Actions.yaml",
    "charts/user_agent_analysis.yaml":            "charts/User_Agent_Analysis.yaml",
    "charts/sensitive_api_calls.yaml":            "charts/Sensitive_API_Calls.yaml",
    "charts/root_account_usage.yaml":             "charts/Root_Account_Usage.yaml",
    "charts/region_activity.yaml":                "charts/Region_Activity.yaml",
    # GeoIP charts (DSH-15 ~ DSH-18)
    "charts/geo_country_requests.yaml":           "charts/Geo_Country_Requests.yaml",
    "charts/geo_world_map.yaml":                  "charts/Geo_World_Map.yaml",
    "charts/geo_city_requests.yaml":              "charts/Geo_City_Requests.yaml",
    "charts/geo_asn_org_requests.yaml":           "charts/Geo_ASN_Org_Requests.yaml",
}

if os.path.exists(OUTPUT_ZIP):
    os.remove(OUTPUT_ZIP)
    print(f"Removed old: {OUTPUT_ZIP}")

with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
    for src_rel, arc_name in FILE_MAP.items():
        abs_path = os.path.join(SOURCE_DIR, src_rel)
        if not os.path.exists(abs_path):
            print(f"  MISSING: {abs_path}")
            continue
        zf.write(abs_path, arc_name)
        print(f"  Added: {arc_name}")

print(f"\nCreated: {OUTPUT_ZIP}")

# Verify structure
with zipfile.ZipFile(OUTPUT_ZIP) as zf:
    names = zf.namelist()
    print("\nZIP contents:")
    for n in names:
        print(f"  {n}")

    # Check uuid in databases file
    db_yaml = zf.read("databases/CloudTrail_DuckDB.yaml").decode()
    if "uuid:" in db_yaml:
        print("\nOK: uuid found in databases/CloudTrail_DuckDB.yaml")
    else:
        print("\nERROR: uuid NOT found in databases/CloudTrail_DuckDB.yaml")

    # Check metadata
    meta = zf.read("metadata.yaml").decode()
    print(f"\nmetadata.yaml:\n{meta}")


