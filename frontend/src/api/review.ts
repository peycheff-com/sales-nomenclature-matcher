import api from "./client";
import type { ReviewInput } from "./types";

export async function reviewItem(
  requestItemId: string,
  input: ReviewInput,
): Promise<{ ok: boolean }> {
  return api.post(`review/items/${requestItemId}`, { json: input }).json();
}
