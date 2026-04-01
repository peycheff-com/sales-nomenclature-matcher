import api from "./client";
import type { QualityMetrics } from "./types";

export async function getQualityMetrics(params?: {
  supplier_id?: string;
  category_id?: string;
}): Promise<QualityMetrics> {
  const searchParams: Record<string, string> = {};
  if (params?.supplier_id) searchParams.supplier_id = params.supplier_id;
  if (params?.category_id) searchParams.category_id = params.category_id;
  return api
    .get("metrics/quality", { searchParams })
    .json<QualityMetrics>();
}

export interface TokenUsageSummary {
  period_days: number;
  totals: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    total_cost_usd: number;
    api_calls: number;
  };
  by_provider: Array<{
    provider: string;
    total_tokens: number;
    cost_usd: number;
    calls: number;
  }>;
  by_model: Array<{
    provider: string;
    model: string;
    operation: string;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    cost_usd: number;
    calls: number;
  }>;
  daily: Array<{
    date: string;
    total_tokens: number;
    cost_usd: number;
  }>;
}

export async function getTokenUsage(days = 30, provider?: string): Promise<TokenUsageSummary> {
  const params: Record<string, string> = { days: String(days) };
  if (provider) params.provider = provider;
  return api.get("metrics/tokens", { searchParams: params }).json<TokenUsageSummary>();
}
