import { gateService } from '../../../services/gateService';
import { BatchSyncResponse, OfflineVisitorQueueItem } from '../../../types';
import { listOfflineQueue, updateOfflineQueueStatus } from './gateIndexedDB';

export interface SyncBatchSummary {
  totalAttempted: number;
  acknowledged: number;
  conflicts: number;
  failed: number;
  items: OfflineVisitorQueueItem[];
}

class GateOfflineSyncManager {
  private isSyncing = false;

  /**
   * Synchronizes all QUEUED or FAILED offline events for a specific gate.
   * Preserves per-event isolation: a CONFLICT (409) or ERROR on one event
   * never discards or blocks other valid events in the batch.
   */
  async syncGateQueue(gateId: string, includeFailed = false): Promise<SyncBatchSummary> {
    if (this.isSyncing) {
      const current = await listOfflineQueue(gateId);
      return {
        totalAttempted: 0,
        acknowledged: 0,
        conflicts: 0,
        failed: 0,
        items: current,
      };
    }

    this.isSyncing = true;
    try {
      const queue = await listOfflineQueue(gateId);
      const candidates = queue.filter(
        (item) =>
          item.sync_status === 'QUEUED' || (includeFailed && item.sync_status === 'FAILED')
      );

      if (candidates.length === 0) {
        return {
          totalAttempted: 0,
          acknowledged: 0,
          conflicts: 0,
          failed: 0,
          items: queue,
        };
      }

      for (const item of candidates) {
        await updateOfflineQueueStatus(item.client_event_id, {
          sync_status: 'SYNCING',
          error_message: null,
        });
      }

      const batchPayload = candidates.map((item) => ({
        client_event_id: item.client_event_id,
        timestamp: item.timestamp,
        payload: {
          visitor_name: item.visitor_name,
          phone_number: item.phone_number,
          vehicle_number: item.vehicle_number,
          purpose: item.purpose,
          destination_flat_id: item.destination_flat_id,
          photo_base64: item.photo_base64,
          photo_sha256: item.photo_sha256 || null,
          photo_captured_at: item.photo_captured_at || null,
          privacy_notice_version: item.privacy_notice_version,
        },
      }));

      let response: BatchSyncResponse;
      try {
        response = await gateService.syncOfflineBatch(gateId, batchPayload);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : 'Batch sync network error';
        for (const item of candidates) {
          await updateOfflineQueueStatus(item.client_event_id, {
            sync_status: 'FAILED',
            error_message: message,
            increment_retry: true,
          });
        }
        const updatedQueue = await listOfflineQueue(gateId);
        return {
          totalAttempted: candidates.length,
          acknowledged: 0,
          conflicts: 0,
          failed: candidates.length,
          items: updatedQueue,
        };
      }

      let acknowledged = 0;
      let conflicts = 0;
      let failed = 0;

      for (const res of response.results) {
        if (res.status === 'ACK') {
          acknowledged += 1;
          await updateOfflineQueueStatus(res.client_event_id, {
            sync_status: 'SYNCED',
            server_visitor_id: res.visitor_id || null,
            error_message: null,
          });
        } else if (res.status === 'CONFLICT') {
          conflicts += 1;
          await updateOfflineQueueStatus(res.client_event_id, {
            sync_status: 'CONFLICT',
            server_visitor_id: res.visitor_id || null,
            error_message: res.error_message || 'CONFLICT_EVENT_PAYLOAD_MODIFIED',
          });
        } else {
          failed += 1;
          await updateOfflineQueueStatus(res.client_event_id, {
            sync_status: 'FAILED',
            error_message: res.error_message || 'Sync validation failed',
            increment_retry: true,
          });
        }
      }

      const finalItems = await listOfflineQueue(gateId);
      return {
        totalAttempted: candidates.length,
        acknowledged,
        conflicts,
        failed,
        items: finalItems,
      };
    } finally {
      this.isSyncing = false;
    }
  }
}

export const gateSyncManager = new GateOfflineSyncManager();

