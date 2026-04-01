import api from "./client";

export interface CatalogProduct {
  product_id: string;
  name: string;
  article?: string;
  brand?: string;
  category_path?: string;
  is_active: boolean;
}

export interface CatalogStats {
  total_products: number;
  onec_connected: boolean;
}

export async function searchCatalog(query: string, limit: number = 50): Promise<CatalogProduct[]> {
  return api.get("catalog/products", { searchParams: { q: query, limit } }).json<CatalogProduct[]>();
}

export async function getCatalogStats(): Promise<CatalogStats> {
  return api.get("catalog/stats").json<CatalogStats>();
}

export async function importFromOnec(): Promise<{ job_id: string }> {
  return api.post("catalog/import", { json: { source_type: "onec_api" } }).json<{ job_id: string }>();
}

export async function uploadCatalogFile(file: File): Promise<{ job_id: string }> {
  const formData = new FormData();
  formData.append("file", file);
  return api.post("catalog/upload", { body: formData }).json<{ job_id: string }>();
}

export async function reindexCatalog(): Promise<{ job_id: string }> {
  return api.post("catalog/reindex", { json: {} }).json<{ job_id: string }>();
}
