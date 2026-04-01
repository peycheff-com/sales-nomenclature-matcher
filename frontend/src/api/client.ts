import ky from "ky";
import { getCsrfToken, setAuthenticated } from "@/lib/auth-store";

const api = ky.create({
  prefixUrl: "/api/v1",
  credentials: "include", // Send httpOnly cookies on every request
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
          window.location.href = "/login";
        }
      },
    ],
  },
});

export default api;
