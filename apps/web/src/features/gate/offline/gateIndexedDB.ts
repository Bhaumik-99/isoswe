import { useState, useEffect } from 'react';
import {
  OfflineSyncStatus,
  OfflineVisitorQueueItem,
  VisitorPurposeType,
} from '../../../types';
import { formatPhoneToE164 } from '../../../services/gateService';

export const GATE_DB_NAME = 'TownshipGateDB';
export const GATE_DB_VERSION = 2; // Version 2: Encrypted offline queue migration
export const OFFLINE_QUEUE_STORE = 'offline_visitor_queue';

export const GATE_KEY_DB_NAME = 'TownshipGateKeyStore';
export const GATE_KEY_DB_VERSION = 1;
export const KEY_STORE_NAME = 'crypto_keys';
export const MASTER_KEY_ID = 'gate_aes_gcm_master_key';

export interface SensitiveVisitorData {
  visitor_name: string;
  phone_number: string;
  vehicle_number: string | null;
  photo_base64: string | null;
  flat_label?: string;
}

export interface EncryptedOfflineVisitorQueueItem {
  client_event_id: string;
  gate_id: string;
  timestamp: string;
  purpose: VisitorPurposeType;
  destination_flat_id: string;
  privacy_notice_version: string;
  payload_hash: string;
  photo_sha256: string | null;
  photo_captured_at: string | null;
  sync_status: OfflineSyncStatus;
  approval_status: 'PENDING' | 'APPROVED' | 'REJECTED' | 'AUTO_APPROVED' | string;
  entry_status: 'EXPECTED' | 'CHECKED_IN' | 'CHECKED_OUT' | string;
  error_message: string | null;
  retry_count: number;
  server_visitor_id: string | null;
  iv: string; // Base64 encoded 12-byte initialization vector
  ciphertext: string; // Base64 encoded AES-GCM ciphertext + auth tag
}

export interface GateMigrationStatus {
  status: 'IDLE' | 'MIGRATING' | 'COMPLETED' | 'FAILED';
  unmigratedCount: number;
  migratedCount: number;
  error: string | null;
  lastAttemptAt: string | null;
}

let currentMigrationStatus: GateMigrationStatus = {
  status: 'IDLE',
  unmigratedCount: 0,
  migratedCount: 0,
  error: null,
  lastAttemptAt: null,
};

type MigrationStatusListener = (status: GateMigrationStatus) => void;
const migrationListeners = new Set<MigrationStatusListener>();

export function getGateMigrationStatus(): GateMigrationStatus {
  return { ...currentMigrationStatus };
}

export function subscribeGateMigrationStatus(listener: MigrationStatusListener): () => void {
  migrationListeners.add(listener);
  listener({ ...currentMigrationStatus });
  return () => {
    migrationListeners.delete(listener);
  };
}

export function updateMigrationStatus(updates: Partial<GateMigrationStatus>): void {
  currentMigrationStatus = {
    ...currentMigrationStatus,
    ...updates,
  };
  const snapshot = { ...currentMigrationStatus };
  for (const listener of migrationListeners) {
    try {
      listener(snapshot);
    } catch (e) {
      console.error('Error in migration listener:', e);
    }
  }
}

export function useGateMigrationStatus(): GateMigrationStatus {
  const [status, setStatus] = useState<GateMigrationStatus>(getGateMigrationStatus());
  useEffect(() => {
    return subscribeGateMigrationStatus(setStatus);
  }, []);
  return status;
}

export function resetMigrationStatusForTesting(): void {
  currentMigrationStatus = {
    status: 'IDLE',
    unmigratedCount: 0,
    migratedCount: 0,
    error: null,
    lastAttemptAt: null,
  };
}

// Module-level in-memory cache for the non-extractable key
let memoryCryptoKey: CryptoKey | null = null;

// In-memory store for environments without IndexedDB (e.g. Node unit tests) or hybrid storage
const memoryStore = new Map<string, any>();
export const memoryEncryptedStore = memoryStore;

export function hasNativeIndexedDB(): boolean {
  return typeof indexedDB !== 'undefined' && indexedDB !== null;
}

export function bufferToBase64(buffer: ArrayBuffer | Uint8Array): string {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

export function base64ToUint8Array(b64: string): Uint8Array {
  let raw = b64.trim();
  if (raw.startsWith('data:') && raw.includes(',')) {
    raw = raw.split(',', 2)[1];
  }
  raw = raw.replace(/\s/g, '');
  const binary = atob(raw);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Computes SHA-256 hex digest of decoded photo bytes, exactly matching backend _decode_photo.
 */
export async function computePhotoSha256(photoBase64: string): Promise<string> {
  const bytes = base64ToUint8Array(photoBase64);
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    const hashBuffer = await crypto.subtle.digest(
      'SHA-256',
      bytes as unknown as BufferSource
    );
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  }
  // Deterministic fallback if subtle crypto unavailable
  let h1 = 0xdeadbeef ^ bytes.length;
  let h2 = 0x41c6ce57 ^ bytes.length;
  for (let i = 0; i < bytes.length; i++) {
    const b = bytes[i];
    h1 = Math.imul(h1 ^ b, 2654435761);
    h2 = Math.imul(h2 ^ b, 1597334677);
  }
  return (h2 >>> 0).toString(16).padStart(8, '0') + (h1 >>> 0).toString(16).padStart(8, '0');
}

function openKeyDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(GATE_KEY_DB_NAME, GATE_KEY_DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(KEY_STORE_NAME)) {
        db.createObjectStore(KEY_STORE_NAME);
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error('Failed to open gate key database'));
    request.onblocked = () => reject(new Error('IndexedDB open blocked for gate key database'));
  });
}

