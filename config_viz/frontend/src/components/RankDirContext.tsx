import { createContext, useContext } from "react";
import type { RankDir } from "../types";

/**
 * Phase A-2: provides the current dagre rank direction to descendant
 * AWS node components so they can place their connection handles on the
 * leading/trailing edge of the layout rather than fixed top/bottom.
 *
 * Default is "TB" to preserve the original behaviour when the provider is
 * not in scope (e.g. unit tests that render a node in isolation).
 */
export const RankDirContext = createContext<RankDir>("TB");

export function useRankDir(): RankDir {
  return useContext(RankDirContext);
}
