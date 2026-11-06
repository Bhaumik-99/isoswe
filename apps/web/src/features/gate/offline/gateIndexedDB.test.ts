import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  GATE_DB_VERSION,
  MASTER_KEY_ID,
  buildCanonicalPayloadString,
  clearAllOfflineQueue,
  computePayloadHash,
  computePhotoSha256,
  countLegacyPlaintextRecords,
  decryptSensitivePayload,
  encryptSensitivePayload,
  enqueueOfflineVisitor,
  evaluateOfflineGuestPassPolicy,
  generateClientEventId,
  getGateMigrationStatus,
  getOrCreateGateEncryptionKey,
  getRawEncryptedRecords,
  isLegacyPlaintextRecord,
  listOfflineQueue,
  migrateLegacyPlaintextRecords,
  openGateDB,
  removeSyncedOfflineItems,
  resetEncryptionKeyMemoryCacheForTesting,
  resetMigrationStatusForTesting,
  retryGateMigration,
  seedLegacyOfflineRecordForTesting,
  updateOfflineQueueStatus,
  validateEncryptedRecordInvariant,
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
      'name:Ramesh Pawar|phone:+919823011223|vehicle:MH-12-AB-1234|purpose:DELIVERY|flat:70000000-0000-4000-a000-000000000701|notice:v1.0-2026-pune|photo:|captured:'
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

  it('computes binary SHA-256 for offline photos and binds digest to canonical payload', async () => {
    // b64 representing b"test_jpeg_bytes_12345"
    const photoBase64 = 'data:image/jpeg;base64,dGVzdF9qcGVnX2J5dGVzXzEyMzQ1';
    const photoSha = await computePhotoSha256(photoBase64);
    expect(photoSha).toBe('ffc33203974fa792b54250be3c955f720d941dd940168bd6ed0e03ab645904d9');

    const canonicalWithPhoto = buildCanonicalPayloadString({
      visitor_name: 'Anand Shinde',
      phone_number: '+919823055443',
      purpose: 'GUEST',
      destination_flat_id: '70000000-0000-4000-a000-000000000701',
      privacy_notice_version: 'v1.0-2026-pune',
      photo_sha256: photoSha,
      photo_captured_at: '2026-11-06T12:00:00Z',
    });
    expect(canonicalWithPhoto).toContain(`photo:${photoSha}`);
    expect(canonicalWithPhoto).toContain('captured:2026-11-06T12:00:00Z');
  });

  it('encrypts sensitive visitor PII using Web Crypto AES-GCM and verifies zero plaintext in raw storage', async () => {
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
      photo_base64: 'data:image/jpeg;base64,dGVzdF9qcGVnX2J5dGVzXzEyMzQ1',
      privacy_notice_version: 'v1.0-2026-pune',
    });

    expect(item.approval_status).toBe('PENDING');
    expect(item.entry_status).toBe('EXPECTED');
    expect(item.sync_status).toBe('QUEUED');
    expect(item.phone_number).toBe('+919823099887');
    expect(item.photo_sha256).toBe('ffc33203974fa792b54250be3c955f720d941dd940168bd6ed0e03ab645904d9');
    expect(item.photo_captured_at).toBeTruthy();

    // Verify raw storage contains ONLY ciphertext, no plaintext PII or photos
    const rawRecords = await getRawEncryptedRecords();
    expect(rawRecords).toHaveLength(1);
    const raw = rawRecords[0];

    // Assert raw storage record does NOT have plaintext sensitive fields
    expect(raw).not.toHaveProperty('visitor_name');
    expect(raw).not.toHaveProperty('phone_number');
    expect(raw).not.toHaveProperty('vehicle_number');
    expect(raw).not.toHaveProperty('photo_base64');

    // Assert ciphertext and IV exist
    expect(raw.ciphertext).toBeTruthy();
    expect(raw.iv).toBeTruthy();

    // Raw serialized object must NOT contain substrings of PII or photo bytes
    const serializedRaw = JSON.stringify(raw);
    expect(serializedRaw).not.toContain('Suresh');
    expect(serializedRaw).not.toContain('Kulkarni');
    expect(serializedRaw).not.toContain('9823099887');
    expect(serializedRaw).not.toContain('MH12XY9999');
    expect(serializedRaw).not.toContain('dGVzdF9qcGVnX2J5dGVzXzEyMzQ1');

    // listOfflineQueue decodes correctly
    const persisted = await listOfflineQueue(gateId);
    expect(persisted).toHaveLength(1);
    expect(persisted[0].client_event_id).toBe(item.client_event_id);
    expect(persisted[0].visitor_name).toBe('Suresh Kulkarni');
    expect(persisted[0].phone_number).toBe('+919823099887');
    expect(persisted[0].vehicle_number).toBe('MH12XY9999');
    expect(persisted[0].photo_sha256).toBe('ffc33203974fa792b54250be3c955f720d941dd940168bd6ed0e03ab645904d9');
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

  it('declares GATE_DB_VERSION = 2 for encryption migration', () => {
    expect(GATE_DB_VERSION).toBe(2);
  });

  it('correctly detects legacy plaintext records vs encrypted records with isLegacyPlaintextRecord', async () => {
    const legacyItem = {
      client_event_id: 'ev-legacy-1',
      visitor_name: 'Old Plaintext Visitor',
      phone_number: '9823011223',
    };
    expect(isLegacyPlaintextRecord(legacyItem)).toBe(true);

    const encryptedItem = await enqueueOfflineVisitor({
      gate_id: 'gate-1',
      visitor_name: 'Encrypted Visitor',
      phone_number: '9823011223',
      purpose: 'DELIVERY',
      destination_flat_id: 'flat-1',
      privacy_notice_version: 'v1.0-2026-pune',
    });
    const rawList = await getRawEncryptedRecords();
    const raw = rawList.find((x) => x.client_event_id === encryptedItem.client_event_id);
    expect(isLegacyPlaintextRecord(raw)).toBe(false);
  });

  it('migrates legacy v1 plaintext records to encrypted storage, preserves IDs and sync states, and verifies round-trip', async () => {
    const legacy1 = {
      client_event_id: 'legacy-event-001',
      gate_id: '60000000-0000-4000-a000-000000000001',
      timestamp: '2026-11-06T09:30:00.000Z',
      visitor_name: 'Suresh Patil',
      phone_number: '9823055555',
      vehicle_number: 'MH-12-QQ-4321',
      purpose: 'GUEST',
      destination_flat_id: '70000000-0000-4000-a000-000000000701',
      flat_label: 'Tower 7 Flat 701',
      photo_base64: 'data:image/jpeg;base64,dGVzdF9qcGVnX2J5dGVzXzEyMzQ1',
      privacy_notice_version: 'v1.0-2026-pune',
      payload_hash: '',
      sync_status: 'QUEUED',
      approval_status: 'PENDING',
      entry_status: 'EXPECTED',
      error_message: null,
      retry_count: 2,
      server_visitor_id: null,
    };

    const legacy2 = {
      client_event_id: 'legacy-event-002',
      gate_id: '60000000-0000-4000-a000-000000000001',
      timestamp: '2026-11-06T09:45:00.000Z',
      visitor_name: 'Kavita Deshmukh',
      phone_number: '+919823066666',
      vehicle_number: null,
      purpose: 'DELIVERY',
      destination_flat_id: '70000000-0000-4000-a000-000000000702',
      flat_label: 'Tower 7 Flat 702',
      photo_base64: null,
      privacy_notice_version: 'v1.0-2026-pune',
      payload_hash: '',
      sync_status: 'FAILED',
      approval_status: 'PENDING',
      entry_status: 'EXPECTED',
      error_message: 'Gateway timed out',
      retry_count: 3,
      server_visitor_id: null,
    };

    await seedLegacyOfflineRecordForTesting(legacy1);
    await seedLegacyOfflineRecordForTesting(legacy2);

    // Verify storage currently holds legacy records with plaintext
    const initialRaw = await getRawEncryptedRecords();
    expect(initialRaw).toHaveLength(2);
    expect(isLegacyPlaintextRecord(initialRaw[0])).toBe(true);

    // Execute migration
    const migrationResult = await migrateLegacyPlaintextRecords();
    expect(migrationResult.migratedCount).toBe(2);
    expect(migrationResult.verifiedCount).toBe(2);

    // Verify raw storage now contains ONLY ciphertext + IV, with zero plaintext PII
    const rawAfter = await getRawEncryptedRecords();
    expect(rawAfter).toHaveLength(2);

    for (const raw of rawAfter) {
      expect(raw.ciphertext).toBeTruthy();
      expect(raw.iv).toBeTruthy();
      expect(raw).not.toHaveProperty('visitor_name');
      expect(raw).not.toHaveProperty('phone_number');
      expect(raw).not.toHaveProperty('vehicle_number');
      expect(raw).not.toHaveProperty('photo_base64');
      expect(raw).not.toHaveProperty('flat_label');

      const serialized = JSON.stringify(raw);
      expect(serialized).not.toContain('Suresh');
      expect(serialized).not.toContain('Patil');
      expect(serialized).not.toContain('Kavita');
      expect(serialized).not.toContain('Deshmukh');
      expect(serialized).not.toContain('9823055555');
      expect(serialized).not.toContain('9823066666');
      expect(serialized).not.toContain('MH-12-QQ-4321');
      expect(serialized).not.toContain('dGVzdF9qcGVnX2J5dGVzXzEyMzQ1');
    }

    // Verify listOfflineQueue decodes all fields accurately with preserved IDs and sync states
    const decoded = await listOfflineQueue();
    expect(decoded).toHaveLength(2);

    const item1 = decoded.find((x) => x.client_event_id === 'legacy-event-001');
    expect(item1).toBeDefined();
    expect(item1?.visitor_name).toBe('Suresh Patil');
    expect(item1?.phone_number).toBe('+919823055555');
    expect(item1?.vehicle_number).toBe('MH-12-QQ-4321');
    expect(item1?.flat_label).toBe('Tower 7 Flat 701');
    expect(item1?.sync_status).toBe('QUEUED');
    expect(item1?.retry_count).toBe(2);
    expect(item1?.photo_sha256).toBe('ffc33203974fa792b54250be3c955f720d941dd940168bd6ed0e03ab645904d9');

    const item2 = decoded.find((x) => x.client_event_id === 'legacy-event-002');
    expect(item2).toBeDefined();
    expect(item2?.visitor_name).toBe('Kavita Deshmukh');
    expect(item2?.phone_number).toBe('+919823066666');
    expect(item2?.vehicle_number).toBeNull();
    expect(item2?.sync_status).toBe('FAILED');
    expect(item2?.error_message).toBe('Gateway timed out');
    expect(item2?.retry_count).toBe(3);
  });

  it('safely handles legacy records during listOfflineQueue without stranding or emitting redacted placeholders', async () => {
    const legacy = {
      client_event_id: 'legacy-unmigrated-003',
      gate_id: 'gate-1',
      timestamp: '2026-11-06T11:00:00.000Z',
      visitor_name: 'Direct Reader Visitor',
      phone_number: '9823077777',
      vehicle_number: null,
      purpose: 'CAB',
      destination_flat_id: 'flat-703',
      privacy_notice_version: 'v1.0-2026-pune',
      payload_hash: 'legacy_hash_003',
      sync_status: 'QUEUED',
      approval_status: 'PENDING',
      entry_status: 'EXPECTED',
      error_message: null,
      retry_count: 0,
      server_visitor_id: null,
    };

    await seedLegacyOfflineRecordForTesting(legacy);

    // Call listOfflineQueue directly without prior migration call
    const list = await listOfflineQueue('gate-1');
    expect(list).toHaveLength(1);
    expect(list[0].visitor_name).toBe('Direct Reader Visitor');
    expect(list[0].visitor_name).not.toBe('[ENCRYPTED_VISITOR]');
    expect(list[0].phone_number).toBe('+919823077777');
    expect(list[0].sync_status).toBe('QUEUED');

    // Wait a brief microtask for background migration to finish
    await new Promise((r) => setTimeout(r, 50));

    // Verify background migration encrypted the record
    const raw = await getRawEncryptedRecords();
    expect(raw[0].ciphertext).toBeTruthy();
    expect(raw[0].visitor_name).toBeUndefined();
  });

  it('migrates legacy records on-the-fly during updateOfflineQueueStatus', async () => {
    const legacy = {
      client_event_id: 'legacy-update-004',
      gate_id: 'gate-1',
      timestamp: '2026-11-06T11:15:00.000Z',
      visitor_name: 'Update Target Visitor',
      phone_number: '9823088888',
      vehicle_number: 'MH-14-ZZ-9999',
      purpose: 'GUEST',
      destination_flat_id: 'flat-704',
      privacy_notice_version: 'v1.0-2026-pune',
      payload_hash: 'legacy_hash_004',
      sync_status: 'QUEUED',
      approval_status: 'PENDING',
      entry_status: 'EXPECTED',
      error_message: null,
      retry_count: 0,
      server_visitor_id: null,
    };

    await seedLegacyOfflineRecordForTesting(legacy);

    const updated = await updateOfflineQueueStatus('legacy-update-004', {
      sync_status: 'SYNCED',
      server_visitor_id: 'visitor-srv-004',
      increment_retry: true,
    });

    expect(updated).not.toBeNull();
    expect(updated?.visitor_name).toBe('Update Target Visitor');
    expect(updated?.sync_status).toBe('SYNCED');
    expect(updated?.server_visitor_id).toBe('visitor-srv-004');
    expect(updated?.retry_count).toBe(1);

    // Verify raw record is now encrypted
    const raw = (await getRawEncryptedRecords()).find((x) => x.client_event_id === 'legacy-update-004');
    expect(raw.ciphertext).toBeTruthy();
    expect(raw.visitor_name).toBeUndefined();
    expect(raw.sync_status).toBe('SYNCED');
  });

  it('simulates native IndexedDB v1-to-v2 upgrade: onupgradeneeded fired, legacy records encrypted and verified', async () => {
    const v1Records = new Map<string, any>();
    const legacyItem = {
      client_event_id: 'legacy-idb-1111-2222',
      gate_id: 'gate-idb-1',
      timestamp: '2026-11-06T10:00:00Z',
      visitor_name: 'IDB Legacy Visitor',
      phone_number: '9876543210',
      vehicle_number: 'MH12IDB999',
      purpose: 'GUEST',
      destination_flat_id: 'flat-idb-1',
      flat_label: 'T10-101',
      photo_base64: 'data:image/jpeg;base64,dGVzdF9qcGVnX2J5dGVzXzEyMzQ1',
      privacy_notice_version: 'v1.0-2026-pune',
      payload_hash: 'legacy_hash_idb',
      sync_status: 'QUEUED',
      approval_status: 'PENDING',
      entry_status: 'EXPECTED',
      error_message: null,
      retry_count: 3,
      server_visitor_id: null,
    };
    v1Records.set(legacyItem.client_event_id, { ...legacyItem });

    let upgradeFiredWithOldVersion: number | null = null;
    let currentDbVersion = 1;

    const mockDb: any = {
      version: 1,
      objectStoreNames: {
        contains: (name: string) => name === 'offline_visitor_queue',
      },
      createObjectStore: vi.fn(),
      transaction: (_stores: any, _mode: string) => {
        const tx: any = {
          objectStore: (_name: string) => ({
            getAll: () => {
              const req: any = { result: Array.from(v1Records.values()) };
              queueMicrotask(() => req.onsuccess && req.onsuccess());
              return req;
            },
            put: (item: any) => {
              v1Records.set(item.client_event_id, item);
              const req: any = { result: item.client_event_id };
              queueMicrotask(() => req.onsuccess && req.onsuccess());
              return req;
            },
          }),
          oncomplete: null,
          onerror: null,
        };
        queueMicrotask(() => tx.oncomplete && tx.oncomplete());
        return tx;
      },
      close: vi.fn(),
    };

    const originalIndexedDB = (globalThis as any).indexedDB;
    (globalThis as any).indexedDB = {
      open: (_name: string, version: number) => {
        const req: any = { result: mockDb, error: null };
        queueMicrotask(() => {
          if (version > currentDbVersion) {
            upgradeFiredWithOldVersion = currentDbVersion;
            currentDbVersion = version;
            mockDb.version = version;
            if (req.onupgradeneeded) {
              req.onupgradeneeded({ oldVersion: upgradeFiredWithOldVersion, newVersion: version });
            }
          }
          if (req.onsuccess) req.onsuccess();
        });
        return req;
      },
    };

    try {
      const db = await openGateDB();
      expect(upgradeFiredWithOldVersion).toBe(1);
      expect(db.version).toBe(2);

      // Verify records in v1Records map are now encrypted
      const migratedRaw = v1Records.get(legacyItem.client_event_id);
      expect(migratedRaw.ciphertext).toBeTruthy();
      expect(migratedRaw.iv).toBeTruthy();
      expect(migratedRaw.visitor_name).toBeUndefined();
      expect(migratedRaw.phone_number).toBeUndefined();
      expect(migratedRaw.photo_base64).toBeUndefined();
      expect(migratedRaw.vehicle_number).toBeUndefined();

      // Verify retry count, sync status, and client_event_id preserved
      expect(migratedRaw.retry_count).toBe(3);
      expect(migratedRaw.sync_status).toBe('QUEUED');
      expect(migratedRaw.client_event_id).toBe(legacyItem.client_event_id);
    } finally {
      if (originalIndexedDB) {
        (globalThis as any).indexedDB = originalIndexedDB;
      } else {
        delete (globalThis as any).indexedDB;
      }
    }
  });

  it('persists master encryption key in TownshipGateKeyStore and reloads exact key after simulated browser restart', async () => {
    const keyStore = new Map<string, any>();
    const originalIndexedDB = (globalThis as any).indexedDB;

    const mockKeyDb: any = {
      objectStoreNames: { contains: () => true },
      createObjectStore: vi.fn(),
      transaction: (_stores: any, _mode: string) => {
        const tx: any = {
          objectStore: () => ({
            get: (key: string) => {
              const req: any = { result: keyStore.get(key) };
              queueMicrotask(() => req.onsuccess && req.onsuccess());
              return req;
            },
            put: (val: any, key: string) => {
              keyStore.set(key, val);
              const req: any = { result: key };
              queueMicrotask(() => req.onsuccess && req.onsuccess());
              return req;
            },
          }),
          oncomplete: null,
          onerror: null,
        };
        queueMicrotask(() => tx.oncomplete && tx.oncomplete());
        return tx;
      },
      close: vi.fn(),
    };

    (globalThis as any).indexedDB = {
      open: (_name: string) => {
        const req: any = { result: mockKeyDb };
        queueMicrotask(() => req.onsuccess && req.onsuccess());
        return req;
      },
    };

    try {
      // 1. Initial key creation
      resetEncryptionKeyMemoryCacheForTesting();
      const key1 = await getOrCreateGateEncryptionKey();
      expect(keyStore.has(MASTER_KEY_ID)).toBe(true);

      // 2. Encrypt sample sensitive data
      const samplePayload = {
        visitor_name: 'Persistent Test Visitor',
        phone_number: '+919823012345',
        vehicle_number: null,
        photo_base64: null,
      };
      const encrypted = await encryptSensitivePayload(samplePayload, key1);

      // 3. Simulate browser restart: memory cache wiped clean
      resetEncryptionKeyMemoryCacheForTesting();

      // 4. Reload key from persistent IndexedDB
      const key2 = await getOrCreateGateEncryptionKey();
      expect(key2).toBeDefined();

      // 5. Decrypt using reloaded key -> proves exact persistent key was preserved across restart
      const decrypted = await decryptSensitivePayload(encrypted.iv, encrypted.ciphertext, key2);
      expect(decrypted.visitor_name).toBe('Persistent Test Visitor');
      expect(decrypted.phone_number).toBe('+919823012345');
    } finally {
      resetEncryptionKeyMemoryCacheForTesting();
      if (originalIndexedDB) {
        (globalThis as any).indexedDB = originalIndexedDB;
      } else {
        delete (globalThis as any).indexedDB;
      }
    }
  });

  it('fails closed and throws when persistent IndexedDB storage is being used and key persistence fails', async () => {
    const originalIndexedDB = (globalThis as any).indexedDB;

    // Simulate IndexedDB available, but opening key store fails (e.g. disk corruption, quota exceeded)
    (globalThis as any).indexedDB = {
      open: (_name: string) => {
        const req: any = {
          error: new Error('QuotaExceededError: storage full'),
        };
        queueMicrotask(() => req.onerror && req.onerror());
        return req;
      },
    };

    try {
      resetEncryptionKeyMemoryCacheForTesting();

      // Must fail closed: throw an error, NEVER silently fall back to an ephemeral in-memory key!
      await expect(getOrCreateGateEncryptionKey()).rejects.toThrow(
        /Failed to persist or retrieve gate encryption key in IndexedDB/
      );
    } finally {
      resetEncryptionKeyMemoryCacheForTesting();
      if (originalIndexedDB) {
        (globalThis as any).indexedDB = originalIndexedDB;
      } else {
        delete (globalThis as any).indexedDB;
      }
    }
  });

  it('fails closed in enqueueOfflineVisitor when persistent encryption key store cannot be opened', async () => {
    const originalIndexedDB = (globalThis as any).indexedDB;

    // IndexedDB exists (meaning persistent storage is active), but key DB fails to open
    (globalThis as any).indexedDB = {
      open: (name: string) => {
        if (name === 'TownshipGateKeyStore') {
          const req: any = { error: new DOMException('Access denied', 'SecurityError') };
          queueMicrotask(() => req.onerror && req.onerror());
          return req;
        }
        // gate DB
        const req: any = { result: {} };
        queueMicrotask(() => req.onsuccess && req.onsuccess());
        return req;
      },
    };

    try {
      resetEncryptionKeyMemoryCacheForTesting();

      // Enqueueing must fail closed: never encrypt with a temporary in-memory key that will vanish on restart
      await expect(
        enqueueOfflineVisitor({
          gate_id: 'gate-failclosed-1',
          visitor_name: 'Fail Closed Visitor',
          phone_number: '9823099999',
          purpose: 'DELIVERY',
          destination_flat_id: 'flat-failclosed-1',
          privacy_notice_version: 'v1.0-2026-pune',
        })
      ).rejects.toThrow(/Failed to persist or retrieve gate encryption key in IndexedDB/);
    } finally {
      resetEncryptionKeyMemoryCacheForTesting();
      if (originalIndexedDB) {
        (globalThis as any).indexedDB = originalIndexedDB;
      } else {
        delete (globalThis as any).indexedDB;
      }
    }
  });

  it('validateEncryptedRecordInvariant strictly rejects plaintext records or missing ciphertext/iv', () => {
    // 1. Plaintext legacy record must be rejected
    const plaintextRecord = {
      client_event_id: 'plain-1',
      visitor_name: 'Plaintext Visitor',
      phone_number: '9823012345',
    };
    expect(() => validateEncryptedRecordInvariant(plaintextRecord)).toThrow(
      /Security Invariant Violation: Plaintext visitor record rejected/
    );

    // 2. Missing ciphertext or iv must be rejected
    expect(() =>
      validateEncryptedRecordInvariant({
        client_event_id: 'plain-2',
        iv: 'some-iv',
      })
    ).toThrow(/Security Invariant Violation/);

    expect(() =>
      validateEncryptedRecordInvariant({
        client_event_id: 'plain-3',
        ciphertext: 'some-cipher',
      })
    ).toThrow(/Security Invariant Violation/);

    // 3. Valid encrypted record must pass and have any accidental plaintext fields stripped
    const validEncrypted: any = {
      client_event_id: 'valid-enc-1',
      iv: 'valid-iv-1234',
      ciphertext: 'valid-ciphertext-5678',
      visitor_name: 'Accidental Plaintext Leak',
      phone_number: '9823000000',
    };
    validateEncryptedRecordInvariant(validEncrypted);
    expect(validEncrypted.visitor_name).toBeUndefined();
    expect(validEncrypted.phone_number).toBeUndefined();
    expect(validEncrypted.ciphertext).toBe('valid-ciphertext-5678');
  });

  it('explicitly surfaces migration failure in getGateMigrationStatus when migration fails, preserving unmigrated count', async () => {
    const originalIndexedDB = (globalThis as any).indexedDB;
    resetMigrationStatusForTesting();
    resetEncryptionKeyMemoryCacheForTesting();

    // Seed 1 unmigrated plaintext record
    await seedLegacyOfflineRecordForTesting({
      client_event_id: 'legacy-surface-err-01',
      gate_id: 'gate-1',
      visitor_name: 'Unmigrated Visitor 1',
      phone_number: '9823011111',
    });

    expect(await countLegacyPlaintextRecords()).toBe(1);

    // Force persistent key store failure
    (globalThis as any).indexedDB = {
      open: (_name: string) => {
        const req: any = { error: new DOMException('Disk I/O error', 'QuotaExceededError') };
        queueMicrotask(() => req.onerror && req.onerror());
        return req;
      },
    };

    try {
      // Direct call to migrateLegacyPlaintextRecords MUST throw and NOT swallow the error
      await expect(migrateLegacyPlaintextRecords()).rejects.toThrow(
        /Failed to persist or retrieve gate encryption key in IndexedDB/
      );

      // Status must explicitly show FAILED, with unmigratedCount preserved
      const status = getGateMigrationStatus();
      expect(status.status).toBe('FAILED');
      expect(status.unmigratedCount).toBe(1);
      expect(status.error).toContain('Failed to persist or retrieve gate encryption key in IndexedDB');
      expect(status.lastAttemptAt).toBeTruthy();
    } finally {
      resetEncryptionKeyMemoryCacheForTesting();
      resetMigrationStatusForTesting();
      if (originalIndexedDB) {
        (globalThis as any).indexedDB = originalIndexedDB;
      } else {
        delete (globalThis as any).indexedDB;
      }
    }
  });

  it('safely retries migration with retryGateMigration() and transitions status to COMPLETED with 0 unmigrated records', async () => {
    const originalIndexedDB = (globalThis as any).indexedDB;
    resetMigrationStatusForTesting();
    resetEncryptionKeyMemoryCacheForTesting();

    const legacyItem = {
      client_event_id: 'legacy-retry-02',
      gate_id: 'gate-1',
      visitor_name: 'Retry Target Visitor',
      phone_number: '9823022222',
      purpose: 'DELIVERY',
      destination_flat_id: 'flat-1',
      privacy_notice_version: 'v1.0-2026-pune',
    };
    await seedLegacyOfflineRecordForTesting(legacyItem);

    // 1. First attempt fails due to simulated failure
    (globalThis as any).indexedDB = {
      open: (_name: string) => {
        const req: any = { error: new Error('Temporary DB lock') };
        queueMicrotask(() => req.onerror && req.onerror());
        return req;
      },
    };

    await expect(migrateLegacyPlaintextRecords()).rejects.toThrow(/Temporary DB lock/);
    expect(getGateMigrationStatus().status).toBe('FAILED');
    expect(getGateMigrationStatus().unmigratedCount).toBe(1);

    // 2. Resolve simulated failure: restore normal memory/crypto execution
    if (originalIndexedDB) {
      (globalThis as any).indexedDB = originalIndexedDB;
    } else {
      delete (globalThis as any).indexedDB;
    }
    resetEncryptionKeyMemoryCacheForTesting();

    // 3. Retry migration safely
    const retryResult = await retryGateMigration();
    expect(retryResult.migratedCount).toBe(1);
    expect(retryResult.verifiedCount).toBe(1);

    // 4. Status must transition to COMPLETED with 0 unmigrated records
    const finalStatus = getGateMigrationStatus();
    expect(finalStatus.status).toBe('COMPLETED');
    expect(finalStatus.unmigratedCount).toBe(0);
    expect(finalStatus.error).toBeNull();

    // 5. Raw record must now be encrypted with zero plaintext
    const rawRecords = await getRawEncryptedRecords();
    const migratedRaw = rawRecords.find((x) => x.client_event_id === 'legacy-retry-02');
    expect(migratedRaw.ciphertext).toBeTruthy();
    expect(migratedRaw.iv).toBeTruthy();
    expect(migratedRaw.visitor_name).toBeUndefined();
    expect(migratedRaw.phone_number).toBeUndefined();
  });

  it('openGateDB surfaces migration failure status explicitly in currentMigrationStatus without swallowing state', async () => {
    const originalIndexedDB = (globalThis as any).indexedDB;
    resetMigrationStatusForTesting();
    resetEncryptionKeyMemoryCacheForTesting();

    await seedLegacyOfflineRecordForTesting({
      client_event_id: 'legacy-opengatedb-03',
      gate_id: 'gate-1',
      visitor_name: 'OpenGateDB Legacy Visitor',
      phone_number: '9823033333',
    });

    const mockDb: any = {
      version: 2,
      objectStoreNames: { contains: () => true },
      createObjectStore: vi.fn(),
      transaction: () => ({
        objectStore: () => ({
          getAll: () => {
            const req: any = { result: [] };
            queueMicrotask(() => req.onsuccess && req.onsuccess());
            return req;
          },
        }),
      }),
      close: vi.fn(),
    };

    (globalThis as any).indexedDB = {
      open: (name: string) => {
        if (name === 'TownshipGateKeyStore') {
          // Key DB fails
          const req: any = { error: new Error('KeyStore corrupted') };
          queueMicrotask(() => req.onerror && req.onerror());
          return req;
        }
        // Gate DB succeeds
        const req: any = { result: mockDb };
        queueMicrotask(() => req.onsuccess && req.onsuccess());
        return req;
      },
    };

    try {
      const db = await openGateDB();
      expect(db).toBe(mockDb);

      // Migration failure MUST be surfaced in migration status
      const status = getGateMigrationStatus();
      expect(status.status).toBe('FAILED');
      expect(status.unmigratedCount).toBe(1);
      expect(status.error).toContain('KeyStore corrupted');
    } finally {
      resetEncryptionKeyMemoryCacheForTesting();
      resetMigrationStatusForTesting();
      if (originalIndexedDB) {
        (globalThis as any).indexedDB = originalIndexedDB;
      } else {
        delete (globalThis as any).indexedDB;
      }
    }
  });
});