let migrationLock: Promise<{ migratedCount: number; verifiedCount: number }> | null = null;

export function openRawGateDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(GATE_DB_NAME, GATE_DB_VERSION);
    request.onupgradeneeded = (_event: IDBVersionChangeEvent) => {
      const db = request.result;
      if (!db.objectStoreNames.contains(OFFLINE_QUEUE_STORE)) {
        const store = db.createObjectStore(OFFLINE_QUEUE_STORE, {
          keyPath: 'client_event_id',
        });
        store.createIndex('by_gate', 'gate_id', { unique: false });
        store.createIndex('by_status', 'sync_status', { unique: false });
        store.createIndex('by_timestamp', 'timestamp', { unique: false });
      }
      // If upgrading from v1 or earlier, stores exist and will be migrated post-open.
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function openGateDB(): Promise<IDBDatabase> {
  const db = await openRawGateDB();
  if (!migrationLock) {
    migrationLock = migrateLegacyPlaintextRecords(db)
      .catch((err) => {
        console.warn(
          '[GateDB] Background migration of legacy records failed; status set to FAILED:',
          err
        );
        return { migratedCount: 0, verifiedCount: 0 };
      })
      .finally(() => {
        migrationLock = null;
      });
  }
  await migrationLock;
  return db;
}

/**
 * Safely retries migration of legacy plaintext records.
 * Uses mutex lock to prevent concurrent races.
 */
export async function retryGateMigration(): Promise<{
  migratedCount: number;
  verifiedCount: number;
}> {
  if (migrationLock) {
    return await migrationLock;
  }
  migrationLock = migrateLegacyPlaintextRecords().finally(() => {
    migrationLock = null;
  });
  return await migrationLock;
}

/**
 * Resets the in-memory CryptoKey cache for testing.
 * Simulates a browser restart where in-memory state is cleared.
 */
export function resetEncryptionKeyMemoryCacheForTesting(): void {
  memoryCryptoKey = null;
}

/**
 * Retrieves or initializes the non-extractable AES-GCM 256-bit encryption key.
 * Non-extractable prevents XSS scripts from reading raw key material.
 *
 * Fail-Closed Invariant:
 * When persistent IndexedDB storage is being used (`hasNativeIndexedDB() === true`),
 * the encryption key MUST be loaded from or persisted into IndexedDB.
 * It MUST NEVER silently fall back to an in-memory key, because if records were encrypted
 * with an ephemeral key, they would become permanently undecryptable upon browser restart.
 */
export async function getOrCreateGateEncryptionKey(): Promise<CryptoKey> {
  if (memoryCryptoKey) {
    return memoryCryptoKey;
  }

  if (hasNativeIndexedDB()) {
    if (typeof crypto === 'undefined' || !crypto.subtle) {
      throw new Error('Web Crypto API (crypto.subtle) is required for persistent gate encryption.');
    }

    try {
      const keyDb = await openKeyDB();
      let storedKey: CryptoKey | undefined;
      try {
        storedKey = await new Promise<CryptoKey | undefined>((resolve, reject) => {
          const tx = keyDb.transaction(KEY_STORE_NAME, 'readonly');
          const store = tx.objectStore(KEY_STORE_NAME);
          const req = store.get(MASTER_KEY_ID);
          req.onsuccess = () => resolve(req.result as CryptoKey | undefined);
          req.onerror = () =>
            reject(req.error || new Error('Failed to retrieve master key from IndexedDB.'));
        });
      } finally {
        keyDb.close();
      }

      if (storedKey) {
        memoryCryptoKey = storedKey;
        return storedKey;
      }

      // Generate non-extractable AES-GCM 256-bit key
      const newKey = await crypto.subtle.generateKey(
        { name: 'AES-GCM', length: 256 },
        false, // non-extractable
        ['encrypt', 'decrypt']
      );

      const saveDb = await openKeyDB();
      try {
        await new Promise<void>((resolve, reject) => {
          const tx = saveDb.transaction(KEY_STORE_NAME, 'readwrite');
          const store = tx.objectStore(KEY_STORE_NAME);
          store.put(newKey, MASTER_KEY_ID);
          tx.oncomplete = () => resolve();
          tx.onerror = () =>
            reject(tx.error || new Error('Failed to persist master key to IndexedDB.'));
        });
      } finally {
        saveDb.close();
      }

      memoryCryptoKey = newKey;
      return newKey;
    } catch (err) {
      // Fail-closed invariant: When persistent IndexedDB storage is being used,
      // do not silently fall back to an ephemeral key. Fail closed if the encryption key
      // cannot be persisted or retrieved.
      throw new Error(
        `Failed to persist or retrieve gate encryption key in IndexedDB: ${
          err instanceof Error ? err.message : String(err)
        }`,
        { cause: err }
      );
    }
  }

  // Only reached when persistent IndexedDB is NOT available in the runtime environment
  // (e.g. headless unit testing without simulated indexedDB)
  if (typeof crypto !== 'undefined' && crypto.subtle) {
    memoryCryptoKey = await crypto.subtle.generateKey(
      { name: 'AES-GCM', length: 256 },
      false,
      ['encrypt', 'decrypt']
    );
    return memoryCryptoKey;
  }

  throw new Error('Web Crypto API is not supported in this runtime environment.');
}

/**
 * Encrypts sensitive visitor PII using AES-GCM with a fresh 12-byte random IV.
 */
export async function encryptSensitivePayload(
  sensitive: SensitiveVisitorData,
  key: CryptoKey
): Promise<{ iv: string; ciphertext: string }> {
  const ivBytes = crypto.getRandomValues(new Uint8Array(12));
  const plaintext = new TextEncoder().encode(JSON.stringify(sensitive));
  const encryptedBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv: ivBytes as unknown as BufferSource },
    key,
    plaintext as unknown as BufferSource
  );
  return {
    iv: bufferToBase64(ivBytes),
    ciphertext: bufferToBase64(encryptedBuffer),
  };
}

