/**
 * Auth state management.
 *
 * Auth is handled via httpOnly cookies (set by the backend on login).
 * The browser automatically sends the cookie on each request.
 * We maintain a lightweight in-memory flag to gate UI route access.
 */

let _authenticated = false;
let _mustChangePassword = false;
let _sessionExpiredCallback: (() => void) | null = null;

/** Called after successful login or /auth/me check */
export function setAuthenticated(value: boolean): void {
  _authenticated = value;
}

export function isAuthenticated(): boolean {
  return _authenticated;
}

export function setMustChangePassword(value: boolean): void {
  _mustChangePassword = value;
}

export function mustChangePassword(): boolean {
  return _mustChangePassword;
}

/** Register a callback for session expiry (called once per expiry event) */
export function onSessionExpired(cb: () => void): () => void {
  _sessionExpiredCallback = cb;
  return () => { _sessionExpiredCallback = null; };
}

/** Fire the session expired callback if registered */
export function notifySessionExpired(): void {
  if (_sessionExpiredCallback) {
    _sessionExpiredCallback();
  }
}

/** Read the CSRF token from the non-httpOnly cookie */
export function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}
