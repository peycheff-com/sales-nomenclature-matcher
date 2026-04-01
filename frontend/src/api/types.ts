export interface MatchItemInput {
  line_id?: string;
  raw_text: string;
  original_row?: Record<string, any>;
}

export interface MatchRequestInput {
  supplier_id?: string;
  source_type?: string;
  items: MatchItemInput[];
}

export interface ProductRef {
  product_id: string;
  name: string;
  article?: string;
  brand?: string;
  category_path?: string;
}

export interface Candidate {
  product_id: string;
  name: string;
  article?: string;
  brand?: string;
  retrieval_rank: number;
  lexical_score?: number;
  semantic_score?: number;
  rerank_score?: number;
  rules_score?: number;
  final_score?: number;
  reasons: string[];
}

export interface MatchResult {
  request_item_id: string;
  line_id?: string;
  raw_text: string;
  original_row?: Record<string, any>;
  normalized_text?: string;
  extracted_attributes: Record<string, unknown>;
  status: "auto_match" | "review_needed" | "no_match";
  confidence?: number;
  best_candidate?: ProductRef;
  alternatives: Candidate[];
  reasons: string[];
  final_decision?: "accepted" | "corrected" | "rejected";
  reviewed_by?: string | null;
  final_product?: ProductRef | null;
}

export interface MatchResponse {
  request_id: string;
  status: string;
  results: MatchResult[];
}

export interface BatchRequestAccepted {
  request_id: string;
  status: string;
}

export interface MatchRequestDetails {
  request_id: string;
  supplier_id?: string;
  status: "queued" | "running" | "done" | "failed";
  total_items: number;
  processed_items: number;
  auto_matched_items: number;
  review_needed_items: number;
  no_match_items: number;
  created_at: string;
  started_at?: string;
  finished_at?: string;
}

export interface MatchItemsPage {
  page: number;
  page_size: number;
  total: number;
  items: MatchResult[];
}

export interface ReviewInput {
  final_decision: "accepted" | "corrected" | "rejected";
  final_product_id?: string;
  create_alias?: boolean;
  create_supplier_mapping?: boolean;
}

export interface SupplierProfile {
  supplier_id: string;
  supplier_name: string;
  strict_mode: boolean;
  is_active: boolean;
}

export interface QualityMetrics {
  total_cases: number;
  top1_accuracy?: number;
  top3_recall?: number;
  precision_at_1?: number;
  auto_match_false_positive_rate?: number;
  review_acceptance_rate?: number;
  avg_latency_ms?: number;
}

export interface LoginResponse {
  logged_in: boolean;
}

export interface UserResponse {
  user_id: string;
  username: string;
  full_name?: string;
  role: string;
  must_change_password: boolean;
}

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
  embedding_model?: string;
  embedding_dimensions?: number;
  auto_match_threshold?: number;
  review_threshold?: number;
  agentic_resolution_enabled?: boolean;
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