/**
 * Decrypts sensitive visitor PII using AES-GCM.
 */
export async function decryptSensitivePayload(
  ivBase64: string,
  ciphertextBase64: string,
  key: CryptoKey
): Promise<SensitiveVisitorData> {
  const ivBytes = base64ToUint8Array(ivBase64);
  const ciphertextBytes = base64ToUint8Array(ciphertextBase64);
  const decryptedBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv: ivBytes as unknown as BufferSource },
    key,
    ciphertextBytes as unknown as BufferSource
  );
  const plaintext = new TextDecoder().decode(decryptedBuffer);
  return JSON.parse(plaintext) as SensitiveVisitorData;
}

/**
 * Generates a RFC-4122 UUIDv4 client_event_id for idempotent offline sync.
 */
export function generateClientEventId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * Computes canonical string representation matching backend OfflineSyncService.compute_payload_hash.
 */
export function buildCanonicalPayloadString(input: {
  visitor_name: string;
  phone_number: string;
  vehicle_number?: string | null;
  purpose: string;
  destination_flat_id: string;
  privacy_notice_version: string;
  photo_sha256?: string | null;
  photo_captured_at?: string | null;
}): string {
  const name = (input.visitor_name || '').trim();
  const phone = (input.phone_number || '').trim();
  const vehicle = (input.vehicle_number || '').trim();
  const purpose = (input.purpose || '').trim();
  const flatId = (input.destination_flat_id || '').trim();
  const noticeVer = (input.privacy_notice_version || '').trim();
  const photoDigest = (input.photo_sha256 || '').trim().toLowerCase();
  const capturedAt = (input.photo_captured_at || '').trim();
  return (
    `name:${name}|phone:${phone}|vehicle:${vehicle}|purpose:${purpose}|flat:${flatId}` +
    `|notice:${noticeVer}|photo:${photoDigest}|captured:${capturedAt}`
  );
}

/**
 * Computes SHA-256 hex digest using Web Crypto API (with pure-JS deterministic fallback).
 */
export async function computePayloadHash(input: {
  visitor_name: string;
  phone_number: string;
  vehicle_number?: string | null;
  purpose: string;
  destination_flat_id: string;
  privacy_notice_version: string;
  photo_sha256?: string | null;
  photo_captured_at?: string | null;
}): Promise<string> {
  const canonical = buildCanonicalPayloadString(input);
  if (typeof crypto !== 'undefined' && crypto.subtle && typeof TextEncoder !== 'undefined') {
    const encoded = new TextEncoder().encode(canonical);
    const hashBuffer = await crypto.subtle.digest('SHA-256', encoded);
    const hashArray = Array.from(new Uint8Array(hashBuffer));
    return hashArray.map((b) => b.toString(16).padStart(2, '0')).join('');
  }
  // Deterministic fallback hash if subtle crypto is unavailable
  let h1 = 0xdeadbeef ^ canonical.length;
  let h2 = 0x41c6ce57 ^ canonical.length;
  for (let i = 0; i < canonical.length; i++) {
    const ch = canonical.charCodeAt(i);
    h1 = Math.imul(h1 ^ ch, 2654435761);
    h2 = Math.imul(h2 ^ ch, 1597334677);
  }
  h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
  h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
  return (h2 >>> 0).toString(16).padStart(8, '0') + (h1 >>> 0).toString(16).padStart(8, '0');
}

