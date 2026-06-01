import ky from "ky";
import { getCsrfToken, setAuthenticated, isAuthenticated, notifySessionExpired } from "@/lib/auth-store";

const apiPrefixUrl =
  typeof window !== "undefined" ? `${window.location.origin}/api/v1` : "/api/v1";

const api = ky.create({
  prefixUrl: apiPrefixUrl,
  credentials: "include", // Send httpOnly cookies on every request
  timeout: 60000, // 60 seconds for LLM inference endpoints
  retry: {
    limit: 2,
    methods: ["get"],
    statusCodes: [408, 502, 503, 504],
  },
  hooks: {
    beforeRequest: [
      (request) => {
        // Attach CSRF token on mutating requests
        const method = request.method.toUpperCase();
        if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
          const csrf = getCsrfToken();
          if (csrf) {
            request.headers.set("X-CSRF-Token", csrf);
          }
        }
      },
    ],
    beforeError: [
      async (error) => {
        // Extract backend error detail for better error messages (GAP-9.6)
        const { response } = error;
        try {
          const body = await response.clone().json();
          if (body?.detail) {
            error.message = typeof body.detail === "string"
              ? body.detail
              : JSON.stringify(body.detail);
          } else if (body?.error) {
            error.message = body.error;
          }
        } catch {
          // Response is not JSON, keep original message
        }
        return error;
      },
    ],
    afterResponse: [
      async (request, _options, response) => {
        if (response.status === 401) {
          const wasAuth = isAuthenticated();
          setAuthenticated(false);
          const url = new URL(request.url);
          const isLoginEndpoint = url.pathname.includes("/auth/login");
          if (wasAuth && !isLoginEndpoint) {
            notifySessionExpired();
          }
        }
      },
    ],
  },
});

export default api;
