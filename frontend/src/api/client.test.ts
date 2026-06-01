import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import api from "./client";
import {
  isAuthenticated,
  onSessionExpired,
  setAuthenticated,
  setMustChangePassword,
} from "@/lib/auth-store";

function clearCookies() {
  document.cookie.split(";").forEach((cookie) => {
    const name = cookie.split("=")[0]?.trim();
    if (name) {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
    }
  });
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  setAuthenticated(false);
  setMustChangePassword(false);
  clearCookies();
});

afterEach(() => {
  vi.unstubAllGlobals();
  onSessionExpired(() => undefined)();
  setAuthenticated(false);
  setMustChangePassword(false);
  clearCookies();
});

describe("api client", () => {
  it("attaches CSRF tokens only to mutating requests", async () => {
    document.cookie = "csrf_token=csrf-123; path=/";
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => jsonResponse({ ok: true }));

    await api.post("match", { json: { items: [] } }).json();
    const postRequest = fetchMock.mock.calls[0][0] as Request;
    expect(postRequest.url).toBe("http://localhost:3000/api/v1/match");
    expect(postRequest.headers.get("X-CSRF-Token")).toBe("csrf-123");

    await api.get("health").json();
    const getRequest = fetchMock.mock.calls[1][0] as Request;
    expect(getRequest.headers.get("X-CSRF-Token")).toBeNull();
  });

  it("does not attach empty CSRF tokens to mutating requests", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementation(async () => jsonResponse({ ok: true }));

    await api.delete("match/request-1").json();

    const deleteRequest = fetchMock.mock.calls[0][0] as Request;
    expect(deleteRequest.headers.get("X-CSRF-Token")).toBeNull();
  });

  it("uses backend detail or error fields as thrown error messages", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "plain detail" }, 400));

    await expect(api.get("match").json()).rejects.toThrow("plain detail");

    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: { field: "bad" } }, 400));

    await expect(api.get("match").json()).rejects.toThrow('{"field":"bad"}');

    fetchMock.mockResolvedValueOnce(jsonResponse({ error: "plain backend error" }, 500));

    await expect(api.get("match").json()).rejects.toThrow("plain backend error");
  });

  it("keeps original error messages for non-json backend errors", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(
      new Response("not json", {
        status: 500,
        headers: { "Content-Type": "text/plain" },
      }),
    );

    await expect(api.get("match").json()).rejects.toThrow(
      "Request failed with status code 500",
    );
  });

  it("marks auth false and notifies once for expired non-login sessions", async () => {
    const callback = vi.fn();
    onSessionExpired(callback);
    setAuthenticated(true);
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "expired" }, 401));

    await expect(api.get("auth/me").json()).rejects.toThrow("expired");

    expect(isAuthenticated()).toBe(false);
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("does not emit a session-expired notification when already anonymous", async () => {
    const callback = vi.fn();
    onSessionExpired(callback);
    setAuthenticated(false);
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(jsonResponse({}, 401));

    await expect(api.get("auth/me").json()).rejects.toThrow(
      "Request failed with status code 401",
    );

    expect(isAuthenticated()).toBe(false);
    expect(callback).not.toHaveBeenCalled();
  });

  it("does not emit a session-expired notification for login failures", async () => {
    const callback = vi.fn();
    onSessionExpired(callback);
    setAuthenticated(true);
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "bad credentials" }, 401));

    await expect(api.post("auth/login", { body: new URLSearchParams() }).json()).rejects.toThrow(
      "bad credentials",
    );

    expect(isAuthenticated()).toBe(false);
    expect(callback).not.toHaveBeenCalled();
  });

  it("uses a relative API prefix when window is unavailable", async () => {
    vi.resetModules();
    vi.stubGlobal("window", undefined);

    const { default: ssrApi } = await import("./client");

    expect(ssrApi).toBeDefined();
  });
});
