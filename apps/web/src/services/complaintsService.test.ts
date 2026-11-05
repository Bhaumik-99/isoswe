import { describe, it, expect, vi, beforeEach } from 'vitest';
import { complaintsService } from './complaintsService';
import { apiClient } from './apiClient';

describe('complaintsService', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('creates resident complaint with expected payload', async () => {
    const mockResponse = {
      id: 'c1',
      complaint_number: 'CMP-202611-0001',
      title: 'Water tap leaking',
      description: 'Kitchen faucet dripping constantly',
      category: 'PLUMBING',
      status: 'SUBMITTED',
      priority: 'MEDIUM',
    };

    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockResponse as any);

    const result = await complaintsService.createComplaint({
      flat_id: 'flat-1',
      title: 'Water tap leaking',
      description: 'Kitchen faucet dripping constantly',
      category: 'PLUMBING',
    });

    expect(requestSpy).toHaveBeenCalledWith('/api/v1/complaints', {
      method: 'POST',
      body: JSON.stringify({
        flat_id: 'flat-1',
        title: 'Water tap leaking',
        description: 'Kitchen faucet dripping constantly',
        category: 'PLUMBING',
      }),
    });
    expect(result.id).toBe('c1');
  });

  it('fetches resident complaints with optional status filter', async () => {
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue([] as any);

    await complaintsService.listResidentComplaints('IN_PROGRESS');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/complaints/me?status=IN_PROGRESS');

    await complaintsService.listResidentComplaints();
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/complaints/me');
  });

  it('submits rating and feedback for resolved complaint', async () => {
    const mockResponse = { id: 'c1', rating: 5, feedback: 'Great job' };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockResponse as any);

    const result = await complaintsService.rateComplaint('c1', 5, 'Great job');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/complaints/me/c1/rating', {
      method: 'POST',
      body: JSON.stringify({ rating: 5, feedback: 'Great job' }),
    });
    expect(result.rating).toBe(5);
  });

  it('reopens resolved complaint with reason', async () => {
    const mockResponse = { id: 'c1', status: 'REOPENED', reopened_count: 1 };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockResponse as any);

    const result = await complaintsService.reopenComplaint('c1', 'Leak started again');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/complaints/me/c1/reopen', {
      method: 'POST',
      body: JSON.stringify({ reason: 'Leak started again' }),
    });
    expect(result.status).toBe('REOPENED');
  });

  it('formats helpdesk query parameters accurately', async () => {
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue([] as any);

    await complaintsService.listHelpdeskComplaints({
      priority: 'CRITICAL',
      category: 'ELECTRICAL',
      is_sla_breached: true,
      search: 'sparking',
      unassigned_only: true,
    });

    expect(requestSpy).toHaveBeenCalledWith(
      expect.stringContaining('/api/v1/complaints/helpdesk?')
    );
    const calledUrl = requestSpy.mock.calls[0][0];
    expect(calledUrl).toContain('priority=CRITICAL');
    expect(calledUrl).toContain('category=ELECTRICAL');
    expect(calledUrl).toContain('is_sla_breached=true');
    expect(calledUrl).toContain('unassigned_only=true');
    expect(calledUrl).toContain('search=sparking');
  });

  it('updates complaint lifecycle status', async () => {
    const mockResponse = { id: 'c1', status: 'IN_PROGRESS' };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockResponse as any);

    const result = await complaintsService.updateComplaintStatus('c1', 'IN_PROGRESS', 'Technician dispatched');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/complaints/helpdesk/c1/status', {
      method: 'PATCH',
      body: JSON.stringify({ status: 'IN_PROGRESS', notes: 'Technician dispatched' }),
    });
    expect(result.status).toBe('IN_PROGRESS');
  });

  it('completes attachment upload and verifies storage receipt', async () => {
    const mockAttachment = {
      id: 'att-1',
      complaint_id: 'c1',
      file_name: 'test.jpg',
      status: 'UPLOADED',
      download_url: 'https://storage/download/att-1',
    };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockAttachment as any);

    const result = await complaintsService.completeAttachmentUpload('c1', 'att-1', false);
    expect(requestSpy).toHaveBeenCalledWith(
      '/api/v1/complaints/me/c1/attachments/att-1/complete',
      { method: 'POST' }
    );
    expect(result.status).toBe('UPLOADED');
  });

  it('corrects complaint category with category and notes payload', async () => {
    const mockComplaint = { id: 'c1', category: 'ELECTRICAL', original_category: 'PLUMBING' };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockComplaint as any);

    const result = await complaintsService.correctCategory('c1', 'ELECTRICAL', 'Reclassified');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/complaints/c1/category', {
      method: 'PATCH',
      body: JSON.stringify({ category: 'ELECTRICAL', notes: 'Reclassified' }),
    });
    expect(result.category).toBe('ELECTRICAL');
  });

  it('links duplicate complaint with duplicate_of_id and notes payload', async () => {
    const mockComplaint = { id: 'c2', duplicate_of_id: 'c1' };
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockComplaint as any);

    const result = await complaintsService.linkDuplicate('c2', 'c1', 'Same pipe leak');
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/complaints/c2/link-duplicate', {
      method: 'POST',
      body: JSON.stringify({ duplicate_of_id: 'c1', notes: 'Same pipe leak' }),
    });
    expect(result.duplicate_of_id).toBe('c1');
  });

  it('fetches safety alerts using unacknowledged_only query param', async () => {
    const mockAlerts = [{ id: 'a1', is_acknowledged: false }];
    const requestSpy = vi.spyOn(apiClient, 'request').mockResolvedValue(mockAlerts as any);

    const result = await complaintsService.getSafetyAlerts(true);
    expect(requestSpy).toHaveBeenCalledWith('/api/v1/complaints/safety-alerts?unacknowledged_only=true');
    expect(result).toHaveLength(1);
  });
});

