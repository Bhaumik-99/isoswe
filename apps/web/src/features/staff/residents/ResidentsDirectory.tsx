import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Users,
  Search,
  UserPlus,
  Phone,
  Mail,
  X,
} from 'lucide-react';
import {
  registryService,
  ResidentDirectoryItem,
  CreateMembershipPayload,
} from '../../../services/registryService';
import { MembershipType, MembershipStatus } from '../../../types';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Skeleton } from '../../../components/ui/Skeleton';
import { Alert } from '../../../components/ui/Alert';

export const ResidentsDirectory: React.FC = () => {
  const queryClient = useQueryClient();

  // Search and Filters
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [flatSearch, setFlatSearch] = useState<string>('');
  const [selectedStatus, setSelectedStatus] = useState<string>('ALL');
  const [selectedType, setSelectedType] = useState<string>('ALL');

  // Modal State
  const [isRegisterOpen, setIsRegisterOpen] = useState<boolean>(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [newResident, setNewResident] = useState<{
    full_name: string;
    email: string;
    phone: string;
    flat_id: string;
    membership_type: MembershipType;
    valid_from: string;
    valid_until: string;
    is_primary: boolean;
  }>({
    full_name: '',
    email: '',
    phone: '',
    flat_id: '',
    membership_type: 'TENANT',
    valid_from: new Date().toISOString().slice(0, 10),
    valid_until: new Date(Date.now() + 365 * 24 * 3600 * 1000).toISOString().slice(0, 10),
    is_primary: true,
  });

  // Query: List Residents
  const {
    data: residents = [],
    isLoading,
    error,
  } = useQuery<ResidentDirectoryItem[]>({
    queryKey: ['staff-residents', searchQuery, flatSearch, selectedStatus, selectedType],
    queryFn: () =>
      registryService.listResidents({
        query: searchQuery || undefined,
        flat_number: flatSearch || undefined,
        status: selectedStatus,
        membership_type: selectedType,
      }),
  });

  // Mutation: Update Membership Status
  const updateStatusMutation = useMutation({
    mutationFn: ({
      membershipId,
      status,
      reason,
    }: {
      membershipId: string;
      status: MembershipStatus;
      reason?: string;
    }) =>
      registryService.updateMembershipStatus(membershipId, {
        status,
        rejection_reason: reason,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staff-residents'] });
    },
  });

  // Mutation: Register Membership
  const registerMutation = useMutation({
    mutationFn: (payload: CreateMembershipPayload) => registryService.createMembership(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staff-residents'] });
      setIsRegisterOpen(false);
      setNewResident({
        full_name: '',
        email: '',
        phone: '',
        flat_id: '',
        membership_type: 'TENANT',
        valid_from: new Date().toISOString().slice(0, 10),
        valid_until: new Date(Date.now() + 365 * 24 * 3600 * 1000).toISOString().slice(0, 10),
        is_primary: true,
      });
      setFormError(null);
    },
    onError: (err: unknown) => {
      setFormError(err instanceof Error ? err.message : 'Registration failed');
    },
  });

  const handleRegisterSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newResident.full_name.trim()) {
      setFormError('Resident full name is required');
      return;
    }
    if (!newResident.phone.trim() || newResident.phone.trim().length < 10) {
      setFormError('A valid phone number (at least 10 digits) is required for registration');
      return;
    }
    if (!newResident.flat_id.trim()) {
      setFormError('Flat ID is required');
      return;
    }
    if (newResident.membership_type === 'TENANT' && !newResident.valid_until) {
      setFormError('Tenant memberships require a valid lease end date');
      return;
    }

    setFormError(null);
    registerMutation.mutate({
      full_name: newResident.full_name.trim(),
      email: newResident.email.trim() || undefined,
      phone: newResident.phone.trim(),
      flat_id: newResident.flat_id.trim(),
      membership_type: newResident.membership_type,
      valid_from: new Date(newResident.valid_from).toISOString(),
      valid_until: newResident.valid_until ? new Date(newResident.valid_until).toISOString() : null,
      is_primary: newResident.is_primary,
    });
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Township Resident & Unit Registry</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Verified resident roster, owner/tenant memberships, lease validity, and move-in approvals
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="primary"
            onClick={() => setIsRegisterOpen(true)}
            className="text-xs flex items-center gap-1.5"
          >
            <UserPlus className="h-3.5 w-3.5" />
            Register Resident
          </Button>
        </div>
      </div>

      {error && (
        <Alert variant="error" title="Directory Query Notice">
          {error instanceof Error ? error.message : 'Failed to retrieve resident registry'}
        </Alert>
      )}

      {/* Filter and Search Bar */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-col md:flex-row gap-3">
            <div className="relative flex-1">
              <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Search by resident name, phone, or email..."
                className="w-full pl-9 pr-3 py-2 text-xs border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div className="w-full md:w-44">
              <input
                type="text"
                value={flatSearch}
                onChange={(e) => setFlatSearch(e.target.value)}
                placeholder="Flat No. (e.g. 1203)"
                className="w-full px-3 py-2 text-xs border border-slate-200 rounded-md focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div className="flex items-center gap-2">
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="text-xs border border-slate-200 rounded-md px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="ALL">All Membership Statuses</option>
                <option value="APPROVED">Approved</option>
                <option value="PENDING">Pending Approval</option>
                <option value="TERMINATED">Terminated</option>
                <option value="REJECTED">Rejected</option>
              </select>

              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="text-xs border border-slate-200 rounded-md px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              >
                <option value="ALL">All Types</option>
                <option value="OWNER">Owner</option>
                <option value="TENANT">Tenant</option>
                <option value="FAMILY_MEMBER">Family Member</option>
              </select>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Directory Table */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-sm font-semibold flex items-center gap-2">
            <Users className="h-4 w-4 text-indigo-600" />
            <span>Residents & Unit Allotments</span>
          </CardTitle>
          <span className="text-xs text-slate-500">
            {residents.length} Resident{residents.length !== 1 ? 's' : ''} Listed
          </span>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : residents.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-500">
              No residents matched your search criteria.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-600 font-semibold border-b border-slate-200 uppercase tracking-wider text-[11px]">
                  <tr>
                    <th className="py-2.5 px-3">Resident</th>
                    <th className="py-2.5 px-3">Contact</th>
                    <th className="py-2.5 px-3">Flat / Tower</th>
                    <th className="py-2.5 px-3">Membership</th>
                    <th className="py-2.5 px-3">Lease Validity</th>
                    <th className="py-2.5 px-3">Status</th>
                    <th className="py-2.5 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {residents.map((resident) =>
                    resident.flats.length === 0 ? (
                      <tr key={resident.user_id} className="hover:bg-slate-50">
                        <td className="py-3 px-3 font-semibold text-slate-900">{resident.full_name}</td>
                        <td className="py-3 px-3 text-slate-500">
                          {resident.phone || resident.email || '—'}
                        </td>
                        <td className="py-3 px-3 text-slate-400 italic" colSpan={4}>
                          No active flat allotments
                        </td>
                        <td className="py-3 px-3 text-right text-slate-400">—</td>
                      </tr>
                    ) : (
                      resident.flats.map((flat) => (
                        <tr key={flat.membership_id} className="hover:bg-slate-50">
                          <td className="py-3 px-3">
                            <div className="font-semibold text-slate-900">{resident.full_name}</div>
                            <div className="text-[10px] text-slate-400 font-mono">
                              UID: {resident.user_id.slice(0, 8)}...
                            </div>
                          </td>
                          <td className="py-3 px-3 text-slate-600 space-y-0.5">
                            {resident.phone && (
                              <div className="flex items-center gap-1 text-[11px]">
                                <Phone className="h-3 w-3 text-slate-400" />
                                <span>{resident.phone}</span>
                              </div>
                            )}
                            {resident.email && (
                              <div className="flex items-center gap-1 text-[11px]">
                                <Mail className="h-3 w-3 text-slate-400" />
                                <span>{resident.email}</span>
                              </div>
                            )}
                            {!resident.phone && !resident.email && (
                              <span className="text-slate-400">—</span>
                            )}
                          </td>
                          <td className="py-3 px-3">
                            <div className="font-semibold text-slate-900">
                              {flat.tower_number} - {flat.flat_number}
                            </div>
                            <div className="text-[10px] text-slate-500">
                              {flat.is_primary ? 'Primary Residence' : 'Secondary Allotment'}
                            </div>
                          </td>
                          <td className="py-3 px-3">
                            <Badge
                              variant={
                                flat.membership_type === 'OWNER'
                                  ? 'success'
                                  : flat.membership_type === 'TENANT'
                                  ? 'info'
                                  : 'neutral'
                              }
                            >
                              {flat.membership_type}
                            </Badge>
                          </td>
                          <td className="py-3 px-3 text-slate-600 text-[11px] font-mono">
                            {flat.membership_type === 'OWNER' ? (
                              <span className="text-slate-500">Permanent</span>
                            ) : flat.valid_until ? (
                              <div>
                                <span>Until {new Date(flat.valid_until).toLocaleDateString()}</span>
                                {new Date(flat.valid_until) < new Date() && (
                                  <Badge variant="danger" className="ml-1 text-[9px] py-0">
                                    Expired
                                  </Badge>
                                )}
                              </div>
                            ) : (
                              <span className="text-slate-500">Indefinite</span>
                            )}
                          </td>
                          <td className="py-3 px-3">
                            <Badge
                              variant={
                                (flat.membership_status || flat.status) === 'APPROVED'
                                  ? 'success'
                                  : (flat.membership_status || flat.status) === 'PENDING'
                                  ? 'warning'
                                  : 'danger'
                              }
                            >
                              {flat.membership_status || flat.status}
                            </Badge>
                          </td>
                          <td className="py-3 px-3 text-right">
                            <div className="flex items-center justify-end gap-1.5">
                              {(flat.membership_status || flat.status) === 'PENDING' && (
                                <>
                                  <Button
                                    size="sm"
                                    variant="primary"
                                    onClick={() =>
                                      updateStatusMutation.mutate({
                                        membershipId: flat.membership_id,
                                        status: 'APPROVED',
                                      })
                                    }
                                    disabled={updateStatusMutation.isPending}
                                    className="text-[11px] py-1 px-2 bg-emerald-600 hover:bg-emerald-700 text-white"
                                  >
                                    Approve
                                  </Button>
                                  <Button
                                    size="sm"
                                    variant="outline"
                                    onClick={() =>
                                      updateStatusMutation.mutate({
                                        membershipId: flat.membership_id,
                                        status: 'REJECTED',
                                        reason: 'Staff rejected onboarding application',
                                      })
                                    }
                                    disabled={updateStatusMutation.isPending}
                                    className="text-[11px] py-1 px-2 border-rose-300 text-rose-600 hover:bg-rose-50"
                                  >
                                    Reject
                                  </Button>
                                </>
                              )}
                              {(flat.membership_status || flat.status) === 'APPROVED' && flat.membership_type === 'TENANT' && (
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() =>
                                    updateStatusMutation.mutate({
                                      membershipId: flat.membership_id,
                                      status: 'TERMINATED',
                                      reason: 'Tenant lease move-out processed',
                                    })
                                  }
                                  disabled={updateStatusMutation.isPending}
                                  className="text-[11px] py-1 px-2 text-slate-600 hover:bg-slate-100"
                                >
                                  Terminate
                                </Button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))
                    )
                  )}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Register Resident Modal */}
      {isRegisterOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full overflow-hidden">
            <div className="flex items-center justify-between p-4 border-b border-slate-200">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <UserPlus className="h-5 w-5 text-indigo-600" />
                Register Resident & Flat Allotment
              </h2>
              <button
                onClick={() => setIsRegisterOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={handleRegisterSubmit} className="p-4 space-y-4">
              {formError && (
                <Alert variant="error" title="Submission Error">
                  {formError}
                </Alert>
              )}

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Full Name *
                </label>
                <input
                  type="text"
                  required
                  value={newResident.full_name}
                  onChange={(e) => setNewResident({ ...newResident, full_name: e.target.value })}
                  placeholder="e.g. Priya Sharma"
                  className="w-full text-xs border border-slate-200 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Phone Number * <span className="text-rose-500 font-normal text-[10px]">(Mandatory)</span>
                  </label>
                  <input
                    type="tel"
                    required
                    value={newResident.phone}
                    onChange={(e) => setNewResident({ ...newResident, phone: e.target.value })}
                    placeholder="e.g. +91 9876543210"
                    className="w-full text-xs border border-slate-200 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  {!newResident.phone.trim() && (
                    <span className="text-[10px] text-rose-500 mt-0.5 block">
                      Phone is required for identity & flat verification
                    </span>
                  )}
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Email Address
                  </label>
                  <input
                    type="email"
                    value={newResident.email}
                    onChange={(e) => setNewResident({ ...newResident, email: e.target.value })}
                    placeholder="e.g. priya@example.com"
                    className="w-full text-xs border border-slate-200 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">
                  Flat ID (UUID) *
                </label>
                <input
                  type="text"
                  required
                  value={newResident.flat_id}
                  onChange={(e) => setNewResident({ ...newResident, flat_id: e.target.value })}
                  placeholder="e.g. 33333333-3333-3333-3333-333333331203"
                  className="w-full text-xs font-mono border border-slate-200 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
                <span className="text-[10px] text-slate-500">
                  Tip: Marvel Greenfield T07-1203 is 33333333-3333-3333-3333-333333331203
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Membership Type
                  </label>
                  <select
                    value={newResident.membership_type}
                    onChange={(e) =>
                      setNewResident({
                        ...newResident,
                        membership_type: e.target.value as MembershipType,
                      })
                    }
                    className="w-full text-xs border border-slate-200 rounded-md px-3 py-2 bg-white text-slate-700 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="TENANT">Tenant</option>
                    <option value="OWNER">Owner</option>
                    <option value="FAMILY_MEMBER">Family Member</option>
                  </select>
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Valid From Date
                  </label>
                  <input
                    type="date"
                    required
                    value={newResident.valid_from}
                    onChange={(e) => setNewResident({ ...newResident, valid_from: e.target.value })}
                    className="w-full text-xs border border-slate-200 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>

              {newResident.membership_type === 'TENANT' && (
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">
                    Lease Expiry Date (Valid Until) *
                  </label>
                  <input
                    type="date"
                    required
                    value={newResident.valid_until}
                    onChange={(e) =>
                      setNewResident({ ...newResident, valid_until: e.target.value })
                    }
                    className="w-full text-xs border border-slate-200 rounded-md px-3 py-2 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              )}

              <div className="flex items-center gap-2 pt-2">
                <input
                  type="checkbox"
                  id="is_primary"
                  checked={newResident.is_primary}
                  onChange={(e) =>
                    setNewResident({ ...newResident, is_primary: e.target.checked })
                  }
                  className="rounded text-indigo-600 focus:ring-indigo-500 h-4 w-4"
                />
                <label htmlFor="is_primary" className="text-xs text-slate-700">
                  Primary resident for this unit
                </label>
              </div>

              <div className="flex items-center justify-end gap-2 pt-4 border-t border-slate-200">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setIsRegisterOpen(false)}
                  className="text-xs"
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  variant="primary"
                  disabled={
                    !newResident.full_name.trim() ||
                    !newResident.phone.trim() ||
                    newResident.phone.trim().length < 10 ||
                    !newResident.flat_id.trim() ||
                    registerMutation.isPending
                  }
                  className="text-xs"
                >
                  {registerMutation.isPending ? 'Registering...' : 'Register Resident'}
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