/**
 * Security Rule (R5/R6): Pre-approved guest pass verification MUST fail closed while offline.
 */
export function evaluateOfflineGuestPassPolicy(isOnline: boolean): {
  allowed: boolean;
  code: string;
  reason: string;
} {
  if (!isOnline) {
    return {
      allowed: false,
      code: 'FAIL_CLOSED_OFFLINE_GUEST_PASS',
      reason:
        'Guest pass verification requires live server connectivity to enforce revocation and usage limits. Please register visitor manually as PENDING.',
    };
  }
  return {
    allowed: true,
    code: 'ONLINE_ALLOWED',
    reason: 'Online verification permitted.',
  };
}

/**
 * Detects whether a queue item is unencrypted or contains legacy plaintext fields.
 */
export function isLegacyPlaintextRecord(item: any): boolean {
  if (!item || typeof item !== 'object') {
    return false;
  }
  const lacksEncryption =
    typeof item.ciphertext !== 'string' ||
    item.ciphertext.trim() === '' ||
    typeof item.iv !== 'string' ||
    item.iv.trim() === '';

  const hasPlaintextPII =
    (typeof item.visitor_name === 'string' &&
      item.visitor_name.trim().length > 0 &&
      !item.visitor_name.startsWith('[ENCRYPTED_')) ||
    (typeof item.phone_number === 'string' &&
      item.phone_number.trim().length > 0 &&
      !item.phone_number.startsWith('[ENCRYPTED_')) ||
    (typeof item.photo_base64 === 'string' && item.photo_base64.trim().length > 0) ||
    (typeof item.vehicle_number === 'string' && item.vehicle_number.trim().length > 0) ||
    typeof item.flat_label === 'string';

  return lacksEncryption || hasPlaintextPII;
}

/**
 * Migrates a single legacy record:
 * 1. Encrypts sensitive fields with AES-GCM master key.
 * 2. Verifies round-trip decryption matches original plaintext.
 * 3. Strips all plaintext sensitive fields so raw storage contains zero PII.
 */
export async function migrateSingleRecord(
  raw: any,
  key: CryptoKey
): Promise<EncryptedOfflineVisitorQueueItem> {
  const sensitive: SensitiveVisitorData = {
    visitor_name: (raw.visitor_name || '').trim(),
    phone_number: raw.phone_number ? formatPhoneToE164(raw.phone_number) : '',
    vehicle_number: raw.vehicle_number ? raw.vehicle_number.trim() : null,
    photo_base64: raw.photo_base64 || null,
    flat_label: raw.flat_label,
  };

  let photoSha256: string | null = raw.photo_sha256 || null;
  let photoCapturedAt: string | null = raw.photo_captured_at || null;

  if (sensitive.photo_base64 && !photoSha256) {
    photoSha256 = await computePhotoSha256(sensitive.photo_base64);
  }
  if (sensitive.photo_base64 && !photoCapturedAt) {
    photoCapturedAt = raw.photo_captured_at || raw.timestamp || new Date().toISOString();
  }

  let payloadHash: string = raw.payload_hash || '';
  if (!payloadHash) {
    payloadHash = await computePayloadHash({
      visitor_name: sensitive.visitor_name,
      phone_number: sensitive.phone_number,
      vehicle_number: sensitive.vehicle_number,
      purpose: raw.purpose || 'GUEST',
      destination_flat_id: raw.destination_flat_id || '',
      privacy_notice_version: raw.privacy_notice_version || 'v1.0-2026-pune',
      photo_sha256: photoSha256,
      photo_captured_at: photoCapturedAt,
    });
  }

  // Encrypt sensitive PII
  const { iv, ciphertext } = await encryptSensitivePayload(sensitive, key);

  // Verification step: assert decryption round-trip
  const verification = await decryptSensitivePayload(iv, ciphertext, key);
  if (
    verification.visitor_name !== sensitive.visitor_name ||
    verification.phone_number !== sensitive.phone_number ||
    verification.vehicle_number !== sensitive.vehicle_number ||
    verification.photo_base64 !== sensitive.photo_base64 ||
    verification.flat_label !== sensitive.flat_label
  ) {
    throw new Error(
      `Migration round-trip verification failed for client_event_id: ${raw.client_event_id}`
    );
  }

  const migrated: EncryptedOfflineVisitorQueueItem = {
    client_event_id: raw.client_event_id,
    gate_id: raw.gate_id,
    timestamp: raw.timestamp || new Date().toISOString(),
    purpose: raw.purpose || 'GUEST',
    destination_flat_id: raw.destination_flat_id || '',
    privacy_notice_version: raw.privacy_notice_version || 'v1.0-2026-pune',
    payload_hash: payloadHash,
    photo_sha256: photoSha256,
    photo_captured_at: photoCapturedAt,
    sync_status: raw.sync_status || 'QUEUED',
    approval_status: raw.approval_status || 'PENDING',
    entry_status: raw.entry_status || 'EXPECTED',
    error_message: raw.error_message || null,
    retry_count: typeof raw.retry_count === 'number' ? raw.retry_count : 0,
    server_visitor_id: raw.server_visitor_id || null,
    iv,
    ciphertext,
  };

  return migrated;
}

