import api from "./client";
import type { HealthResponse } from "./types";

export async function getHealth(): Promise<HealthResponse> {
  return api.get("health").json<HealthResponse>();
}
