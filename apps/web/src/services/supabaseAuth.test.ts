import { describe, it, expect } from 'vitest';
import { supabaseAuth } from './supabaseAuth';

describe('SupabaseAuthAdapter', () => {
  it('reports configuration status based on environment variables', () => {
    // In test environment without env vars, isConfigured returns false
    expect(typeof supabaseAuth.isConfigured()).toBe('boolean');
  });

  it('rejects empty phone input when requesting OTP', async () => {
    await expect(supabaseAuth.requestPhoneOtp('')).rejects.toThrow();
  });

  it('rejects empty OTP token when verifying OTP', async () => {
    await expect(supabaseAuth.verifyPhoneOtp('9800000001', '')).rejects.toThrow();
  });
});
