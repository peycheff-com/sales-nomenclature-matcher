import api from "./client";
import type {
  BatchRequestAccepted,
  Candidate,
  MatchItemInput,
  MatchItemsPage,
  MatchRequestDetails,
  MatchRequestInput,
  MatchResponse,
} from "./types";

export async function matchSync(input: MatchRequestInput): Promise<MatchResponse> {
  return api.post("match", { json: input }).json<MatchResponse>();
}

export async function matchBatch(input: MatchRequestInput): Promise<BatchRequestAccepted> {
  return api.post("match/batch", { json: input }).json<BatchRequestAccepted>();
}

export async function uploadFile(file: File, supplierId?: string, useAiColumnPicker: boolean = false): Promise<BatchRequestAccepted> {
  const formData = new FormData();
  formData.append("file", file);
  if (supplierId && supplierId !== "__all__") {
    formData.append("supplier_id", supplierId);
  }
  if (useAiColumnPicker) {
    formData.append("use_ai_column_picker", "true");
  }
  return api.post("match/upload", { body: formData }).json<BatchRequestAccepted>();
}

export async function parseFilePreview(file: File, useAiColumnPicker: boolean = false): Promise<{ items: MatchItemInput[] }> {
  const formData = new FormData();
  formData.append("file", file);
  if (useAiColumnPicker) {
    formData.append("use_ai_column_picker", "true");
  }
  return api.post("match/parse", { body: formData }).json<{ items: MatchItemInput[] }>();
}

export interface FileAnalysisResult {
  mode: "structured";
  supplier_items: Record<string, unknown>[];
  catalog_items: Record<string, unknown>[];
  supplier_name: string | null;
  tables_detected: number;
}

export async function parseFileStructured(file: File): Promise<FileAnalysisResult> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("analyze_structure", "true");
  return api.post("match/parse", { body: formData }).json<FileAnalysisResult>();
}

export async function smartUpload(
  file: File,
  opts: { supplierName?: string; supplierId?: string },
): Promise<BatchRequestAccepted> {
  const formData = new FormData();
  formData.append("file", file);
  if (opts.supplierName) formData.append("supplier_name", opts.supplierName);
  if (opts.supplierId) formData.append("supplier_id", opts.supplierId);
  return api.post("match/smart-upload", { body: formData }).json<BatchRequestAccepted>();
}

export async function previewGoogleSheet(url: string): Promise<{ rows: Record<string, unknown>[] }> {
  return api.get("match/google-sheet/preview", { searchParams: { url } }).json<{ rows: Record<string, unknown>[] }>();
}


export async function getMatchRequest(requestId: string): Promise<MatchRequestDetails> {
  return api.get(`match/requests/${requestId}`).json<MatchRequestDetails>();
}

export async function listMatchRequests(params?: {
  page?: number;
  limit?: number;
  supplier_id?: string;
  status?: string;
  created_after?: string;
}): Promise<{ items: MatchRequestDetails[], total?: number }> {
  const searchParams: Record<string, string | number> = {};
  if (params?.page != null) searchParams.page = params.page;
  if (params?.limit != null) searchParams.limit = params.limit;
  if (params?.supplier_id && params.supplier_id !== "__all__") searchParams.supplier_id = params.supplier_id;
  if (params?.status && params.status !== "all") searchParams.status = params.status;
  if (params?.created_after) searchParams.created_after = params.created_after;

  return api.get("match/requests", { searchParams }).json<{ items: MatchRequestDetails[], total?: number }>();
}

export async function deleteMatchRequest(requestId: string): Promise<{ ok: boolean }> {
  return api.delete(`match/requests/${requestId}`).json<{ ok: boolean }>();
}

export async function getMatchItems(
  requestId: string,
  params: { status?: string; page?: number; page_size?: number },
): Promise<MatchItemsPage> {
  const searchParams: Record<string, string | number> = {};
  if (params.status) searchParams.status = params.status;
  if (params.page != null) searchParams.page = params.page;
  if (params.page_size != null) searchParams.page_size = params.page_size;
  return api
    .get(`match/requests/${requestId}/items`, { searchParams })
    .json<MatchItemsPage>();
}

export async function getItemCandidates(
  requestItemId: string,
): Promise<{ request_item_id: string; candidates: Candidate[] }> {
  return api
    .get(`match/items/${requestItemId}/candidates`)
    .json<{ request_item_id: string; candidates: Candidate[] }>();
}
