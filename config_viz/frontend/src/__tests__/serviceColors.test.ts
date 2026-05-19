import { describe, it, expect } from "vitest";
import { serviceColorOf, MINIMAP_LEAF_COLOR } from "../utils/serviceColors";

// Phase A-3: a single source of truth for "what color represents this
// AWS service" — shared between group node borders and the MiniMap.
describe("serviceColorOf", () => {
  it("returns the EC2 palette color for EC2 resource types", () => {
    expect(serviceColorOf("AWS::EC2::Instance")).toMatch(/^#/);
    expect(serviceColorOf("AWS::EC2::Instance")).toBe(serviceColorOf("AWS::EC2::VPC"));
  });

  it("returns the same color for a virtual service-group node and its members", () => {
    expect(serviceColorOf("__service__IAM")).toBe(serviceColorOf("AWS::IAM::Role"));
  });

  it("returns a neutral fallback for unknown services", () => {
    const color = serviceColorOf("AWS::SomethingNew::Thing");
    expect(color).toMatch(/^#/);
  });

  it("returns a neutral leaf color for non-namespaced strings", () => {
    expect(serviceColorOf("")).toMatch(/^#/);
  });

  it("exposes a distinct neutral color for plain leaf nodes on the MiniMap", () => {
    expect(MINIMAP_LEAF_COLOR).toMatch(/^#/);
  });
});
