export const AUTH_SESSION_EXPIRED_EVENT = "pla:auth-session-expired";

export function notifyAuthSessionExpired(): void {
  window.dispatchEvent(new CustomEvent(AUTH_SESSION_EXPIRED_EVENT));
}

export function subscribeAuthSessionExpired(handler: () => void): () => void {
  window.addEventListener(AUTH_SESSION_EXPIRED_EVENT, handler);
  return () => window.removeEventListener(AUTH_SESSION_EXPIRED_EVENT, handler);
}
