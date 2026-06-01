import { beforeEach, describe, expect, it, vi } from "vitest";

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
}));

vi.mock("./client", () => ({
  default: apiMock,
}));

import { getMe, login, logout } from "./auth";
import {
  deleteCatalogProduct,
  getCatalogStats,
  getIndexVersions,
  importFromOnec,
  reindexCatalog,
  rollbackIndex,
  searchCatalog,
  uploadCatalogFile,
} from "./catalog";
import { getHealth } from "./health";
import {
  deleteMatchRequest,
  getItemCandidates,
  getMatchItems,
  getMatchRequest,
  getReviewQueue,
  listMatchRequests,
  matchBatch,
  matchSync,
  parseFilePreview,
  parseFileStructured,
  previewGoogleSheet,
  retryMatchRequest,
  smartUpload,
  uploadFile,
} from "./match";
import { getQualityHistory, getQualityMetrics, getTokenUsage } from "./metrics";
import { reviewBatch, reviewItem } from "./review";
import { getModels, getSettings, testOneCConnection, updateSettings } from "./settings";
import {
  createSupplier,
  createSupplierMapping,
  deleteSupplier,
  listSupplierMappings,
  listSuppliers,
  updateSupplier,
} from "./suppliers";
import {
  changePassword,
  createUser,
  forceChangePassword,
  listUsers,
  resetUserPassword,
  updateProfile,
  updateUser,
} from "./users";

function jsonResponse<T>(value: T) {
  return { json: vi.fn().mockResolvedValue(value) };
}

function textResponse(value = "") {
  return { text: vi.fn().mockResolvedValue(value) };
}

function expectFormData(call: unknown[], expected: Record<string, string | File>) {
  const body = (call[1] as { body: FormData }).body;
  expect(body).toBeInstanceOf(FormData);
  for (const [key, value] of Object.entries(expected)) {
    expect(body.get(key)).toEqual(value);
  }
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("auth api", () => {
  it("posts URL-encoded login data and reads auth endpoints", async () => {
    apiMock.post.mockReturnValueOnce(jsonResponse({ logged_in: true, must_change_password: false }));
    await expect(login("admin", "secret")).resolves.toEqual({
      logged_in: true,
      must_change_password: false,
    });
    const [, loginOptions] = apiMock.post.mock.calls[0];
    expect(apiMock.post).toHaveBeenCalledWith("auth/login", { body: expect.any(URLSearchParams) });
    expect((loginOptions.body as URLSearchParams).get("username")).toBe("admin");
    expect((loginOptions.body as URLSearchParams).get("password")).toBe("secret");

    apiMock.post.mockReturnValueOnce(textResponse());
    await expect(logout()).resolves.toBeUndefined();
    expect(apiMock.post).toHaveBeenLastCalledWith("auth/logout");

    apiMock.get.mockReturnValueOnce(jsonResponse({ user_id: "u1" }));
    await expect(getMe()).resolves.toEqual({ user_id: "u1" });
    expect(apiMock.get).toHaveBeenLastCalledWith("auth/me");
  });
});

describe("catalog api", () => {
  it("wraps catalog list, import, upload, delete, and rollback calls", async () => {
    apiMock.get.mockReturnValueOnce(jsonResponse([{ product_id: "p1" }]));
    await searchCatalog("pump", 25);
    expect(apiMock.get).toHaveBeenCalledWith("catalog/products", {
      searchParams: { q: "pump", limit: 25 },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ total_products: 1 }));
    await getCatalogStats();
    expect(apiMock.get).toHaveBeenLastCalledWith("catalog/stats");

    apiMock.post.mockReturnValueOnce(jsonResponse({ job_id: "j1" }));
    await importFromOnec();
    expect(apiMock.post).toHaveBeenLastCalledWith("catalog/import", {
      json: { source_type: "onec_api" },
    });

    const file = new File(["csv"], "catalog.csv", { type: "text/csv" });
    apiMock.post.mockReturnValueOnce(jsonResponse({ job_id: "j2" }));
    await uploadCatalogFile(file);
    expect(apiMock.post).toHaveBeenLastCalledWith("catalog/upload", { body: expect.any(FormData) });
    expectFormData(apiMock.post.mock.calls.at(-1)!, { file });

    apiMock.post.mockReturnValueOnce(jsonResponse({ job_id: "j3" }));
    await reindexCatalog();
    expect(apiMock.post).toHaveBeenLastCalledWith("catalog/reindex", { json: {} });

    apiMock.delete.mockReturnValueOnce(textResponse());
    await deleteCatalogProduct("p1");
    expect(apiMock.delete).toHaveBeenLastCalledWith("catalog/products/p1");

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await getIndexVersions();
    expect(apiMock.get).toHaveBeenLastCalledWith("catalog/index-versions");

    apiMock.post.mockReturnValueOnce(jsonResponse({ ok: true }));
    await rollbackIndex("idx1");
    expect(apiMock.post).toHaveBeenLastCalledWith("catalog/rollback", {
      json: { index_version_id: "idx1" },
    });
  });
});

