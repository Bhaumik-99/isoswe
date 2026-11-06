import {
  OfflineSyncStatus,
  OfflineVisitorQueueItem,
  VisitorPurposeType,
} from '../../../types';
import { formatPhoneToE164 } from '../../../services/gateService';

export const GATE_DB_NAME = 'TownshipGateDB';
export const GATE_DB_VERSION = 1;
export const OFFLINE_QUEUE_STORE = 'offline_visitor_queue';
const FALLBACK_STORAGE_KEY = 'isoswe_gate_offline_queue_fallback_v1';

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
}): string {
  const name = (input.visitor_name || '').trim();
  const phone = (input.phone_number || '').trim();
  const vehicle = (input.vehicle_number || '').trim();
  const purpose = (input.purpose || '').trim();
  const flatId = (input.destination_flat_id || '').trim();
  const noticeVer = (input.privacy_notice_version || '').trim();
  return `name:${name}|phone:${phone}|vehicle:${vehicle}|purpose:${purpose}|flat:${flatId}|notice:${noticeVer}`;
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

function hasNativeIndexedDB(): boolean {
  return typeof indexedDB !== 'undefined' && indexedDB !== null;
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

const memoryFallbackStore = new Map<string, OfflineVisitorQueueItem>();

function readFallbackStore(): OfflineVisitorQueueItem[] {
  try {
    if (typeof localStorage !== 'undefined' && typeof localStorage.getItem === 'function') {
      const raw = localStorage.getItem(FALLBACK_STORAGE_KEY);
      if (raw) {
        return JSON.parse(raw) as OfflineVisitorQueueItem[];
      }
    }
  } catch {
    // Fallback to in-memory map
  }
  return Array.from(memoryFallbackStore.values());
}

function writeFallbackStore(items: OfflineVisitorQueueItem[]): void {
  memoryFallbackStore.clear();
  for (const item of items) {
    memoryFallbackStore.set(item.client_event_id, item);
  }
  try {
    if (typeof localStorage !== 'undefined' && typeof localStorage.setItem === 'function') {
      localStorage.setItem(FALLBACK_STORAGE_KEY, JSON.stringify(items));
    }
  } catch {
    // Ignore quota errors
  }
}

export async function putOfflineQueueItem(item: OfflineVisitorQueueItem): Promise<void> {
  // Always mirror in fallback storage so reload survival works across all browser/test environments
  const existing = readFallbackStore().filter((x) => x.client_event_id !== item.client_event_id);
  existing.push(item);
  writeFallbackStore(existing);

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
}): Promise<OfflineVisitorQueueItem> {
  const normalizedPhone = formatPhoneToE164(params.phone_number);
  const normalizedName = params.visitor_name.trim();
  const normalizedVehicle = params.vehicle_number?.trim() || null;
  const payloadHash = await computePayloadHash({
    visitor_name: normalizedName,
    phone_number: normalizedPhone,
    vehicle_number: normalizedVehicle,
    purpose: params.purpose,
    destination_flat_id: params.destination_flat_id,
    privacy_notice_version: params.privacy_notice_version,
  });

  // Security Invariant: Offline registrations are strictly queued as PENDING / EXPECTED
  const item: OfflineVisitorQueueItem = {
    client_event_id: params.client_event_id || generateClientEventId(),
    gate_id: params.gate_id,
    timestamp: params.timestamp || new Date().toISOString(),
    visitor_name: normalizedName,
    phone_number: normalizedPhone,
    vehicle_number: normalizedVehicle,
    purpose: params.purpose,
    destination_flat_id: params.destination_flat_id,
    flat_label: params.flat_label,
    photo_base64: params.photo_base64 || null,
    privacy_notice_version: params.privacy_notice_version,
    payload_hash: payloadHash,
    sync_status: 'QUEUED',
    approval_status: 'PENDING',
    entry_status: 'EXPECTED',
    error_message: null,
    retry_count: 0,
    server_visitor_id: null,
  };

  await putOfflineQueueItem(item);
  return item;
}

export async function listOfflineQueue(gateId?: string): Promise<OfflineVisitorQueueItem[]> {
  let items: OfflineVisitorQueueItem[];

  if (hasNativeIndexedDB()) {
    try {
      const db = await openGateDB();
      items = await new Promise<OfflineVisitorQueueItem[]>((resolve, reject) => {
        const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readonly');
        const store = tx.objectStore(OFFLINE_QUEUE_STORE);
        const req = store.getAll();
        req.onsuccess = () => {
          db.close();
          resolve((req.result || []) as OfflineVisitorQueueItem[]);
        };
        req.onerror = () => {
          db.close();
          reject(req.error);
        };
      });
    } catch {
      items = readFallbackStore();
    }
  } else {
    items = readFallbackStore();
  }

  if (items.length === 0) {
    items = readFallbackStore();
  }

  const filtered = gateId ? items.filter((i) => i.gate_id === gateId) : items;
  return filtered.sort((a, b) => b.timestamp.localeCompare(a.timestamp));
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
  const all = await listOfflineQueue();
  const target = all.find((x) => x.client_event_id === clientEventId);
  if (!target) return null;

  const updated: OfflineVisitorQueueItem = {
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

  await putOfflineQueueItem(updated);
  return updated;
}

export async function removeSyncedOfflineItems(gateId?: string): Promise<number> {
  const all = await listOfflineQueue();
  const toKeep = all.filter(
    (item) => item.sync_status !== 'SYNCED' || (gateId && item.gate_id !== gateId)
  );
  const removedCount = all.length - toKeep.length;
  writeFallbackStore(toKeep);

  if (hasNativeIndexedDB()) {
    try {
      const db = await openGateDB();
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(OFFLINE_QUEUE_STORE, 'readwrite');
        const store = tx.objectStore(OFFLINE_QUEUE_STORE);
        for (const item of all) {
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
      // Fallback already updated
    }
  }

  return removedCount;
}

export async function clearAllOfflineQueue(): Promise<void> {
  writeFallbackStore([]);
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
