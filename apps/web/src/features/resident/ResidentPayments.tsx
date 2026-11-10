import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { CreditCard, CheckCircle2, Receipt, Printer, X } from 'lucide-react';
import { billingService, formatINR, formatDateTimeIST } from '../../services/billingService';
import { Payment, ReceiptResponse } from '../../types/billing';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { Alert } from '../../components/ui/Alert';
import { Portal } from '../../components/ui/Portal';

export const ResidentPayments: React.FC = () => {
  const [receiptData, setReceiptData] = useState<ReceiptResponse | null>(null);

  const {
    data: payments,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['resident-payments'],
    queryFn: billingService.getResidentPayments,
  });

  const handleFetchReceiptForPayment = async (payment: Payment) => {
    if (!payment.allocations || payment.allocations.length === 0) {
      alert('This payment was not allocated to an invoice.');
      return;
    }
    const invoiceId = payment.allocations[0].invoice_id;
    try {
      const receipt = await billingService.getInvoiceReceipt(invoiceId);
      setReceiptData(receipt);
    } catch (err: any) {
      alert(err?.message || 'Unable to load payment receipt');
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'SUCCESS':
        return <Badge variant="success">SUCCESS</Badge>;
      case 'FAILED':
        return <Badge variant="danger">FAILED</Badge>;
      case 'REFUNDED':
        return <Badge variant="neutral">REFUNDED</Badge>;
      default:
        return <Badge variant="warning">PENDING</Badge>;
    }
  };

  const totalSuccessfulPayments =
    payments?.filter((p) => p.status === 'SUCCESS').reduce((acc, curr) => acc + curr.amount_paise, 0) || 0;

  return (
    <div className="space-y-6">
      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Payment Transactions</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Complete transaction history and digital receipts for society maintenance
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="success">Total Settled: {formatINR(totalSuccessfulPayments)}</Badge>
        </div>
      </div>

      {error && (
        <Alert variant="error" title="Failed to load payments">
          {(error as any)?.message || 'An error occurred fetching transaction history.'}
        </Alert>
      )}

      {/* Payments Table Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div>
            <CardTitle>Transaction History</CardTitle>
            <p className="text-xs text-slate-500 mt-0.5">Simulated test gateway entries and allocations</p>
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : payments && payments.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-600 uppercase font-semibold border-b border-slate-200">
                  <tr>
                    <th className="py-3 px-4">Date & Time</th>
                    <th className="py-3 px-4">Reference</th>
                    <th className="py-3 px-4">Apartment</th>
                    <th className="py-3 px-4">Amount</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Allocated Amount</th>
                    <th className="py-3 px-4 text-right">Receipt</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-normal">
                  {payments.map((pmt) => {
                    const allocatedTotal = pmt.allocations?.reduce((acc, a) => acc + a.allocated_paise, 0) || 0;
                    return (
                      <tr key={pmt.id} className="hover:bg-slate-50/80 transition-colors">
                        <td className="py-3 px-4 text-slate-700 whitespace-nowrap">
                          {formatDateTimeIST(pmt.created_at)}
                        </td>
                        <td className="py-3 px-4 font-mono font-medium text-slate-900">{pmt.provider_reference}</td>
                        <td className="py-3 px-4 text-slate-700">
                          {pmt.tower_number ? `${pmt.tower_number}-${pmt.flat_number}` : `Flat ${pmt.flat_number}`}
                        </td>
                        <td className="py-3 px-4 font-bold text-slate-900">{formatINR(pmt.amount_paise)}</td>
                        <td className="py-3 px-4">{getStatusBadge(pmt.status)}</td>
                        <td className="py-3 px-4 font-mono text-emerald-700 font-medium">
                          {allocatedTotal > 0 ? formatINR(allocatedTotal) : '-'}
                        </td>
                        <td className="py-3 px-4 text-right">
                          {pmt.status === 'SUCCESS' ? (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleFetchReceiptForPayment(pmt)}
                              className="text-xs h-7 px-2 text-indigo-700 hover:text-indigo-900"
                            >
                              <Receipt className="h-3.5 w-3.5 mr-1" />
                              Receipt
                            </Button>
                          ) : (
                            <span className="text-slate-400 text-xs italic">N/A</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-10 text-slate-500 text-xs">
              <CreditCard className="h-8 w-8 text-slate-400 mx-auto mb-2" />
              <p className="font-semibold text-slate-700">No payment transactions recorded yet</p>
              <p className="text-slate-500 mt-1">Payment activity will appear here once you make test payments.</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------- */}
      {/* Modal: Official Receipt View */}
      {/* ------------------------------------------------------------- */}
      {receiptData && (
        <Portal>
          <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full border border-slate-200 overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-emerald-50">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Official Payment Receipt</h3>
                  <p className="text-[11px] text-slate-500 font-mono">{receiptData.receipt_number}</p>
                </div>
              </div>
              <button onClick={() => setReceiptData(null)} className="text-slate-400 hover:text-slate-600 rounded p-1">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="p-5 space-y-4 text-xs font-mono">
              <div className="text-center py-2 border-b border-slate-200">
                <p className="text-sm font-bold text-slate-900">{receiptData.society_name}</p>
                <p className="text-slate-500 text-[11px]">Society Maintenance Receipt</p>
                <p className="text-2xl font-bold text-emerald-700 mt-2">{formatINR(receiptData.amount_paid_paise)}</p>
              </div>

              <div className="space-y-2 text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Payer Name:</span>
                  <span className="font-semibold text-slate-900">{receiptData.payer_name}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Apartment:</span>
                  <span className="font-semibold text-slate-900">
                    {receiptData.tower_number}-{receiptData.flat_number}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Invoice:</span>
                  <span className="font-semibold text-slate-900">{receiptData.invoice_number}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Billing Period:</span>
                  <span className="font-semibold text-slate-900">{receiptData.billing_period}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Payment Date:</span>
                  <span className="font-semibold text-slate-900">{formatDateTimeIST(receiptData.payment_date)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Reference:</span>
                  <span className="font-semibold text-slate-900">{receiptData.provider_reference}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Remaining Balance:</span>
                  <span className="font-bold text-slate-900">{formatINR(receiptData.remaining_outstanding_paise)}</span>
                </div>
              </div>
            </div>

            <div className="px-5 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
              <Button size="sm" variant="outline" onClick={() => window.print()}>
                <Printer className="h-3.5 w-3.5 mr-1" />
                Print Receipt
              </Button>
              <Button size="sm" variant="secondary" onClick={() => setReceiptData(null)}>
                Close
              </Button>
            </div>
          </div>
          </div>
        </Portal>
      )}
    </div>
  );
};
