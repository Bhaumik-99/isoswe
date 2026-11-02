/**
 * Genuine Supabase Authentication Adapter
 *
 * Implements passwordless Phone OTP authentication via official @supabase/supabase-js:
 * 1. Dispatches SMS OTP via supabase.auth.signInWithOtp({ phone }).
 * 2. Verifies 6-digit OTP code via supabase.auth.verifyOtp({ phone, token, type: 'sms' }).
 * 3. Extracts genuine bearer JWT access token for FastAPI backend communication.
 * 4. Fails closed when required Supabase configuration is missing in non-development environments.
 */

import { createClient, SupabaseClient } from '@supabase/supabase-js';

export interface SupabaseTokens {
  accessToken: string;
  expiresIn?: number;
  userId?: string;
  phone?: string;
}

export class SupabaseAuthError extends Error {
  code: string;

  constructor(message: string, code: string = 'SUPABASE_AUTH_ERROR') {
    super(message);
    this.name = 'SupabaseAuthError';
    this.code = code;
  }
}

export class SupabaseAuthAdapter {
  private supabase: SupabaseClient | null = null;
  private supabaseUrl: string;
  private publishableKey: string;

  constructor() {
    this.supabaseUrl = import.meta.env.VITE_SUPABASE_URL || '';
    this.publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY || '';

    if (this.supabaseUrl && this.publishableKey) {
      this.supabase = createClient(this.supabaseUrl, this.publishableKey, {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: false,
        },
      });
    }
  }

  isConfigured(): boolean {
    return Boolean(this.supabaseUrl && this.publishableKey && this.supabase);
  }

  getSupabaseClient(): SupabaseClient {
    if (!this.supabase) {
      if (import.meta.env.DEV) {
        throw new SupabaseAuthError(
          'Supabase client configuration (VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY) is not set. For local testing without live Supabase, please use the "Local Dev Personas" tab with seeded test accounts.',
          'SUPABASE_NOT_CONFIGURED_DEV'
        );
      }
      throw new SupabaseAuthError(
        'Authentication service is temporarily unavailable. Missing identity provider configuration.',
        'IDENTITY_PROVIDER_UNAVAILABLE'
      );
    }
    return this.supabase;
  }

  /**
   * Formats a mobile number to E.164 format (+91 for India by default).
   */
  private formatPhoneNumber(input: string): string {
    const cleaned = input.trim().replace(/[\s-]/g, '');
    if (!cleaned) {
      throw new SupabaseAuthError('Please provide a valid mobile phone number', 'INVALID_INPUT');
    }
    if (cleaned.startsWith('+')) {
      return cleaned;
    }
    // Default to +91 for Indian phone numbers if standard 10 digits
    if (/^\d{10}$/.test(cleaned)) {
      return `+91${cleaned}`;
    }
    return `+${cleaned}`;
  }

  /**
   * Dispatches SMS OTP challenge initiation via Supabase Auth.
   */
  async requestPhoneOtp(phoneNumber: string): Promise<{ phone: string }> {
    const formattedPhone = this.formatPhoneNumber(phoneNumber);
    const client = this.getSupabaseClient();

    const { error } = await client.auth.signInWithOtp({
      phone: formattedPhone,
    });

    if (error) {
      throw new SupabaseAuthError(error.message, error.status?.toString() || 'OTP_REQUEST_FAILED');
    }

    return { phone: formattedPhone };
  }

  /**
   * Submits user-entered 6-digit OTP code to complete authentication and retrieve signed JWT.
   */
  async verifyPhoneOtp(phoneNumber: string, otpToken: string): Promise<SupabaseTokens> {
    const formattedPhone = this.formatPhoneNumber(phoneNumber);
    const cleanToken = otpToken.trim();

    if (!cleanToken || cleanToken.length < 4) {
      throw new SupabaseAuthError('Please enter a valid OTP verification code', 'INVALID_OTP');
    }

    const client = this.getSupabaseClient();

    const { data, error } = await client.auth.verifyOtp({
      phone: formattedPhone,
      token: cleanToken,
      type: 'sms',
    });

    if (error || !data.session?.access_token) {
      throw new SupabaseAuthError(
        error?.message || 'Invalid or expired verification code. Please request a new code.',
        'INVALID_OTP'
      );
    }

    return {
      accessToken: data.session.access_token,
      expiresIn: data.session.expires_in,
      userId: data.user?.id,
      phone: data.user?.phone,
    };
  }

  /**
   * Retrieves current active Supabase session if present.
   */
  async getSession(): Promise<{ accessToken: string; expiresIn?: number } | null> {
    if (!this.supabase) {
      return null;
    }
    const { data } = await this.supabase.auth.getSession();
    if (data.session?.access_token) {
      return {
        accessToken: data.session.access_token,
        expiresIn: data.session.expires_in,
      };
    }
    return null;
  }

  /**
   * Subscribes to Supabase authentication state events (TOKEN_REFRESHED, SIGNED_OUT, etc.).
   */
  onAuthStateChange(
    callback: (
      event: string,
      session: { access_token?: string; expires_in?: number } | null
    ) => void
  ): (() => void) | undefined {
    if (!this.supabase) {
      return undefined;
    }
    const { data } = this.supabase.auth.onAuthStateChange((event, session) => {
      callback(
        event,
        session ? { access_token: session.access_token, expires_in: session.expires_in } : null
      );
    });
    return () => data.subscription.unsubscribe();
  }

  /**
   * Signs out from Supabase Auth.
   */
  async signOut(): Promise<void> {
    if (this.supabase) {
      await this.supabase.auth.signOut();
    }
  }
}

export const supabaseAuth = new SupabaseAuthAdapter();
