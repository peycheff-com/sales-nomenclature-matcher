import api from "./client";
import type { SupplierProfile } from "./types";

export interface SupplierCreate {
  supplier_id: string;
  supplier_name: string;
  strict_mode: boolean;
}

export interface SupplierUpdate {
  supplier_name?: string;
  strict_mode?: boolean;
  is_active?: boolean;
}

export async function createSupplier(input: SupplierCreate): Promise<SupplierProfile> {
  return api.post("suppliers", { json: input }).json<SupplierProfile>();
}

export async function updateSupplier(supplierId: string, input: SupplierUpdate): Promise<SupplierProfile> {
  return api.put(`suppliers/${supplierId}`, { json: input }).json<SupplierProfile>();
}

export interface SupplierMappingCreate {
  supplier_sku?: string;
  supplier_article?: string;
  supplier_raw_text?: string;
  product_id: string;
  mapping_type: string;
  confidence?: number;
}

export async function createSupplierMapping(
  supplierId: string,
  data: SupplierMappingCreate,
) {
  return api.post(`suppliers/${supplierId}/mappings`, { json: data }).json();
}

// Ensure legacy list endpoint is wrapped:
export async function listSuppliers(): Promise<{ items: SupplierProfile[] }> {
    return api.get("suppliers").json<{ items: SupplierProfile[] }>();
}
