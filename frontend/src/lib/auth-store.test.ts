import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getCsrfToken,
  isAuthenticated,
  mustChangePassword,
  notifySessionExpired,
  onSessionExpired,
  setAuthenticated,
  setMustChangePassword,
} from "./auth-store";

function clearCookies() {
  document.cookie.split(";").forEach((cookie) => {
    const name = cookie.split("=")[0]?.trim();
    if (name) {
      document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
    }
  });
}

afterEach(() => {
  setAuthenticated(false);
  setMustChangePassword(false);
  onSessionExpired(() => undefined)();
  clearCookies();
});

describe("auth-store", () => {
  it("tracks in-memory authentication state", () => {
    expect(isAuthenticated()).toBe(false);

    setAuthenticated(true);
    expect(isAuthenticated()).toBe(true);

    setAuthenticated(false);
    expect(isAuthenticated()).toBe(false);
  });

  it("tracks force-password-change state", () => {
    expect(mustChangePassword()).toBe(false);

    setMustChangePassword(true);
    expect(mustChangePassword()).toBe(true);
  });

  it("notifies and unregisters session-expiry callbacks", () => {
    const callback = vi.fn();
    const unsubscribe = onSessionExpired(callback);

    notifySessionExpired();
    expect(callback).toHaveBeenCalledTimes(1);

    unsubscribe();
    notifySessionExpired();
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it("reads and decodes the CSRF cookie", () => {
    document.cookie = "csrf_token=token%20value; path=/";

    expect(getCsrfToken()).toBe("token value");
  });

  it("returns null when the CSRF cookie is absent", () => {
    expect(getCsrfToken()).toBeNull();
  });
});
