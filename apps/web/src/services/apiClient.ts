/**
 * Central API Client Abstraction
 *
 * Enforces:
 * - Bearer token injection
 * - Distributed request and correlation tracing (X-Request-ID, X-Correlation-ID)
 * - Standardized error unwrapping
 */

import { ApiErrorResponse } from '../types';

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
  private token: string | null = null;

  constructor() {
    this.baseUrl = import.meta.env.VITE_API_URL || '';
    // Check localStorage for saved session token
    this.token = localStorage.getItem('auth_token');
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('auth_token', token);
    } else {
      localStorage.removeItem('auth_token');
    }
  }

  getToken(): string | null {
    return this.token;
  }

  private generateId(): string {
    return 'req-' + Math.random().toString(36).substring(2, 9) + '-' + Date.now();
  }

  async request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
    const requestId = this.generateId();
    const correlationId = sessionStorage.getItem('correlation_id') || requestId;
    sessionStorage.setItem('correlation_id', correlationId);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'X-Request-ID': requestId,
      'X-Correlation-ID': correlationId,
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
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

      const data = await response.json().catch(() => null);

      if (!response.ok) {
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
}

export const apiClient = new ApiClient();