/**
 * Returns the count of legacy plaintext records across in-memory and native IndexedDB stores.
 */
export async function countLegacyPlaintextRecords(dbInstance?: IDBDatabase): Promise<number> {
  let count = 0;
  for (const record of memoryStore.values()) {
    if (isLegacyPlaintextRecord(record)) {
      count++;
    }
  }

  if (hasNativeIndexedDB()) {
    const shouldClose = !dbInstance;
    let db: IDBDatabase | null = null;
    try {
      db = dbInstance || (await openRawGateDB());
      const allRecords = await new Promise<any[]>((resolve, reject) => {
        const tx = db!.transaction(OFFLINE_QUEUE_STORE, 'readonly');
        const store = tx.objectStore(OFFLINE_QUEUE_STORE);
        const req = store.getAll();
        req.onsuccess = () => resolve((req.result || []) as any[]);
        req.onerror = () => reject(req.error);
      });
      count += allRecords.filter(isLegacyPlaintextRecord).length;
    } catch {
      // If store cannot be opened, count remains what was found in memory
    } finally {
      if (shouldClose && db) {
        db.close();
      }
    }
  }

  return count;
}

/**
 * Scans offline queue for any legacy plaintext records, encrypts them,
 * verifies successful encryption, and updates storage without dropping or clearing the queue.
 *
 * Invariants:
 * 1. Surfaces migration state explicitly via getGateMigrationStatus() and subscribeGateMigrationStatus().
 * 2. If migration fails (e.g. key store failure, storage error), records failure status with details and rethrows.
 * 3. Never writes unencrypted plaintext records.
 */
export async function migrateLegacyPlaintextRecords(
  dbInstance?: IDBDatabase
): Promise<{ migratedCount: number; verifiedCount: number }> {
  let initialUnmigrated = 0;
  try {
    initialUnmigrated = await countLegacyPlaintextRecords(dbInstance);
  } catch {
    initialUnmigrated = 1;
  }

  if (initialUnmigrated === 0) {
    updateMigrationStatus({
      status: 'COMPLETED',
      unmigratedCount: 0,
      error: null,
    });
    return { migratedCount: 0, verifiedCount: 0 };
  }

  updateMigrationStatus({
    status: 'MIGRATING',
    unmigratedCount: initialUnmigrated,
    error: null,
    lastAttemptAt: new Date().toISOString(),
  });

  let migratedCount = 0;
  let verifiedCount = 0;

  try {
    const key = await getOrCreateGateEncryptionKey();

    // 1. Migrate in-memory records (for tests and memory fallback)
    for (const [id, record] of Array.from(memoryStore.entries())) {
      if (isLegacyPlaintextRecord(record)) {
        const migrated = await migrateSingleRecord(record, key);
        memoryStore.set(id, migrated);
        migratedCount++;
        verifiedCount++;
      }
    }

    // 2. Migrate native IndexedDB records if present
    if (hasNativeIndexedDB()) {
      const shouldClose = !dbInstance;
      let db: IDBDatabase | null = null;
      try {
        db = dbInstance || (await openRawGateDB());
        const allRecords = await new Promise<any[]>((resolve, reject) => {
          const tx = db!.transaction(OFFLINE_QUEUE_STORE, 'readonly');
          const store = tx.objectStore(OFFLINE_QUEUE_STORE);
          const req = store.getAll();
          req.onsuccess = () => resolve((req.result || []) as any[]);
          req.onerror = () => reject(req.error);
        });

        const legacyRecords = allRecords.filter(isLegacyPlaintextRecord);
        if (legacyRecords.length > 0) {
          const migratedList: EncryptedOfflineVisitorQueueItem[] = [];
          for (const legacy of legacyRecords) {
            const migrated = await migrateSingleRecord(legacy, key);
            migratedList.push(migrated);
            migratedCount++;
            verifiedCount++;
          }

          await new Promise<void>((resolve, reject) => {
            const tx = db!.transaction(OFFLINE_QUEUE_STORE, 'readwrite');
            const store = tx.objectStore(OFFLINE_QUEUE_STORE);
            for (const item of migratedList) {
              store.put(item);
            }
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
          });
        }
      } finally {
        if (shouldClose && db) {
          db.close();
        }
      }
    }

    updateMigrationStatus({
      status: 'COMPLETED',
      unmigratedCount: 0,
      migratedCount,
      error: null,
      lastAttemptAt: new Date().toISOString(),
    });

    return { migratedCount, verifiedCount };
  } catch (err) {
    const errMsg = err instanceof Error ? err.message : String(err);
    console.error('[GateMigration] Legacy plaintext record migration failed:', err);

    const remainingUnmigrated = await countLegacyPlaintextRecords(dbInstance).catch(
      () => initialUnmigrated
    );
    updateMigrationStatus({
      status: 'FAILED',
      unmigratedCount: remainingUnmigrated,
      error: errMsg,
      lastAttemptAt: new Date().toISOString(),
    });

    throw err;
  }
}