describe("match api", () => {
  it("wraps sync, batch, file, smart upload, and request endpoints", async () => {
    const input = { items: [{ raw_text: "pump" }] };
    apiMock.post.mockReturnValueOnce(jsonResponse({ request_id: "r1" }));
    await matchSync(input);
    expect(apiMock.post).toHaveBeenLastCalledWith("match", { json: input });

    apiMock.post.mockReturnValueOnce(jsonResponse({ request_id: "r2" }));
    await matchBatch(input);
    expect(apiMock.post).toHaveBeenLastCalledWith("match/batch", { json: input });

    const file = new File(["xlsx"], "items.xlsx");
    apiMock.post.mockReturnValueOnce(jsonResponse({ request_id: "r3" }));
    await uploadFile(file, "supplier-1", true);
    expectFormData(apiMock.post.mock.calls.at(-1)!, {
      file,
      supplier_id: "supplier-1",
      use_ai_column_picker: "true",
    });

    apiMock.post.mockReturnValueOnce(jsonResponse({ request_id: "r4" }));
    await uploadFile(file, "__all__");
    const uploadAllBody = apiMock.post.mock.calls.at(-1)![1].body as FormData;
    expect(uploadAllBody.get("supplier_id")).toBeNull();

    apiMock.post.mockReturnValueOnce(jsonResponse({ items: [] }));
    await parseFilePreview(file, true);
    expectFormData(apiMock.post.mock.calls.at(-1)!, { file, use_ai_column_picker: "true" });

    apiMock.post.mockReturnValueOnce(jsonResponse({ mode: "structured" }));
    await parseFileStructured(file);
    expectFormData(apiMock.post.mock.calls.at(-1)!, { file, analyze_structure: "true" });

    apiMock.post.mockReturnValueOnce(jsonResponse({ request_id: "r5" }));
    await smartUpload(file, { supplierName: "Supplier", supplierId: "s1" });
    expectFormData(apiMock.post.mock.calls.at(-1)!, {
      file,
      supplier_name: "Supplier",
      supplier_id: "s1",
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ rows: [] }));
    await previewGoogleSheet("https://docs.example/sheet");
    expect(apiMock.get).toHaveBeenLastCalledWith("match/google-sheet/preview", {
      searchParams: { url: "https://docs.example/sheet" },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ request_id: "r1" }));
    await getMatchRequest("r1");
    expect(apiMock.get).toHaveBeenLastCalledWith("match/requests/r1");

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await listMatchRequests({
      page: 2,
      limit: 10,
      supplier_id: "__all__",
      status: "all",
      created_after: "2026-01-01",
    });
    expect(apiMock.get).toHaveBeenLastCalledWith("match/requests", {
      searchParams: { page: 2, limit: 10, created_after: "2026-01-01" },
    });

    apiMock.delete.mockReturnValueOnce(jsonResponse({ ok: true }));
    await deleteMatchRequest("r1");
    expect(apiMock.delete).toHaveBeenLastCalledWith("match/requests/r1");

    apiMock.post.mockReturnValueOnce(jsonResponse({ ok: true }));
    await retryMatchRequest("r1");
    expect(apiMock.post).toHaveBeenLastCalledWith("match/requests/r1/retry");

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await getMatchItems("r1", { status: "review_needed", page: 3, page_size: 20 });
    expect(apiMock.get).toHaveBeenLastCalledWith("match/requests/r1/items", {
      searchParams: { status: "review_needed", page: 3, page_size: 20 },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ candidates: [] }));
    await getItemCandidates("item1");
    expect(apiMock.get).toHaveBeenLastCalledWith("match/items/item1/candidates");

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await getReviewQueue({ supplier_id: "s1", page: 1, page_size: 5 });
    expect(apiMock.get).toHaveBeenLastCalledWith("match/review-queue", {
      searchParams: { supplier_id: "s1", page: 1, page_size: 5 },
    });
  });

  it("omits optional match params and fields when they are absent or defaults", async () => {
    const file = new File(["xlsx"], "items.xlsx");

    apiMock.post.mockReturnValueOnce(jsonResponse({ items: [] }));
    await parseFilePreview(file);
    const previewBody = apiMock.post.mock.calls.at(-1)![1].body as FormData;
    expect(previewBody.get("file")).toEqual(file);
    expect(previewBody.get("use_ai_column_picker")).toBeNull();

    apiMock.post.mockReturnValueOnce(jsonResponse({ request_id: "r1" }));
    await smartUpload(file, {});
    const smartUploadBody = apiMock.post.mock.calls.at(-1)![1].body as FormData;
    expect(smartUploadBody.get("file")).toEqual(file);
    expect(smartUploadBody.get("supplier_name")).toBeNull();
    expect(smartUploadBody.get("supplier_id")).toBeNull();

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await listMatchRequests({ supplier_id: "s1", status: "completed" });
    expect(apiMock.get).toHaveBeenLastCalledWith("match/requests", {
      searchParams: { supplier_id: "s1", status: "completed" },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await getMatchItems("r1", {});
    expect(apiMock.get).toHaveBeenLastCalledWith("match/requests/r1/items", {
      searchParams: {},
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await getReviewQueue();
    expect(apiMock.get).toHaveBeenLastCalledWith("match/review-queue", {
      searchParams: {},
    });
  });
});

describe("metrics, settings, review, supplier, user, and health apis", () => {
  it("builds request payloads and query params for the remaining modules", async () => {
    apiMock.get.mockReturnValueOnce(jsonResponse({ status: "ok" }));
    await getHealth();
    expect(apiMock.get).toHaveBeenLastCalledWith("health");

    apiMock.get.mockReturnValueOnce(jsonResponse({ total_cases: 0 }));
    await getQualityMetrics({ supplier_id: "s1", category_id: "c1" });
    expect(apiMock.get).toHaveBeenLastCalledWith("metrics/quality", {
      searchParams: { supplier_id: "s1", category_id: "c1" },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ daily: [] }));
    await getTokenUsage(7, "local");
    expect(apiMock.get).toHaveBeenLastCalledWith("metrics/tokens", {
      searchParams: { days: "7", provider: "local" },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await getQualityHistory({ supplier_id: "s1", days: 14 });
    expect(apiMock.get).toHaveBeenLastCalledWith("metrics/quality/history", {
      searchParams: { supplier_id: "s1", days: "14" },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ total_cases: 0 }));
    await getQualityMetrics();
    expect(apiMock.get).toHaveBeenLastCalledWith("metrics/quality", {
      searchParams: {},
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ total_cases: 0 }));
    await getQualityMetrics({ category_id: "c2" });
    expect(apiMock.get).toHaveBeenLastCalledWith("metrics/quality", {
      searchParams: { category_id: "c2" },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ daily: [] }));
    await getTokenUsage();
    expect(apiMock.get).toHaveBeenLastCalledWith("metrics/tokens", {
      searchParams: { days: "30" },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await getQualityHistory({ category_id: "c2" });
    expect(apiMock.get).toHaveBeenLastCalledWith("metrics/quality/history", {
      searchParams: { category_id: "c2" },
    });

    apiMock.post.mockReturnValueOnce(jsonResponse({ ok: true }));
    await reviewItem("item1", { final_decision: "accepted" });
    expect(apiMock.post).toHaveBeenLastCalledWith("review/items/item1", {
      json: { final_decision: "accepted" },
    });

    apiMock.post.mockReturnValueOnce(jsonResponse({ ok: true, processed_count: 1 }));
    await reviewBatch([{ request_item_id: "item1", final_decision: "rejected" }]);
    expect(apiMock.post).toHaveBeenLastCalledWith("review/batch", {
      json: { items: [{ request_item_id: "item1", final_decision: "rejected" }] },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ llm_provider: "local" }));
    await getSettings();
    expect(apiMock.get).toHaveBeenLastCalledWith("settings");

    apiMock.put.mockReturnValueOnce(jsonResponse({ llm_provider: "openai" }));
    await updateSettings({ llm_provider: "openai" });
    expect(apiMock.put).toHaveBeenLastCalledWith("settings", {
      json: { llm_provider: "openai" },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ models: [] }));
    await getModels("openrouter");
    const modelsParams = apiMock.get.mock.calls.at(-1)![1].searchParams as URLSearchParams;
    expect(apiMock.get.mock.calls.at(-1)![0]).toBe("settings/models");
    expect(modelsParams.get("provider_id")).toBe("openrouter");

    apiMock.get.mockReturnValueOnce(jsonResponse({ models: [] }));
    await getModels();
    const defaultModelsParams = apiMock.get.mock.calls.at(-1)![1].searchParams as URLSearchParams;
    expect(apiMock.get.mock.calls.at(-1)![0]).toBe("settings/models");
    expect(defaultModelsParams.get("provider_id")).toBeNull();

    apiMock.post.mockReturnValueOnce(jsonResponse({ status: "ok" }));
    await testOneCConnection();
    expect(apiMock.post).toHaveBeenLastCalledWith("settings/test-onec");

    apiMock.post.mockReturnValueOnce(jsonResponse({ supplier_id: "s1" }));
    await createSupplier({ supplier_id: "s1", supplier_name: "Supplier", strict_mode: false });
    expect(apiMock.post).toHaveBeenLastCalledWith("suppliers", {
      json: { supplier_id: "s1", supplier_name: "Supplier", strict_mode: false },
    });

    apiMock.put.mockReturnValueOnce(jsonResponse({ supplier_id: "s1" }));
    await updateSupplier("s1", { is_active: false });
    expect(apiMock.put).toHaveBeenLastCalledWith("suppliers/s1", { json: { is_active: false } });

    apiMock.post.mockReturnValueOnce(jsonResponse({ ok: true }));
    await createSupplierMapping("s1", { product_id: "p1", mapping_type: "manual" });
    expect(apiMock.post).toHaveBeenLastCalledWith("suppliers/s1/mappings", {
      json: { product_id: "p1", mapping_type: "manual" },
    });

    apiMock.delete.mockReturnValueOnce(jsonResponse({ ok: true }));
    await deleteSupplier("s1");
    expect(apiMock.delete).toHaveBeenLastCalledWith("suppliers/s1");

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [{ product_id: "p1" }] }));
    await expect(listSupplierMappings("s1", 5)).resolves.toEqual([{ product_id: "p1" }]);
    expect(apiMock.get).toHaveBeenLastCalledWith("suppliers/s1/mappings", {
      searchParams: { limit: 5 },
    });

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await listSuppliers();
    expect(apiMock.get).toHaveBeenLastCalledWith("suppliers");

    apiMock.get.mockReturnValueOnce(jsonResponse({ items: [] }));
    await listUsers();
    expect(apiMock.get).toHaveBeenLastCalledWith("users");

    apiMock.post.mockReturnValueOnce(jsonResponse({ user_id: "u1" }));
    await createUser({ username: "u", role: "admin", password: "p" });
    expect(apiMock.post).toHaveBeenLastCalledWith("users", {
      json: { username: "u", role: "admin", password: "p" },
    });

    apiMock.put.mockReturnValueOnce(jsonResponse({ user_id: "u1" }));
    await updateUser("u1", { is_active: false });
    expect(apiMock.put).toHaveBeenLastCalledWith("users/u1", { json: { is_active: false } });

    apiMock.post.mockReturnValueOnce(jsonResponse({ ok: true }));
    await resetUserPassword("u1", "new");
    expect(apiMock.post).toHaveBeenLastCalledWith("users/u1/reset-password", {
      json: { new_password: "new" },
    });

    apiMock.put.mockReturnValueOnce(jsonResponse({ user_id: "u1", full_name: null }));
    await updateProfile(null);
    expect(apiMock.put).toHaveBeenLastCalledWith("auth/profile", {
      json: { full_name: null },
    });

    apiMock.post.mockReturnValueOnce(jsonResponse({ ok: true }));
    await changePassword("old", "new");
    expect(apiMock.post).toHaveBeenLastCalledWith("auth/change-password", {
      json: { current_password: "old", new_password: "new" },
    });

    apiMock.post.mockReturnValueOnce(jsonResponse({ ok: true }));
    await forceChangePassword("new");
    expect(apiMock.post).toHaveBeenLastCalledWith("auth/force-change-password", {
      json: { new_password: "new" },
    });
  });
});
