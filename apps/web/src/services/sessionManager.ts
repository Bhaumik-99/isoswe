/**
 * Cognito & In-Memory Session Manager
 *
 * Security Invariants:
 * 1. Tokens are kept in memory and ephemeral sessionStorage (tab-scoped only).
 * 2. Never stores raw bearer tokens in persistent localStorage (guards against XSS token harvesting).
 * 3. Enforces client-side token expiration timestamps.
 * 4. Dispatches session-expired events when tokens lapse or API returns 401.
 */

export interface SessionData {
  token: string;
  expiresAt: number | null; // Unix timestamp in ms
}

type SessionExpiredListener = () => void;

class SessionManager {
  private inMemoryToken: string | null = null;
  private inMemoryExpiresAt: number | null = null;
  private expiredListeners: SessionExpiredListener[] = [];
  private readonly SESSION_STORAGE_KEY = '__township_ephemeral_session';

  constructor() {
    this.hydrateFromSessionStorage();
  }

  private hydrateFromSessionStorage(): void {
    try {
      const raw = sessionStorage.getItem(this.SESSION_STORAGE_KEY);
      if (raw) {
        const parsed: SessionData = JSON.parse(raw);
        if (parsed.expiresAt && Date.now() > parsed.expiresAt) {
          this.clearSession();
        } else {
          this.inMemoryToken = parsed.token;
          this.inMemoryExpiresAt = parsed.expiresAt;
        }
      }
    } catch {
      this.clearSession();
    }
  }

  setSession(token: string | null, expiresInSeconds?: number): void {
    if (!token) {
      this.clearSession();
      return;
    }

    const expiresAt = expiresInSeconds ? Date.now() + expiresInSeconds * 1000 : null;
    this.inMemoryToken = token;
    this.inMemoryExpiresAt = expiresAt;

    try {
      const data: SessionData = { token, expiresAt };
      sessionStorage.setItem(this.SESSION_STORAGE_KEY, JSON.stringify(data));
    } catch {
      // Fallback to pure in-memory if sessionStorage is restricted
    }
  }

  getToken(): string | null {
    if (this.isExpired()) {
      this.clearSession();
      this.notifySessionExpired();
      return null;
    }
    return this.inMemoryToken;
  }

  isExpired(): boolean {
    if (!this.inMemoryToken) {
      return false;
    }
    if (this.inMemoryExpiresAt && Date.now() >= this.inMemoryExpiresAt) {
      return true;
    }
    return false;
  }

  clearSession(): void {
    this.inMemoryToken = null;
    this.inMemoryExpiresAt = null;
    try {
      sessionStorage.removeItem(this.SESSION_STORAGE_KEY);
      // Clean up legacy localStorage token if present
      localStorage.removeItem('auth_token');
    } catch {
      // Ignore storage errors on cleanup
    }
  }

  notifySessionExpired(): void {
    for (const listener of this.expiredListeners) {
      try {
        listener();
      } catch {
        // Prevent listener failures from breaking session cleanup
      }
    }
  }

  onSessionExpired(listener: SessionExpiredListener): () => void {
    this.expiredListeners.push(listener);
    return () => {
      this.expiredListeners = this.expiredListeners.filter((l) => l !== listener);
    };
  }
}

export const sessionManager = new SessionManager();
