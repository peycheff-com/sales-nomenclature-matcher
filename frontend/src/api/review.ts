import api from "./client";
import type { ReviewInput } from "./types";

export async function reviewItem(
  requestItemId: string,
  input: ReviewInput,
): Promise<{ ok: boolean }> {
  return api.post(`review/items/${requestItemId}`, { json: input }).json();
}

export interface BatchReviewItem {
  request_item_id: string;
  final_decision: "accepted" | "corrected" | "rejected";
  final_product_id?: string;
  comment?: string;
  create_alias?: boolean;
  create_supplier_mapping?: boolean;
}

export async function reviewBatch(items: BatchReviewItem[]): Promise<{ ok: boolean; processed_count: number }> {
  return api.post("review/batch", { json: { items } }).json();
}
