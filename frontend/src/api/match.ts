import api from "./client";
import type {
  BatchRequestAccepted,
  Candidate,
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

export async function getMatchRequest(requestId: string): Promise<MatchRequestDetails> {
  return api.get(`match/requests/${requestId}`).json<MatchRequestDetails>();
}

export async function listMatchRequests(): Promise<{ items: MatchRequestDetails[] }> {
  return api.get("match/requests").json<{ items: MatchRequestDetails[] }>();
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
