import api from "./client";

export interface OneCConnectionSettings {
  base_url: string;
  username: string;
  password: string;
  catalog_endpoint: string;
  enabled: boolean;
}

export interface ProviderConfigResponse {
  id: string;
  name: string;
  api_key_set: boolean;
  base_url: string;
}

export interface SettingsResponse {
  llm_provider: string;
  embedding_provider: string;
  rerank_provider: string;
  providers_registry: ProviderConfigResponse[];
  llm_model: string;
  llm_rerank_model: string;
  embedding_model: string;
  embedding_dimensions: number;
  auto_match_threshold: number;
  review_threshold: number;
  retrieval_top_n: number;
  rerank_top_n: number;
  agentic_resolution_enabled: boolean;
  onec: OneCConnectionSettings;
}

export interface ProviderConfigInput {
  id: string;
  api_key?: string;
  base_url?: string;
}

export interface SettingsUpdateInput {
  llm_provider?: string;
  embedding_provider?: string;
  rerank_provider?: string;
  providers_registry?: ProviderConfigInput[];
  llm_model?: string;
  llm_rerank_model?: string;
  embedding_model?: string;
  embedding_dimensions?: number;
  auto_match_threshold?: number;
  review_threshold?: number;
  retrieval_top_n?: number;
  rerank_top_n?: number;
  agentic_resolution_enabled?: boolean;
  onec?: OneCConnectionSettings;
}

export interface OpenRouterModel {
  id: string;
  name: string;
  context_length: number;
  type?: string;
}

export interface OpenRouterModelsResponse {
  models: OpenRouterModel[];
}

export async function getSettings(): Promise<SettingsResponse> {
  return api.get("settings").json<SettingsResponse>();
}

export async function updateSettings(input: SettingsUpdateInput): Promise<SettingsResponse> {
  return api.put("settings", { json: input }).json<SettingsResponse>();
}

export async function getModels(providerId?: string): Promise<OpenRouterModelsResponse> {
  const searchParams = new URLSearchParams();
  if (providerId) {
    searchParams.set("provider_id", providerId);
  }
  return api.get("settings/models", { searchParams }).json<OpenRouterModelsResponse>();
}

export async function testOneCConnection(): Promise<{ status: string; detail?: string; http_status?: number }> {
  return api.post("settings/test-onec").json();
}