/**
 * Seeds a raw record directly into storage (for migration testing).
 */
export async function seedLegacyOfflineRecordForTesting(record: any): Promise<void> {
  memoryStore.set(record.client_event_id, record);

  if (hasNativeIndexedDB()) {
    const db = await openRawGateDB();
    await new Promise<void>((resolve, reject) => {
      const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readwrite');
      const store = tx.objectStore(OFFLINE_QUEUE_STORE);
      store.put(record);
      tx.oncomplete = () => {
        db.close();
        resolve();
      };
      tx.onerror = () => {
        db.close();
        reject(tx.error);
      };
    });
  }
}

/**
 * Security Invariant Guard:
 * Prevents new or updated unencrypted plaintext records from being written into storage.
 * Enforces presence of ciphertext and IV, and strips any leaked plaintext fields.
 */
export function validateEncryptedRecordInvariant(item: any): void {
  if (!item || typeof item !== 'object') {
    throw new Error('Security Invariant Violation: Record payload is null or undefined.');
  }
  if (
    typeof item.ciphertext !== 'string' ||
    !item.ciphertext.trim() ||
    typeof item.iv !== 'string' ||
    !item.iv.trim()
  ) {
    throw new Error(
      'Security Invariant Violation: Plaintext visitor record rejected. Offline records MUST be encrypted with AES-GCM before writing to storage.'
    );
  }
  // Scrub any plaintext sensitive keys that may have been erroneously attached to the root item
  const sensitiveFields = [
    'visitor_name',
    'phone_number',
    'vehicle_number',
    'photo_base64',
    'flat_label',
  ];
  for (const field of sensitiveFields) {
    if (field in item && item[field] !== undefined) {
      delete item[field];
    }
  }
}

async function putEncryptedItem(item: EncryptedOfflineVisitorQueueItem): Promise<void> {
  validateEncryptedRecordInvariant(item);
  memoryStore.set(item.client_event_id, item);

  if (!hasNativeIndexedDB()) {
    return;
  }

  const db = await openGateDB();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readwrite');
    const store = tx.objectStore(OFFLINE_QUEUE_STORE);
    store.put(item);
    tx.oncomplete = () => {
      db.close();
      resolve();
    };
    tx.onerror = () => {
      db.close();
      reject(tx.error);
    };
  });
}

/**
 * Returns raw encrypted records directly from storage to verify no plaintext PII survives.
 */
export async function getRawEncryptedRecords(): Promise<any[]> {
  if (hasNativeIndexedDB()) {
    try {
      const db = await openGateDB();
      return await new Promise<any[]>((resolve, reject) => {
        const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readonly');
        const store = tx.objectStore(OFFLINE_QUEUE_STORE);
        const req = store.getAll();
        req.onsuccess = () => {
          db.close();
          resolve((req.result || []) as any[]);
        };
        req.onerror = () => {
          db.close();
          reject(req.error);
        };
      });
    } catch {
      // Fall through to memory store
    }
  }
  return Array.from(memoryStore.values());
}

