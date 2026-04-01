import ky from "ky";
import { getCsrfToken, setAuthenticated } from "@/lib/auth-store";

const api = ky.create({
  prefixUrl: "/api/v1",
  credentials: "include", // Send httpOnly cookies on every request
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
    afterResponse: [
      async (_request, _options, response) => {
        if (response.status === 401) {
          setAuthenticated(false);
          // Don't hard-redirect here — the router's beforeLoad guards
          // handle redirection. A hard reload would reset in-memory
          // auth state and cause an infinite redirect loop.
        }
      },
    ],
  },
});

export default api;
