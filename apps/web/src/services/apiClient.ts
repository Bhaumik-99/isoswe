/**
 * Central API Client Abstraction
 *
 * Enforces:
 * - Bearer token injection
 * - Distributed request and correlation tracing (X-Request-ID, X-Correlation-ID)
 * - Standardized error unwrapping
 */

import { ApiErrorResponse } from '../types';
import { handleDemoApiRequest } from './demoMockBackend';
import { sessionManager } from './sessionManager';
import { supabaseAuth } from './supabaseAuth';

export class ApiClientError extends Error {
  code: string;
  requestId: string;
  status: number;
  details?: Record<string, unknown> | null;

  constructor(status: number, code: string, message: string, requestId: string, details?: Record<string, unknown> | null) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

class ApiClient {
  private baseUrl: string;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_URL || '';
  }

  setToken(token: string | null, expiresInSeconds?: number) {
    sessionManager.setSession(token, expiresInSeconds);
  }

  getToken(): string | null {
    return sessionManager.getToken();
  }

  private generateId(): string {
    return 'req-' + Math.random().toString(36).substring(2, 9) + '-' + Date.now();
  }

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const requestId = this.generateId();
    const correlationId = sessionStorage.getItem('correlation_id') || requestId;
    sessionStorage.setItem('correlation_id', correlationId);

    const isFormData = typeof FormData !== 'undefined' && options.body instanceof FormData;
    const headers: Record<string, string> = {
      ...(isFormData ? {} : { 'Content-Type': 'application/json' }),
      'X-Request-ID': requestId,
      'X-Correlation-ID': correlationId,
      ...(options.headers as Record<string, string>),
    };
    if (isFormData && headers['Content-Type']) {
      delete headers['Content-Type'];
    }

    const token = this.getToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const url = endpoint.startsWith('http') ? endpoint : `${this.baseUrl}${endpoint}`;

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      // Handle non-JSON or empty responses
      if (response.status === 204) {
        return {} as T;
      }

      const contentType = response.headers.get('content-type') || '';
      const isJson = contentType.includes('application/json');
      const data = isJson ? await response.json().catch(() => null) : null;

      // On static deployments (e.g. Vercel without backend proxy), /api/* may return index.html or 404/401.
      // When authenticated with a demo persona token, fall back to the stateful in-browser demo backend.
      if (token?.startsWith('dev-token-') && (!response.ok || !isJson || data === null)) {
        return handleDemoApiRequest<T>(endpoint, options, token);
      }

      if (!response.ok) {
        if (response.status === 401) {
          const isRetry = Boolean((headers as Record<string, string>)['X-Session-Retry']);
          if (!isRetry) {
            // Attempt automatic session recovery via Supabase refresh token
            const refreshed = await supabaseAuth.refreshSession();
            if (refreshed?.accessToken) {
              this.setToken(refreshed.accessToken, refreshed.expiresIn);
              return this.request<T>(endpoint, {
                ...options,
                headers: {
                  ...(options.headers as Record<string, string>),
                  'X-Session-Retry': 'true',
                },
              });
            }
          }

          // If session recovery fails or retry still returned 401, invalidate both in sync
          await supabaseAuth.signOut();
          sessionManager.clearSession();
          sessionManager.notifySessionExpired();
        }
        if (data && data.error) {
          const errData = data as ApiErrorResponse;
          throw new ApiClientError(
            response.status,
            errData.error.code,
            errData.error.message,
            errData.error.request_id || requestId,
            errData.error.details
          );
        }
        throw new ApiClientError(
          response.status,
          `HTTP_${response.status}`,
          response.statusText || 'Request failed',
          requestId
        );
      }

      return data as T;
    } catch (err: unknown) {
      if (token?.startsWith('dev-token-')) {
        return handleDemoApiRequest<T>(endpoint, options, token);
      }
      if (err instanceof ApiClientError) {
        throw err;
      }
      throw new ApiClientError(
        0,
        'NETWORK_ERROR',
        err instanceof Error ? err.message : 'Network connection failure',
        requestId
      );
    }
  }

  get<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'GET' });
  }

  post<T>(endpoint: string, body?: unknown, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  put<T>(endpoint: string, body?: unknown, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  patch<T>(endpoint: string, body?: unknown, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, {
      ...options,
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  delete<T>(endpoint: string, options?: RequestInit): Promise<T> {
    return this.request<T>(endpoint, { ...options, method: 'DELETE' });
  }
}

export const apiClient = new ApiClient();