export async function enqueueOfflineVisitor(params: {
  gate_id: string;
  visitor_name: string;
  phone_number: string;
  vehicle_number?: string | null;
  purpose: VisitorPurposeType;
  destination_flat_id: string;
  flat_label?: string;
  photo_base64?: string | null;
  privacy_notice_version: string;
  client_event_id?: string;
  timestamp?: string;
  photo_captured_at?: string | null;
}): Promise<OfflineVisitorQueueItem> {
  const normalizedPhone = formatPhoneToE164(params.phone_number);
  const normalizedName = params.visitor_name.trim();
  const normalizedVehicle = params.vehicle_number?.trim() || null;
  const timestamp = params.timestamp || new Date().toISOString();

  let photoSha256: string | null = null;
  let photoCapturedAt: string | null = null;

  if (params.photo_base64 && params.photo_base64.trim()) {
    photoSha256 = await computePhotoSha256(params.photo_base64);
    photoCapturedAt = params.photo_captured_at || timestamp;
  }

  const payloadHash = await computePayloadHash({
    visitor_name: normalizedName,
    phone_number: normalizedPhone,
    vehicle_number: normalizedVehicle,
    purpose: params.purpose,
    destination_flat_id: params.destination_flat_id,
    privacy_notice_version: params.privacy_notice_version,
    photo_sha256: photoSha256,
    photo_captured_at: photoCapturedAt,
  });

  const clientEventId = params.client_event_id || generateClientEventId();

  // Encrypt sensitive PII using AES-GCM before writing to storage
  const key = await getOrCreateGateEncryptionKey();
  const sensitiveData: SensitiveVisitorData = {
    visitor_name: normalizedName,
    phone_number: normalizedPhone,
    vehicle_number: normalizedVehicle,
    photo_base64: params.photo_base64 || null,
    flat_label: params.flat_label,
  };
  const { iv, ciphertext } = await encryptSensitivePayload(sensitiveData, key);

  const encryptedItem: EncryptedOfflineVisitorQueueItem = {
    client_event_id: clientEventId,
    gate_id: params.gate_id,
    timestamp,
    purpose: params.purpose,
    destination_flat_id: params.destination_flat_id,
    privacy_notice_version: params.privacy_notice_version,
    payload_hash: payloadHash,
    photo_sha256: photoSha256,
    photo_captured_at: photoCapturedAt,
    sync_status: 'QUEUED',
    approval_status: 'PENDING',
    entry_status: 'EXPECTED',
    error_message: null,
    retry_count: 0,
    server_visitor_id: null,
    iv,
    ciphertext,
  };

  await putEncryptedItem(encryptedItem);

  return {
    client_event_id: clientEventId,
    gate_id: params.gate_id,
    timestamp,
    visitor_name: normalizedName,
    phone_number: normalizedPhone,
    vehicle_number: normalizedVehicle,
    purpose: params.purpose,
    destination_flat_id: params.destination_flat_id,
    flat_label: params.flat_label,
    photo_base64: params.photo_base64 || null,
    photo_sha256: photoSha256,
    photo_captured_at: photoCapturedAt,
    privacy_notice_version: params.privacy_notice_version,
    payload_hash: payloadHash,
    sync_status: 'QUEUED',
    approval_status: 'PENDING',
    entry_status: 'EXPECTED',
    error_message: null,
    retry_count: 0,
    server_visitor_id: null,
  };
}

