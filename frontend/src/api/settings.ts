import api from "./client";

export interface OneCConnectionSettings {
  base_url: string;
  username: string;
  password: string;
  catalog_endpoint: string;
  enabled: boolean;
}

export interface SettingsResponse {
  llm_provider: string;
  embedding_provider: string;
  llm_model: string;
  llm_rerank_model: string;
  embedding_model: string;
  embedding_dimensions: number;
  openrouter_api_key_set: boolean;
  openai_api_key_set: boolean;
  google_api_key_set: boolean;
  cohere_api_key_set: boolean;
  auto_match_threshold: number;
  review_threshold: number;
  retrieval_top_n: number;
  rerank_top_n: number;
  onec: OneCConnectionSettings;
}

export interface SettingsUpdateInput {
  llm_provider?: string;
  embedding_provider?: string;
  llm_model?: string;
  llm_rerank_model?: string;
  embedding_model?: string;
  embedding_dimensions?: number;
  openrouter_api_key?: string;
  openai_api_key?: string;
  google_api_key?: string;
  cohere_api_key?: string;
  auto_match_threshold?: number;
  review_threshold?: number;
  retrieval_top_n?: number;
  rerank_top_n?: number;
  onec?: OneCConnectionSettings;
}

export interface FreeModel {
  id: string;
  name: string;
  context_length: number;
}

export interface FreeModelsResponse {
  models: FreeModel[];
}

export async function getSettings(): Promise<SettingsResponse> {
  return api.get("settings").json<SettingsResponse>();
}

export async function updateSettings(input: SettingsUpdateInput): Promise<SettingsResponse> {
  return api.put("settings", { json: input }).json<SettingsResponse>();
}

export async function getFreeModels(): Promise<FreeModelsResponse> {
  return api.get("settings/free-models").json<FreeModelsResponse>();
}

export async function testOneCConnection(): Promise<{ status: string; detail?: string; http_status?: number }> {
  return api.post("settings/test-onec").json();
}
