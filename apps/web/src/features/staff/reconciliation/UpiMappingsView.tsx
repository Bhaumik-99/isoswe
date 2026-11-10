import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Smartphone,
  Plus,
  Trash2,
  Search,
  X,
  Building,
} from 'lucide-react';
import { reconciliationService } from '../../../services/reconciliationService';
import { ResidentUPIMapping } from '../../../types/reconciliation';
import { Card, CardContent, CardHeader, CardTitle } from '../../../components/ui/Card';
import { Badge } from '../../../components/ui/Badge';
import { Button } from '../../../components/ui/Button';
import { Skeleton } from '../../../components/ui/Skeleton';
import { Alert } from '../../../components/ui/Alert';
import { Portal } from '../../../components/ui/Portal';

export const UpiMappingsView: React.FC = () => {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const [isRegisterModalOpen, setIsRegisterModalOpen] = useState(false);
  const [modalError, setModalError] = useState<string | null>(null);

  const [newMapping, setNewMapping] = useState({
    flat_id: '',
    vpa: '',
    notes: '',
  });

  const {
    data: mappings = [],
    isLoading,
    error,
  } = useQuery<ResidentUPIMapping[]>({
    queryKey: ['staff-upi-mappings'],
    queryFn: () => reconciliationService.listUpiMappings(),
  });

  const createMutation = useMutation({
    mutationFn: () => {
      if (!newMapping.flat_id.trim()) {
        throw new Error('Flat ID is required');
      }
      if (!newMapping.vpa.trim() || !newMapping.vpa.includes('@')) {
        throw new Error('A valid UPI VPA is required (e.g. name@okhdfcbank)');
      }
      return reconciliationService.createUpiMapping({
        flat_id: newMapping.flat_id.trim(),
        vpa: newMapping.vpa.trim(),
        notes: newMapping.notes.trim() || undefined,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staff-upi-mappings'] });
      setIsRegisterModalOpen(false);
      setNewMapping({ flat_id: '', vpa: '', notes: '' });
      setModalError(null);
    },
    onError: (err: any) => {
      setModalError(err?.message || 'Failed to register UPI mapping');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => reconciliationService.deleteUpiMapping(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['staff-upi-mappings'] });
    },
  });

  const filteredMappings = mappings.filter((m) => {
    if (!searchQuery.trim()) return true;
    const q = searchQuery.toLowerCase();
    return (
      m.vpa.toLowerCase().includes(q) ||
      (m.flat_number && m.flat_number.toLowerCase().includes(q)) ||
      (m.notes && m.notes.toLowerCase().includes(q))
    );
  });

  return (
    <div className="space-y-4">
      {/* Search & Actions Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white p-4 rounded-xl border border-gray-200 shadow-sm">
        <div className="relative flex-1 max-w-md">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-gray-400" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search by VPA, Flat number, or Notes..."
            className="w-full pl-9 pr-4 py-2 border border-gray-300 rounded-lg text-xs focus:ring-1 focus:ring-indigo-500 font-mono"
          />
        </div>

        <Button
          size="sm"
          variant="primary"
          onClick={() => setIsRegisterModalOpen(true)}
          className="text-xs"
        >
          <Plus className="w-3.5 h-3.5 mr-1" />
          Register Resident VPA
        </Button>
      </div>

      {error && (
        <Alert variant="error" title="Failed to load UPI mappings">
          {(error as any)?.message || 'Unable to fetch registered VPAs'}
        </Alert>
      )}

      {/* Mappings Table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-bold text-gray-900 flex items-center gap-2">
            <Smartphone className="w-4 h-4 text-indigo-600" />
            Authorized Resident UPI VPAs for Auto-Matching
          </CardTitle>
          <p className="text-xs text-gray-500 mt-0.5">
            Statements with matching payer VPAs are promoted to HIGH confidence tier (≥90%) during automated statement processing.
          </p>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-2 py-4">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : filteredMappings.length === 0 ? (
            <div className="text-center py-10 text-gray-500 text-xs">
              <Smartphone className="w-8 h-8 text-gray-400 mx-auto mb-2" />
              <p className="font-semibold text-gray-800">No UPI Mappings Found</p>
              <p className="mt-1">Register resident VPAs to enable transparent, instant statement auto-matching.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-gray-50 text-gray-600 font-semibold border-b border-gray-200">
                  <tr>
                    <th className="py-2.5 px-3">Resident VPA</th>
                    <th className="py-2.5 px-3">Flat Allotment</th>
                    <th className="py-2.5 px-3">Verification</th>
                    <th className="py-2.5 px-3">Notes</th>
                    <th className="py-2.5 px-3">Registered On</th>
                    <th className="py-2.5 px-3 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 font-mono text-[11px]">
                  {filteredMappings.map((m) => (
                    <tr key={m.id} className="hover:bg-gray-50/80 transition">
                      <td className="py-3 px-3 font-bold text-indigo-700">{m.vpa}</td>
                      <td className="py-3 px-3 font-sans">
                        <div className="flex items-center gap-1 font-semibold text-gray-900">
                          <Building className="w-3 h-3 text-gray-400" />
                          <span>{m.flat_number || `Flat ${m.flat_id.slice(0, 8)}...`}</span>
                        </div>
                      </td>
                      <td className="py-3 px-3 font-sans">
                        <Badge variant={m.is_verified ? 'success' : 'neutral'}>
                          {m.is_verified ? 'VERIFIED' : 'PENDING'}
                        </Badge>
                      </td>
                      <td className="py-3 px-3 text-gray-500 font-sans">{m.notes || '—'}</td>
                      <td className="py-3 px-3 text-gray-400">
                        {new Date(m.created_at).toLocaleDateString('en-IN', {
                          day: '2-digit',
                          month: 'short',
                          year: 'numeric',
                        })}
                      </td>
                      <td className="py-3 px-3 text-right">
                        <button
                          onClick={() => {
                            if (window.confirm(`Remove UPI mapping ${m.vpa}?`)) {
                              deleteMutation.mutate(m.id);
                            }
                          }}
                          disabled={deleteMutation.isPending}
                          className="p-1 text-rose-600 hover:text-rose-800 hover:bg-rose-50 rounded"
                          title="Delete Mapping"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Register VPA Modal */}
      {isRegisterModalOpen && (
        <Portal>
          <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full border border-gray-200 overflow-hidden">
            <div className="px-5 py-4 border-b border-gray-200 flex items-center justify-between bg-gray-50">
              <div className="flex items-center gap-2">
                <Smartphone className="w-5 h-5 text-indigo-600" />
                <h3 className="text-sm font-bold text-gray-900">Register Resident UPI VPA</h3>
              </div>
              <button
                onClick={() => setIsRegisterModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 rounded p-1"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs">
              {modalError && (
                <Alert variant="error" title="Validation Error">
                  {modalError}
                </Alert>
              )}

              <div className="space-y-1">
                <label className="block font-semibold text-gray-700">Resident UPI VPA</label>
                <input
                  type="text"
                  placeholder="e.g. neeraj@okhdfcbank or resident@upi"
                  value={newMapping.vpa}
                  onChange={(e) => setNewMapping((prev) => ({ ...prev, vpa: e.target.value }))}
                  className="w-full px-3 py-1.5 border border-gray-300 rounded font-mono text-xs focus:ring-1 focus:ring-indigo-500"
                />
                <p className="text-[10px] text-gray-500">
                  VPAs will be automatically normalized to lowercase and trimmed.
                </p>
              </div>

              <div className="space-y-1">
                <label className="block font-semibold text-gray-700">Flat UUID</label>
                <input
                  type="text"
                  placeholder="Flat UUID from Registry"
                  value={newMapping.flat_id}
                  onChange={(e) => setNewMapping((prev) => ({ ...prev, flat_id: e.target.value }))}
                  className="w-full px-3 py-1.5 border border-gray-300 rounded font-mono text-xs focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div className="space-y-1">
                <label className="block font-semibold text-gray-700">Notes (Optional)</label>
                <input
                  type="text"
                  placeholder="e.g. Primary resident GPay handle"
                  value={newMapping.notes}
                  onChange={(e) => setNewMapping((prev) => ({ ...prev, notes: e.target.value }))}
                  className="w-full px-3 py-1.5 border border-gray-300 rounded text-xs focus:ring-1 focus:ring-indigo-500"
                />
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-gray-200">
                <Button size="sm" variant="outline" onClick={() => setIsRegisterModalOpen(false)}>
                  Cancel
                </Button>
                <Button
                  size="sm"
                  variant="primary"
                  onClick={() => createMutation.mutate()}
                  disabled={createMutation.isPending}
                >
                  {createMutation.isPending ? 'Registering...' : 'Register VPA'}
                </Button>
              </div>
            </div>
          </div>
          </div>
        </Portal>
      )}
    </div>
  );
};