export async function listOfflineQueue(gateId?: string): Promise<OfflineVisitorQueueItem[]> {
  const rawEncryptedList = await getRawEncryptedRecords();
  const key = await getOrCreateGateEncryptionKey();

  const decryptedItems: OfflineVisitorQueueItem[] = [];
  let foundLegacyRecord = false;

  for (const raw of rawEncryptedList) {
    if (gateId && raw.gate_id !== gateId) {
      continue;
    }

    // Defensive check: if unencrypted legacy record is encountered, read it directly
    // so it is NEVER stranded or presented as [ENCRYPTED_VISITOR]
    if (isLegacyPlaintextRecord(raw)) {
      foundLegacyRecord = true;
      decryptedItems.push({
        client_event_id: raw.client_event_id,
        gate_id: raw.gate_id,
        timestamp: raw.timestamp,
        visitor_name: raw.visitor_name || '',
        phone_number: raw.phone_number ? formatPhoneToE164(raw.phone_number) : '',
        vehicle_number: raw.vehicle_number || null,
        purpose: raw.purpose,
        destination_flat_id: raw.destination_flat_id,
        flat_label: raw.flat_label,
        photo_base64: raw.photo_base64 || null,
        photo_sha256: raw.photo_sha256 || null,
        photo_captured_at: raw.photo_captured_at || null,
        privacy_notice_version: raw.privacy_notice_version || 'v1.0-2026-pune',
        payload_hash: raw.payload_hash,
        sync_status: raw.sync_status || 'QUEUED',
        approval_status: raw.approval_status || 'PENDING',
        entry_status: raw.entry_status || 'EXPECTED',
        error_message: raw.error_message || null,
        retry_count: typeof raw.retry_count === 'number' ? raw.retry_count : 0,
        server_visitor_id: raw.server_visitor_id || null,
      });
      continue;
    }

    try {
      const sensitive = await decryptSensitivePayload(raw.iv, raw.ciphertext, key);
      decryptedItems.push({
        client_event_id: raw.client_event_id,
        gate_id: raw.gate_id,
        timestamp: raw.timestamp,
        visitor_name: sensitive.visitor_name,
        phone_number: sensitive.phone_number,
        vehicle_number: sensitive.vehicle_number,
        purpose: raw.purpose,
        destination_flat_id: raw.destination_flat_id,
        flat_label: sensitive.flat_label,
        photo_base64: sensitive.photo_base64,
        photo_sha256: raw.photo_sha256,
        photo_captured_at: raw.photo_captured_at,
        privacy_notice_version: raw.privacy_notice_version,
        payload_hash: raw.payload_hash,
        sync_status: raw.sync_status,
        approval_status: raw.approval_status,
        entry_status: raw.entry_status,
        error_message: raw.error_message,
        retry_count: raw.retry_count,
        server_visitor_id: raw.server_visitor_id,
      });
    } catch {
      // If decryption fails, emit record with redacted placeholder rather than leaking or crashing
      decryptedItems.push({
        client_event_id: raw.client_event_id,
        gate_id: raw.gate_id,
        timestamp: raw.timestamp,
        visitor_name: '[ENCRYPTED_VISITOR]',
        phone_number: '[ENCRYPTED_PHONE]',
        vehicle_number: null,
        purpose: raw.purpose,
        destination_flat_id: raw.destination_flat_id,
        photo_base64: null,
        photo_sha256: raw.photo_sha256,
        photo_captured_at: raw.photo_captured_at,
        privacy_notice_version: raw.privacy_notice_version,
        payload_hash: raw.payload_hash,
        sync_status: 'FAILED',
        approval_status: raw.approval_status,
        entry_status: raw.entry_status,
        error_message: 'DECRYPTION_FAILED',
        retry_count: raw.retry_count,
        server_visitor_id: raw.server_visitor_id,
      });
    }
  }

  // Trigger background migration so disk storage is encrypted
  if (foundLegacyRecord) {
    migrateLegacyPlaintextRecords().catch((err) => {
      console.warn('Background migration of legacy records failed:', err);
    });
  }

  return decryptedItems.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

export async function updateOfflineQueueStatus(
  clientEventId: string,
  updates: {
    sync_status: OfflineSyncStatus;
    error_message?: string | null;
    server_visitor_id?: string | null;
    increment_retry?: boolean;
  }
): Promise<OfflineVisitorQueueItem | null> {
  const rawList = await getRawEncryptedRecords();
  let target = rawList.find((x) => x.client_event_id === clientEventId);
  if (!target) return null;

  const key = await getOrCreateGateEncryptionKey();

  if (isLegacyPlaintextRecord(target)) {
    target = await migrateSingleRecord(target, key);
  }

  const updatedRaw: EncryptedOfflineVisitorQueueItem = {
    ...target,
    sync_status: updates.sync_status,
    error_message:
      updates.error_message !== undefined ? updates.error_message : target.error_message,
    server_visitor_id:
      updates.server_visitor_id !== undefined
        ? updates.server_visitor_id
        : target.server_visitor_id,
    retry_count: updates.increment_retry ? target.retry_count + 1 : target.retry_count,
  };

  await putEncryptedItem(updatedRaw);

  const sensitive = await decryptSensitivePayload(updatedRaw.iv, updatedRaw.ciphertext, key);

  return {
    client_event_id: updatedRaw.client_event_id,
    gate_id: updatedRaw.gate_id,
    timestamp: updatedRaw.timestamp,
    visitor_name: sensitive.visitor_name,
    phone_number: sensitive.phone_number,
    vehicle_number: sensitive.vehicle_number,
    purpose: updatedRaw.purpose,
    destination_flat_id: updatedRaw.destination_flat_id,
    flat_label: sensitive.flat_label,
    photo_base64: sensitive.photo_base64,
    photo_sha256: updatedRaw.photo_sha256,
    photo_captured_at: updatedRaw.photo_captured_at,
    privacy_notice_version: updatedRaw.privacy_notice_version,
    payload_hash: updatedRaw.payload_hash,
    sync_status: updatedRaw.sync_status,
    approval_status: updatedRaw.approval_status as any,
    entry_status: updatedRaw.entry_status as any,
    error_message: updatedRaw.error_message,
    retry_count: updatedRaw.retry_count,
    server_visitor_id: updatedRaw.server_visitor_id,
  };
}

export async function removeSyncedOfflineItems(gateId?: string): Promise<number> {
  const rawList = await getRawEncryptedRecords();
  let removedCount = 0;

  for (const item of rawList) {
    if (item.sync_status === 'SYNCED' && (!gateId || item.gate_id === gateId)) {
      memoryStore.delete(item.client_event_id);
      removedCount += 1;
    }
  }

  if (hasNativeIndexedDB()) {
    try {
      const db = await openGateDB();
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readwrite');
        const store = tx.objectStore(OFFLINE_QUEUE_STORE);
        for (const item of rawList) {
          if (item.sync_status === 'SYNCED' && (!gateId || item.gate_id === gateId)) {
            store.delete(item.client_event_id);
          }
        }
        tx.oncomplete = () => {
          db.close();
          resolve();
        };
        tx.onerror = () => {
          db.close();
          reject(tx.error);
        };
      });
    } catch {
      // Memory store already cleaned
    }
  }

  return removedCount;
}

export async function clearAllOfflineQueue(): Promise<void> {
  memoryStore.clear();
  if (hasNativeIndexedDB()) {
    try {
      const db = await openGateDB();
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readwrite');
        tx.objectStore(OFFLINE_QUEUE_STORE).clear();
        tx.oncomplete = () => {
          db.close();
          resolve();
        };
        tx.onerror = () => {
          db.close();
          reject(tx.error);
        };
      });
    } catch {
      // Ignore cleanup error
    }
  }
}
