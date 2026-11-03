import React, { useState, useRef } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  CreditCard,
  Calendar,
  AlertCircle,
  CheckCircle2,
  FileText,
  Printer,
  X,
  TrendingUp,
  Receipt,
} from 'lucide-react';
import { billingService, formatINR, formatDateIST, formatDateTimeIST } from '../../services/billingService';
import { Invoice, InvoiceStatus, Payment, ReceiptResponse } from '../../types/billing';
import { Card, CardContent, CardHeader, CardTitle } from '../../components/ui/Card';
import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { Skeleton } from '../../components/ui/Skeleton';
import { Alert } from '../../components/ui/Alert';

export const ResidentBilling: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedInvoiceForPayment, setSelectedInvoiceForPayment] = useState<Invoice | null>(null);
  const [selectedInvoiceForDetail, setSelectedInvoiceForDetail] = useState<Invoice | null>(null);
  const [receiptData, setReceiptData] = useState<ReceiptResponse | null>(null);
  const [paymentAmountRupees, setPaymentAmountRupees] = useState<string>('');
  const [simulateFailure, setSimulateFailure] = useState<boolean>(false);
  const [paymentError, setPaymentError] = useState<string | null>(null);
  const [paymentSuccessNotice, setPaymentSuccessNotice] = useState<string | null>(null);

  // IDEMPOTENCY: Store a stable key per payment attempt. The same key is reused
  // for retries of the same logical payment. It is regenerated only when the user
  // opens a new payment modal (i.e., starts a new payment attempt).
  // Generating a new random key on every mutation call would defeat idempotency guarantees.
  const idempotencyKeyRef = useRef<string | null>(null);

  // Queries
  const {
    data: summary,
    isLoading: isSummaryLoading,
  } = useQuery({
    queryKey: ['billing-summary'],
    queryFn: billingService.getResidentSummary,
  });

  const {
    data: invoices,
    isLoading: isInvoicesLoading,
    error: invoicesError,
  } = useQuery({
    queryKey: ['resident-invoices'],
    queryFn: () => billingService.getResidentInvoices(),
  });

  // Payment Mutation
  const paymentMutation = useMutation({
    mutationFn: async ({
      invoiceId,
      amountPaise,
      failure,
    }: {
      invoiceId: string;
      amountPaise: number;
      failure: boolean;
    }) => {
      // IDEMPOTENCY: Reuse the stable key for retries of this payment attempt.
      const idempKey = idempotencyKeyRef.current ?? ('pay-' + crypto.randomUUID());
      idempotencyKeyRef.current = idempKey;

      if (failure) {
        return billingService.initiatePayment(invoiceId, amountPaise, true, idempKey);
      }

      try {
        // STEP 1: Server-side Razorpay test order creation
        const order = await billingService.createPaymentOrder(invoiceId, amountPaise);

        // STEP 2: Checkout with Razorpay if script is available
        if (typeof (window as any).Razorpay !== 'undefined') {
          return await new Promise<Payment>((resolve, reject) => {
            const rzp = new (window as any).Razorpay({
              key: order.key_id,
              amount: order.amount_paise,
              currency: order.currency,
              name: 'Township Maintenance',
              description: 'Maintenance Assessment Dues',
              order_id: order.order_id,
              handler: async (response: any) => {
                try {
                  const payment = await billingService.verifyPayment(
                    invoiceId,
                    {
                      razorpay_order_id: response.razorpay_order_id || order.order_id,
                      razorpay_payment_id: response.razorpay_payment_id,
                      razorpay_signature: response.razorpay_signature,
                    },
                    idempKey,
                  );
                  resolve(payment);
                } catch (err) {
                  reject(err);
                }
              },
              modal: {
                ondismiss: () => {
                  reject(new Error('Razorpay payment cancelled by resident.'));
                },
              },
              theme: { color: '#4f46e5' },
            });
            rzp.open();
          });
        }

        // Headless / test-mode fallback when external CDN is not loaded
        return await billingService.initiatePayment(invoiceId, amountPaise, false, idempKey);
      } catch (err: any) {
        if (err?.message?.includes('cancelled')) {
          throw err;
        }
        return await billingService.initiatePayment(invoiceId, amountPaise, false, idempKey);
      }
    },
    onSuccess: (payment) => {
      queryClient.invalidateQueries({ queryKey: ['billing-summary'] });
      queryClient.invalidateQueries({ queryKey: ['resident-invoices'] });
      queryClient.invalidateQueries({ queryKey: ['resident-payments'] });

      if (payment.status === 'SUCCESS') {
        setPaymentSuccessNotice(
          `Payment of ${formatINR(payment.amount_paise)} processed successfully. Ref: ${payment.provider_reference}`
        );
        setSelectedInvoiceForPayment(null);
      } else {
        setPaymentError(
          `Simulated Payment Failed (Status: ${payment.status}). Ref: ${payment.provider_reference}. Invoice balance remains unchanged.`
        );
      }
    },
    onError: (err: any) => {
      setPaymentError(err?.message || 'Payment initiation failed');
    },
  });

  const handleOpenPaymentModal = (invoice: Invoice) => {
    // Generate a fresh idempotency key when the user opens a NEW payment attempt.
    // This key is stable for retries of this specific attempt (see paymentMutation above).
    idempotencyKeyRef.current = 'pay-' + crypto.randomUUID();
    setSelectedInvoiceForPayment(invoice);
    setPaymentAmountRupees((invoice.outstanding_paise / 100).toString());
    setPaymentError(null);
    setSimulateFailure(false);
  };

  const handleSubmitPayment = (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedInvoiceForPayment) return;

    const amountRupeesNum = parseFloat(paymentAmountRupees);
    if (isNaN(amountRupeesNum) || amountRupeesNum <= 0) {
      setPaymentError('Please enter a valid positive payment amount.');
      return;
    }

    const amountPaise = Math.round(amountRupeesNum * 100);
    if (amountPaise > selectedInvoiceForPayment.outstanding_paise) {
      setPaymentError(
        `Payment amount cannot exceed remaining outstanding balance of ${formatINR(selectedInvoiceForPayment.outstanding_paise)}.`
      );
      return;
    }

    setPaymentError(null);
    paymentMutation.mutate({
      invoiceId: selectedInvoiceForPayment.id,
      amountPaise,
      failure: simulateFailure,
    });
  };

  const handleFetchReceipt = async (invoiceId: string) => {
    try {
      const receipt = await billingService.getInvoiceReceipt(invoiceId);
      setReceiptData(receipt);
    } catch (err: any) {
      alert(err?.message || 'Unable to load payment receipt');
    }
  };

  const getStatusBadge = (status: InvoiceStatus, isOverdue: boolean) => {
    if (status === 'PAID') return <Badge variant="success">PAID</Badge>;
    if (status === 'OVERDUE' || isOverdue) return <Badge variant="danger">OVERDUE</Badge>;
    if (status === 'PARTIALLY_PAID') return <Badge variant="info">PARTIALLY PAID</Badge>;
    if (status === 'VOID') return <Badge variant="neutral">VOID</Badge>;
    return <Badge variant="warning">UNPAID</Badge>;
  };

  return (
    <div className="space-y-6">
      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b border-slate-200">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Maintenance & Billing</h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Society maintenance billing ledger, invoice history, and simulated digital payments
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="info">Rate: ₹6.50 / sq ft</Badge>
          <Badge variant="neutral">Period: {summary?.current_billing_period || 'Current'}</Badge>
        </div>
      </div>

      {paymentSuccessNotice && (
        <Alert variant="success" title="Payment Recorded">
          <div className="flex justify-between items-center">
            <span>{paymentSuccessNotice}</span>
            <button
              onClick={() => setPaymentSuccessNotice(null)}
              className="text-emerald-700 hover:text-emerald-900 text-xs font-bold"
            >
              Dismiss
            </button>
          </div>
        </Alert>
      )}

      {/* Summary KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Outstanding Balance */}
        <Card className="border-l-4 border-l-rose-500">
          <CardContent className="pt-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Outstanding</p>
                {isSummaryLoading ? (
                  <Skeleton className="h-8 w-28 mt-1" />
                ) : (
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {formatINR(summary?.total_outstanding_paise || 0)}
                  </p>
                )}
              </div>
              <div className="h-10 w-10 rounded-full bg-rose-50 flex items-center justify-center text-rose-600">
                <CreditCard className="h-5 w-5" />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-3">
              {summary && summary.total_overdue_paise > 0 ? (
                <span className="text-rose-600 font-semibold">
                  Includes {formatINR(summary.total_overdue_paise)} overdue
                </span>
              ) : (
                'All dues current and up to date'
              )}
            </p>
          </CardContent>
        </Card>

        {/* Next Due Date */}
        <Card className="border-l-4 border-l-amber-500">
          <CardContent className="pt-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Next Due Date</p>
                {isSummaryLoading ? (
                  <Skeleton className="h-8 w-28 mt-1" />
                ) : (
                  <p className="text-lg font-bold text-slate-900 mt-1">
                    {summary?.next_due_date ? formatDateIST(summary.next_due_date) : 'No Pending Dues'}
                  </p>
                )}
              </div>
              <div className="h-10 w-10 rounded-full bg-amber-50 flex items-center justify-center text-amber-600">
                <Calendar className="h-5 w-5" />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-3">Monthly cycle due date as per society policy</p>
          </CardContent>
        </Card>

        {/* Lifetime Paid */}
        <Card className="border-l-4 border-l-emerald-500">
          <CardContent className="pt-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Collected</p>
                {isSummaryLoading ? (
                  <Skeleton className="h-8 w-28 mt-1" />
                ) : (
                  <p className="text-2xl font-bold text-slate-900 mt-1">{formatINR(summary?.total_paid_paise || 0)}</p>
                )}
              </div>
              <div className="h-10 w-10 rounded-full bg-emerald-50 flex items-center justify-center text-emerald-600">
                <TrendingUp className="h-5 w-5" />
              </div>
            </div>
            <p className="text-[11px] text-slate-500 mt-3">{summary?.paid_count || 0} fully cleared invoices</p>
          </CardContent>
        </Card>

        {/* Invoices Status Breakdown */}
        <Card className="border-l-4 border-l-indigo-500">
          <CardContent className="pt-5">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Invoice Portfolio</p>
                {isSummaryLoading ? (
                  <Skeleton className="h-8 w-28 mt-1" />
                ) : (
                  <div className="flex items-center gap-2 mt-1">
                    <span className="text-2xl font-bold text-slate-900">
                      {(summary?.unpaid_count || 0) + (summary?.partially_paid_count || 0) + (summary?.paid_count || 0)}
                    </span>
                    <span className="text-xs text-slate-500">Total Billed</span>
                  </div>
                )}
              </div>
              <div className="h-10 w-10 rounded-full bg-indigo-50 flex items-center justify-center text-indigo-600">
                <FileText className="h-5 w-5" />
              </div>
            </div>
            <div className="flex items-center gap-1.5 mt-3 text-[11px]">
              <span className="text-rose-600 font-medium">{summary?.overdue_count || 0} Overdue</span>
              <span>•</span>
              <span className="text-amber-600 font-medium">{summary?.unpaid_count || 0} Unpaid</span>
              <span>•</span>
              <span className="text-emerald-600 font-medium">{summary?.paid_count || 0} Paid</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Invoices Table Card */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between pb-3">
          <div>
            <CardTitle>Invoices & Payment Journey</CardTitle>
            <p className="text-xs text-slate-500 mt-0.5">Authoritative society billing records for your verified apartments</p>
          </div>
        </CardHeader>
        <CardContent>
          {isInvoicesLoading ? (
            <div className="space-y-3">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : invoicesError ? (
            <Alert variant="error" title="Failed to load invoices">
              {(invoicesError as any)?.message || 'An error occurred while fetching billing data.'}
            </Alert>
          ) : invoices && invoices.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-50 text-slate-600 uppercase font-semibold border-b border-slate-200">
                  <tr>
                    <th className="py-3 px-4">Invoice #</th>
                    <th className="py-3 px-4">Period</th>
                    <th className="py-3 px-4">Unit & Area</th>
                    <th className="py-3 px-4">Total Amount</th>
                    <th className="py-3 px-4">Paid</th>
                    <th className="py-3 px-4">Outstanding</th>
                    <th className="py-3 px-4">Due Date</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-normal">
                  {invoices.map((inv) => (
                    <tr key={inv.id} className="hover:bg-slate-50/80 transition-colors">
                      <td className="py-3 px-4 font-mono font-medium text-slate-900">{inv.invoice_number}</td>
                      <td className="py-3 px-4 text-slate-700">{inv.billing_period}</td>
                      <td className="py-3 px-4">
                        <div className="font-medium text-slate-900">
                          {inv.tower_number ? `${inv.tower_number}-${inv.flat_number}` : `Flat ${inv.flat_number}`}
                        </div>
                        <div className="text-[11px] text-slate-500">
                          {inv.area_sqft_snapshot} sq ft @ ₹{(inv.rate_paise_per_sqft_snapshot / 100).toFixed(2)}
                        </div>
                      </td>
                      <td className="py-3 px-4 font-semibold text-slate-900">{formatINR(inv.total_paise)}</td>
                      <td className="py-3 px-4 text-emerald-700 font-medium">{formatINR(inv.paid_paise)}</td>
                      <td className="py-3 px-4">
                        <span
                          className={
                            inv.outstanding_paise > 0 ? 'text-rose-600 font-bold' : 'text-slate-500 font-medium'
                          }
                        >
                          {formatINR(inv.outstanding_paise)}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-slate-600">{formatDateIST(inv.due_date)}</td>
                      <td className="py-3 px-4">{getStatusBadge(inv.status, inv.is_overdue)}</td>
                      <td className="py-3 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {inv.outstanding_paise > 0 ? (
                            <Button
                              size="sm"
                              variant="primary"
                              onClick={() => handleOpenPaymentModal(inv)}
                              className="text-xs h-7 px-2.5"
                            >
                              <CreditCard className="h-3.5 w-3.5 mr-1" />
                              Pay
                            </Button>
                          ) : (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleFetchReceipt(inv.id)}
                              className="text-xs h-7 px-2 text-emerald-700 hover:text-emerald-800"
                            >
                              <Receipt className="h-3.5 w-3.5 mr-1" />
                              Receipt
                            </Button>
                          )}

                          <Button
                            size="sm"
                            variant="secondary"
                            onClick={() => setSelectedInvoiceForDetail(inv)}
                            className="text-xs h-7 px-2"
                            title="View line items & printable view"
                          >
                            <FileText className="h-3.5 w-3.5 mr-1" />
                            Detail
                          </Button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-10 text-slate-500 text-xs">
              <FileText className="h-8 w-8 text-slate-400 mx-auto mb-2" />
              <p className="font-semibold text-slate-700">No invoices generated yet</p>
              <p className="text-slate-500 mt-1">Invoices will appear here once monthly society billing is executed.</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ------------------------------------------------------------- */}
      {/* Modal: Simulated Payment Flow */}
      {/* ------------------------------------------------------------- */}
      {selectedInvoiceForPayment && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full border border-slate-200 overflow-hidden animate-in fade-in zoom-in-95 duration-150">
            <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <div className="h-8 w-8 rounded-full bg-indigo-100 flex items-center justify-center text-indigo-600">
                  <CreditCard className="h-4 w-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Simulate Maintenance Payment</h3>
                  <p className="text-[11px] text-slate-500">Invoice: {selectedInvoiceForPayment.invoice_number}</p>
                </div>
              </div>
              <button
                onClick={() => setSelectedInvoiceForPayment(null)}
                className="text-slate-400 hover:text-slate-600 rounded p-1"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <form onSubmit={handleSubmitPayment} className="p-5 space-y-4 text-xs">
              {paymentError && (
                <Alert variant="error" title="Payment Issue">
                  {paymentError}
                </Alert>
              )}

              {/* Invoice snapshot */}
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200 space-y-1.5 font-mono text-[11px]">
                <div className="flex justify-between">
                  <span className="text-slate-500">Apartment:</span>
                  <span className="font-semibold text-slate-900">
                    {selectedInvoiceForPayment.tower_number}-{selectedInvoiceForPayment.flat_number} (
                    {selectedInvoiceForPayment.area_sqft_snapshot} sq ft)
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Invoice Total:</span>
                  <span className="font-semibold text-slate-900">{formatINR(selectedInvoiceForPayment.total_paise)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Already Paid:</span>
                  <span className="text-emerald-700 font-semibold">
                    {formatINR(selectedInvoiceForPayment.paid_paise)}
                  </span>
                </div>
                <div className="flex justify-between border-t border-slate-200 pt-1 text-xs">
                  <span className="font-bold text-slate-700">Remaining Balance:</span>
                  <span className="font-bold text-rose-600">
                    {formatINR(selectedInvoiceForPayment.outstanding_paise)}
                  </span>
                </div>
              </div>

              {/* Amount input */}
              <div className="space-y-1">
                <label className="block font-semibold text-slate-700">Payment Amount (INR)</label>
                <div className="relative">
                  <span className="absolute left-3 top-2 text-slate-400 font-bold">₹</span>
                  <input
                    type="number"
                    step="0.01"
                    min="1"
                    max={(selectedInvoiceForPayment.outstanding_paise / 100).toString()}
                    value={paymentAmountRupees}
                    onChange={(e) => setPaymentAmountRupees(e.target.value)}
                    required
                    className="w-full pl-7 pr-3 py-1.5 text-sm font-semibold rounded-md border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
                <div className="flex justify-between items-center text-[11px] text-slate-500 pt-1">
                  <span>Supports partial payments</span>
                  <button
                    type="button"
                    onClick={() => setPaymentAmountRupees((selectedInvoiceForPayment.outstanding_paise / 100).toString())}
                    className="text-indigo-600 hover:text-indigo-800 font-semibold"
                  >
                    Pay Full Dues
                  </button>
                </div>
              </div>

              {/* Simulation outcome toggle */}
              <div className="p-3 bg-amber-50 rounded-lg border border-amber-200 space-y-2">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={simulateFailure}
                    onChange={(e) => setSimulateFailure(e.target.checked)}
                    className="rounded border-amber-400 text-amber-600 focus:ring-amber-500 h-4 w-4"
                  />
                  <span className="font-semibold text-amber-900 text-xs">Simulate Failed Payment Outcome</span>
                </label>
                <p className="text-[11px] text-amber-700">
                  Demonstrates payment resilience: creates a FAILED payment record while leaving invoice balance and status
                  unchanged.
                </p>
              </div>

              <div className="p-2.5 bg-slate-100 rounded text-[11px] text-slate-500 flex items-center gap-2">
                <AlertCircle className="h-4 w-4 text-slate-400 shrink-0" />
                <span>Razorpay Test Mode / Simulated Payment. Idempotency-Key prevents duplicate charge.</span>
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100">
                <Button type="button" variant="outline" size="sm" onClick={() => setSelectedInvoiceForPayment(null)}>
                  Cancel
                </Button>
                <Button type="submit" variant="primary" size="sm" isLoading={paymentMutation.isPending}>
                  Confirm Payment
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Modal: Printable Invoice Detail */}
      {/* ------------------------------------------------------------- */}
      {selectedInvoiceForDetail && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-2xl w-full border border-slate-200 overflow-hidden max-h-[90vh] flex flex-col">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <FileText className="h-5 w-5 text-indigo-600" />
                <h3 className="text-sm font-bold text-slate-900">
                  Maintenance Invoice {selectedInvoiceForDetail.invoice_number}
                </h3>
              </div>
              <div className="flex items-center gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => window.print()}
                  className="text-xs h-7 px-2.5 print:hidden"
                >
                  <Printer className="h-3.5 w-3.5 mr-1" />
                  Print
                </Button>
                <button
                  onClick={() => setSelectedInvoiceForDetail(null)}
                  className="text-slate-400 hover:text-slate-600 rounded p-1"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>
            </div>

            <div className="p-6 overflow-y-auto space-y-6 text-xs printable-invoice">
              {/* Invoice Header */}
              <div className="flex justify-between items-start border-b border-slate-200 pb-4">
                <div>
                  <h2 className="text-base font-bold text-slate-900">Marvel Greenfield Residences</h2>
                  <p className="text-slate-500">Township Co-operative Housing Society Ltd.</p>
                  <p className="text-slate-500">Pune, Maharashtra • Timezone: Asia/Kolkata</p>
                </div>
                <div className="text-right space-y-0.5">
                  <span className="text-sm font-mono font-bold text-indigo-600">
                    {selectedInvoiceForDetail.invoice_number}
                  </span>
                  <p className="text-slate-500">Period: {selectedInvoiceForDetail.billing_period}</p>
                  <p className="text-slate-500">Due Date: {formatDateIST(selectedInvoiceForDetail.due_date)}</p>
                  <div className="pt-1">
                    {getStatusBadge(selectedInvoiceForDetail.status, selectedInvoiceForDetail.is_overdue)}
                  </div>
                </div>
              </div>

              {/* Bill To Info */}
              <div className="grid grid-cols-2 gap-4 p-3 bg-slate-50 rounded-lg border border-slate-200 text-slate-700">
                <div>
                  <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Bill To</p>
                  <p className="font-bold text-slate-900 text-sm mt-0.5">
                    {selectedInvoiceForDetail.resident_name || 'Resident Member'}
                  </p>
                  <p className="text-slate-600">
                    Unit: {selectedInvoiceForDetail.tower_number}-{selectedInvoiceForDetail.flat_number}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">Area & Rate Formula</p>
                  <p className="font-bold text-slate-900 text-sm mt-0.5">
                    {selectedInvoiceForDetail.area_sqft_snapshot} sq ft
                  </p>
                  <p className="text-slate-600 font-mono">
                    ₹{(selectedInvoiceForDetail.rate_paise_per_sqft_snapshot / 100).toFixed(2)} per sq ft
                  </p>
                </div>
              </div>

              {/* Line Items Table */}
              <div>
                <p className="font-bold text-slate-800 mb-2">Itemized Assessment</p>
                <table className="w-full text-left text-xs border border-slate-200 rounded overflow-hidden">
                  <thead className="bg-slate-100 text-slate-600 uppercase font-semibold">
                    <tr>
                      <th className="py-2 px-3">Description</th>
                      <th className="py-2 px-3 text-center">Qty / Area</th>
                      <th className="py-2 px-3 text-right">Unit Rate</th>
                      <th className="py-2 px-3 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {selectedInvoiceForDetail.line_items.map((item) => (
                      <tr key={item.id}>
                        <td className="py-2 px-3 font-medium text-slate-900">{item.description}</td>
                        <td className="py-2 px-3 text-center text-slate-600">{item.quantity.toLocaleString()} sq ft</td>
                        <td className="py-2 px-3 text-right font-mono text-slate-600">
                          ₹{(item.unit_rate_paise / 100).toFixed(2)}
                        </td>
                        <td className="py-2 px-3 text-right font-semibold text-slate-900">
                          {formatINR(item.amount_paise)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot className="bg-slate-50 font-bold border-t border-slate-200">
                    <tr>
                      <td colSpan={3} className="py-2 px-3 text-right text-slate-700">
                        Total Invoice Amount:
                      </td>
                      <td className="py-2 px-3 text-right text-slate-900">
                        {formatINR(selectedInvoiceForDetail.total_paise)}
                      </td>
                    </tr>
                    <tr>
                      <td colSpan={3} className="py-2 px-3 text-right text-emerald-700">
                        Valid Payment Allocations:
                      </td>
                      <td className="py-2 px-3 text-right text-emerald-700">
                        - {formatINR(selectedInvoiceForDetail.paid_paise)}
                      </td>
                    </tr>
                    <tr className="border-t border-slate-300 text-sm">
                      <td colSpan={3} className="py-2.5 px-3 text-right text-slate-900 font-extrabold">
                        Net Outstanding Balance:
                      </td>
                      <td className="py-2.5 px-3 text-right text-rose-600 font-extrabold">
                        {formatINR(selectedInvoiceForDetail.outstanding_paise)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>

              {/* Existing Allocations if any */}
              {selectedInvoiceForDetail.allocations && selectedInvoiceForDetail.allocations.length > 0 && (
                <div>
                  <p className="font-bold text-slate-800 mb-2">Recorded Payment Allocations</p>
                  <div className="space-y-1.5 font-mono text-[11px]">
                    {selectedInvoiceForDetail.allocations.map((alloc) => (
                      <div
                        key={alloc.id}
                        className="p-2 rounded bg-emerald-50/60 border border-emerald-200 flex justify-between items-center text-emerald-800"
                      >
                        <span>Allocated on {formatDateTimeIST(alloc.created_at)}</span>
                        <span className="font-bold">+{formatINR(alloc.allocated_paise)}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            <div className="px-6 py-3 border-t border-slate-200 bg-slate-50 flex items-center justify-between">
              <span className="text-[11px] text-slate-500">Immutable record logged in financial_ledger_entries</span>
              <Button size="sm" variant="secondary" onClick={() => setSelectedInvoiceForDetail(null)}>
                Close
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* ------------------------------------------------------------- */}
      {/* Modal: Official Payment Receipt */}
      {/* ------------------------------------------------------------- */}
      {receiptData && (
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
      )}
    </div>
  );
};
