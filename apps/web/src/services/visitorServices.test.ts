import { describe, it, expect, vi, beforeEach } from 'vitest';
import { getDictionary, PRIVACY_NOTICE_VERSION } from '../i18n/LanguageContext';
import { gateService, formatPhoneToE164, isValidIndianPhone } from './gateService';
import { residentVisitorService } from './residentVisitorService';
import { apiClient } from './apiClient';

describe('Phase 6 Tri-Lingual Localization & Visitor Services', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('provides complete English, Hindi, and Marathi dictionaries with statutory privacy version', () => {
    expect(PRIVACY_NOTICE_VERSION).toBe('v1.0-2026-pune');

    const en = getDictionary('en');
    const hi = getDictionary('hi');
    const mr = getDictionary('mr');

    expect(en.privacyNotice.version).toBe('v1.0-2026-pune');
    expect(hi.privacyNotice.version).toBe('v1.0-2026-pune');
    expect(mr.privacyNotice.version).toBe('v1.0-2026-pune');

    // Verify no empty strings in critical gate & resident sections across all 3 languages
    for (const dict of [en, hi, mr]) {
      expect(dict.gate.tabletTitle.length).toBeGreaterThan(3);
      expect(dict.gate.passVerification.offlineDisabledBody.length).toBeGreaterThan(10);
      expect(dict.privacyNotice.retentionBody.length).toBeGreaterThan(10);
      expect(dict.resident.pendingInbox.approveBtn.length).toBeGreaterThan(2);
      expect(dict.resident.guestPasses.generatedCodeBannerTitle.length).toBeGreaterThan(5);
    }
  });

  it('normalizes and validates Indian mobile phone numbers in E.164 format', () => {
    expect(formatPhoneToE164('9823011223')).toBe('+919823011223');
    expect(formatPhoneToE164('+91 98230 11223')).toBe('+919823011223');
    expect(isValidIndianPhone('9823011223')).toBe(true);
    expect(isValidIndianPhone('12345')).toBe(false);
  });

  it('sends normalized payload for gate visitor registration and pass verification', async () => {
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      visitor_id: 'v-1',
      visitor_name: 'Kiran Rao',
      phone_masked: '******1223',
      purpose: 'GUEST',
      destination_flat_id: 'flat-1',
      approval_status: 'PENDING',
      entry_status: 'EXPECTED',
      created_at: new Date().toISOString(),
    });

    await gateService.registerVisitor({
      visitor_name: '  Kiran Rao ',
      phone_number: '9823011223',
      vehicle_number: 'mh-12-ab-9999',
      purpose: 'GUEST',
      destination_flat_id: 'flat-1',
      privacy_notice_version: 'v1.0-2026-pune',
    });

    expect(postSpy).toHaveBeenCalledWith(
      '/api/v1/gate/visitors/register',
      expect.objectContaining({
        visitor_name: 'Kiran Rao',
        phone_number: '+919823011223',
        privacy_notice_version: 'v1.0-2026-pune',
      })
    );
  });

  it('calls resident approval action and guest pass endpoints with expected contract', async () => {
    const postSpy = vi.spyOn(apiClient, 'post').mockResolvedValue({
      visitor_id: 'v-1',
      approval_status: 'APPROVED',
      approved_at: new Date().toISOString(),
      action_by_user_id: 'u-1',
    });

    await residentVisitorService.actOnVisitor('v-1', 'APPROVE');
    expect(postSpy).toHaveBeenCalledWith('/api/v1/resident/visitors/v-1/action', {
      action: 'APPROVE',
      reason: undefined,
    });
  });
});

