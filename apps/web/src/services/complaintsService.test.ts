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
});
