import {
  OfflineSyncStatus,
  OfflineVisitorQueueItem,
  VisitorPurposeType,
} from '../../../types';
import { formatPhoneToE164 } from '../../../services/gateService';

export const GATE_DB_NAME = 'TownshipGateDB';
export const GATE_DB_VERSION = 1;
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
  approval_status: 'PENDING';
  entry_status: 'EXPECTED';
  error_message: string | null;
  retry_count: number;
  server_visitor_id: string | null;
  iv: string; // Base64 encoded 12-byte initialization vector
  ciphertext: string; // Base64 encoded AES-GCM ciphertext + auth tag
}

// Module-level in-memory cache for the non-extractable key
let memoryCryptoKey: CryptoKey | null = null;

// In-memory encrypted store for environments without IndexedDB (e.g. Node unit tests)
// Notice: records stored here are strictly EncryptedOfflineVisitorQueueItem with zero plaintext PII
const memoryEncryptedStore = new Map<string, EncryptedOfflineVisitorQueueItem>();

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
    request.onerror = () => reject(request.error);
  });
}

function openGateDB(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(GATE_DB_NAME, GATE_DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(OFFLINE_QUEUE_STORE)) {
        const store = db.createObjectStore(OFFLINE_QUEUE_STORE, {
          keyPath: 'client_event_id',
        });
        store.createIndex('by_gate', 'gate_id', { unique: false });
        store.createIndex('by_status', 'sync_status', { unique: false });
        store.createIndex('by_timestamp', 'timestamp', { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/**
 * Retrieves or initializes the non-extractable AES-GCM 256-bit encryption key.
 * Non-extractable prevents XSS scripts from reading raw key material.
 */
export async function getOrCreateGateEncryptionKey(): Promise<CryptoKey> {
  if (memoryCryptoKey) {
    return memoryCryptoKey;
  }

  if (hasNativeIndexedDB() && typeof crypto !== 'undefined' && crypto.subtle) {
    try {
      const keyDb = await openKeyDB();
      const storedKey = await new Promise<CryptoKey | undefined>((resolve, reject) => {
        const tx = keyDb.transaction(KEY_STORE_NAME, 'readonly');
        const store = tx.objectStore(KEY_STORE_NAME);
        const req = store.get(MASTER_KEY_ID);
        req.onsuccess = () => {
          keyDb.close();
          resolve(req.result as CryptoKey | undefined);
        };
        req.onerror = () => {
          keyDb.close();
          reject(req.error);
        };
      });

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
      await new Promise<void>((resolve, reject) => {
        const tx = saveDb.transaction(KEY_STORE_NAME, 'readwrite');
        const store = tx.objectStore(KEY_STORE_NAME);
        store.put(newKey, MASTER_KEY_ID);
        tx.oncomplete = () => {
          saveDb.close();
          resolve();
        };
        tx.onerror = () => {
          saveDb.close();
          reject(tx.error);
        };
      });

      memoryCryptoKey = newKey;
      return newKey;
    } catch {
      // Fallback if IndexedDB key storage fails
    }
  }

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

async function putEncryptedItem(item: EncryptedOfflineVisitorQueueItem): Promise<void> {
  memoryEncryptedStore.set(item.client_event_id, item);

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
export async function getRawEncryptedRecords(): Promise<EncryptedOfflineVisitorQueueItem[]> {
  if (hasNativeIndexedDB()) {
    try {
      const db = await openGateDB();
      return await new Promise<EncryptedOfflineVisitorQueueItem[]>((resolve, reject) => {
        const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readonly');
        const store = tx.objectStore(OFFLINE_QUEUE_STORE);
        const req = store.getAll();
        req.onsuccess = () => {
          db.close();
          resolve((req.result || []) as EncryptedOfflineVisitorQueueItem[]);
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
  return Array.from(memoryEncryptedStore.values());
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

  for (const raw of rawEncryptedList) {
    if (gateId && raw.gate_id !== gateId) {
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
  const target = rawList.find((x) => x.client_event_id === clientEventId);
  if (!target) return null;

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

  const key = await getOrCreateGateEncryptionKey();
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
    approval_status: updatedRaw.approval_status,
    entry_status: updatedRaw.entry_status,
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
      memoryEncryptedStore.delete(item.client_event_id);
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
  memoryEncryptedStore.clear();
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
