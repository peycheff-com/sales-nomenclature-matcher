import api from "./client";
import type { QualityMetrics } from "./types";

export async function getQualityMetrics(params?: {
  supplier_id?: string;
}): Promise<QualityMetrics> {
  const searchParams: Record<string, string> = {};
  if (params?.supplier_id) searchParams.supplier_id = params.supplier_id;
  return api
    .get("metrics/quality", { searchParams })
    .json<QualityMetrics>();
}
