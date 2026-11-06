import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  buildCanonicalPayloadString,
  clearAllOfflineQueue,
  computePayloadHash,
  enqueueOfflineVisitor,
  evaluateOfflineGuestPassPolicy,
  generateClientEventId,
  listOfflineQueue,
  removeSyncedOfflineItems,
} from './gateIndexedDB';
import { gateSyncManager } from './syncManager';
import { gateService } from '../../../services/gateService';

describe('Gate Offline IndexedDB & Replay-Protected Sync Engine', () => {
  beforeEach(async () => {
    await clearAllOfflineQueue();
    vi.restoreAllMocks();
  });

  it('generates valid UUIDv4 client_event_id identifiers', () => {
    const id1 = generateClientEventId();
    const id2 = generateClientEventId();
    expect(id1).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i
    );
    expect(id1).not.toBe(id2);
  });

  it('computes deterministic canonical SHA-256 payload hash and detects tampering', async () => {
    const baseInput = {
      visitor_name: 'Ramesh Pawar',
      phone_number: '+919823011223',
      vehicle_number: 'MH-12-AB-1234',
      purpose: 'DELIVERY',
      destination_flat_id: '70000000-0000-4000-a000-000000000701',
      privacy_notice_version: 'v1.0-2026-pune',
    };

    const canonical = buildCanonicalPayloadString(baseInput);
    expect(canonical).toBe(
      'name:Ramesh Pawar|phone:+919823011223|vehicle:MH-12-AB-1234|purpose:DELIVERY|flat:70000000-0000-4000-a000-000000000701|notice:v1.0-2026-pune'
    );

    const hash1 = await computePayloadHash(baseInput);
    const hash2 = await computePayloadHash({
      ...baseInput,
      visitor_name: '  Ramesh Pawar ',
    });
    expect(hash1).toBe(hash2);

    const tamperedFlatHash = await computePayloadHash({
      ...baseInput,
      destination_flat_id: '70000000-0000-4000-a000-000000001201',
    });
    expect(tamperedFlatHash).not.toBe(hash1);
  });

  it('enqueues offline visitor strictly with PENDING approval and survives reload reads', async () => {
    const gateId = '60000000-0000-4000-a000-000000000001';
    const flatId = '70000000-0000-4000-a000-000000000701';

    const item = await enqueueOfflineVisitor({
      gate_id: gateId,
      visitor_name: 'Suresh Kulkarni',
      phone_number: '9823099887',
      vehicle_number: 'MH12XY9999',
      purpose: 'GUEST',
      destination_flat_id: flatId,
      flat_label: 'T07-1203',
      photo_base64: 'data:image/jpeg;base64,/9j/4AAQSkZJRg==',
      privacy_notice_version: 'v1.0-2026-pune',
    });

    expect(item.approval_status).toBe('PENDING');
    expect(item.entry_status).toBe('EXPECTED');
    expect(item.sync_status).toBe('QUEUED');
    expect(item.phone_number).toBe('+919823099887');

    const persisted = await listOfflineQueue(gateId);
    expect(persisted).toHaveLength(1);
    expect(persisted[0].client_event_id).toBe(item.client_event_id);
    expect(persisted[0].approval_status).toBe('PENDING');
  });

  it('enforces fail-closed policy on guest pass verification when tablet is offline', () => {
    const offlineCheck = evaluateOfflineGuestPassPolicy(false);
    expect(offlineCheck.allowed).toBe(false);
    expect(offlineCheck.code).toBe('FAIL_CLOSED_OFFLINE_GUEST_PASS');

    const onlineCheck = evaluateOfflineGuestPassPolicy(true);
    expect(onlineCheck.allowed).toBe(true);
    expect(onlineCheck.code).toBe('ONLINE_ALLOWED');
  });

  it('processes partial batch sync results isolating ACK, CONFLICT, and ERROR items', async () => {
    const gateId = '60000000-0000-4000-a000-000000000001';
    const flatId = '70000000-0000-4000-a000-000000000701';

    const ev1 = await enqueueOfflineVisitor({
      gate_id: gateId,
      visitor_name: 'Valid Visitor',
      phone_number: '9823011111',
      purpose: 'DELIVERY',
      destination_flat_id: flatId,
      privacy_notice_version: 'v1.0-2026-pune',
    });

    const ev2 = await enqueueOfflineVisitor({
      gate_id: gateId,
      visitor_name: 'Tampered Visitor',
      phone_number: '9823022222',
      purpose: 'CAB',
      destination_flat_id: flatId,
      privacy_notice_version: 'v1.0-2026-pune',
    });

    vi.spyOn(gateService, 'syncOfflineBatch').mockResolvedValueOnce({
      gate_id: gateId,
      processed_count: 1,
      results: [
        {
          client_event_id: ev1.client_event_id,
          status: 'ACK',
          visitor_id: '80000000-0000-4000-a000-000000000099',
          approval_status: 'PENDING',
        },
        {
          client_event_id: ev2.client_event_id,
          status: 'CONFLICT',
          error_message: 'CONFLICT_EVENT_PAYLOAD_MODIFIED',
        },
      ],
    });

    const summary = await gateSyncManager.syncGateQueue(gateId);
    expect(summary.totalAttempted).toBe(2);
    expect(summary.acknowledged).toBe(1);
    expect(summary.conflicts).toBe(1);
    expect(summary.failed).toBe(0);

    const removed = await removeSyncedOfflineItems(gateId);
    expect(removed).toBe(1);

    const remaining = await listOfflineQueue(gateId);
    expect(remaining).toHaveLength(1);
    expect(remaining[0].client_event_id).toBe(ev2.client_event_id);
    expect(remaining[0].sync_status).toBe('CONFLICT');
  });
});

