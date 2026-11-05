/**
 * TypeScript definitions for Phase 4 Bank Statement Reconciliation
 */

export type StatementImportStatus =
  | 'UPLOADED'
  | 'VALIDATING'
  | 'READY_FOR_IMPORT'
  | 'PROCESSING'
  | 'COMPLETED'
  | 'COMPLETED_WITH_ERRORS'
  | 'FAILED'
  | 'CANCELLED';

export type TransactionType = 'CREDIT' | 'DEBIT';

export type TransactionReconciliationStatus =
  | 'UNMATCHED'
  | 'SUGGESTED'
  | 'PENDING_APPROVAL'
  | 'APPROVED'
  | 'POSTED'
  | 'REJECTED'
  | 'DUPLICATE'
  | 'UNIDENTIFIED'
  | 'REVERSED';

export type MatchConfidenceTier = 'HIGH' | 'MEDIUM' | 'LOW';

export type MatchingLevel =
  | 'LEVEL_1_UTR'
  | 'LEVEL_2_AMOUNT_REF'
  | 'LEVEL_3_NARRATION_RESIDENT'
  | 'LEVEL_4_INVOICE_AMOUNT'
  | 'LEVEL_5_UNMATCHED'
  | 'MANUAL';

export interface ProposedAllocation {
  invoice_id: string;
  allocated_paise: number;
}

export interface TransactionPreviewItem {
  source_row_number: number;
  transaction_date: string;
  description: string;
  reference_number?: string | null;
  utr_number?: string | null;
  transaction_type: TransactionType;
  debit_paise: number;
  credit_paise: number;
  balance_paise?: number | null;
}

export interface StatementUploadPreview {
  import_id: string;
  file_name: string;
  file_checksum: string;
  status: StatementImportStatus;
  total_rows: number;
  valid_rows: number;
  rejected_rows: number;
  detected_headers: Record<string, string>;
  bank_profile: string;
  preview_transactions: TransactionPreviewItem[];
  rejected_samples: Array<{ row: number; reason: string }>;
  created_at: string;
}

export interface BankStatementImport {
  id: string;
  society_id: string;
  file_name: string;
  file_checksum: string;
  status: StatementImportStatus;
  bank_name?: string | null;
  account_number_mask?: string | null;
  uploaded_by: string;
  total_rows: number;
  valid_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  imported_rows: number;
  error_summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ReconciliationMatch {
  id: string;
  transaction_id: string;
  flat_id?: string | null;
  flat_number?: string | null;
  resident_id?: string | null;
  resident_name?: string | null;
  invoice_id?: string | null;
  invoice_number?: string | null;
  invoice_total_paise?: number | null;
  invoice_outstanding_paise?: number | null;
  existing_payment_id?: string | null;
  existing_payment_reference?: string | null;
  confidence_score: number;
  confidence_tier: MatchConfidenceTier;
  matching_level: MatchingLevel;
  explanation: string;
  evidence: Record<string, unknown>;
  is_selected: boolean;
  created_at: string;
}

export interface BankTransaction {
  id: string;
  society_id: string;
  import_id: string;
  source_row_number: number;
  transaction_date: string;
  value_date?: string | null;
  description: string;
  normalized_description: string;
  reference_number?: string | null;
  utr_number?: string | null;
  transaction_type: TransactionType;
  debit_paise: number;
  credit_paise: number;
  balance_paise?: number | null;
  allocated_paise: number;
  unallocated_paise: number;
  reconciliation_status: TransactionReconciliationStatus;
  transaction_fingerprint: string;
  is_duplicate: boolean;
  duplicate_of_id?: string | null;
  matches: ReconciliationMatch[];
  created_at: string;
  updated_at: string;
}

export interface ManualReviewQueueItem {
  transaction: BankTransaction;
  suggested_match?: ReconciliationMatch | null;
  candidates_count: number;
  queue_category: string;
  latest_review_note?: string | null;
}

export interface ReconciliationSummary {
  society_id: string;
  total_credit_paise: number;
  total_debit_paise: number;
  reconciled_credit_paise: number;
  unmatched_credit_paise: number;
  pending_approval_credit_paise: number;
  total_transactions: number;
  unmatched_count: number;
  suggested_count: number;
  pending_approval_count: number;
  posted_count: number;
  duplicate_count: number;
  unidentified_count: number;
  reconciliation_percentage: number;
}

/** Formats integer paise into Indian Rupee string (₹X,XX,XXX.XX) */
export function formatPaiseToINR(paise: number): string {
  const inr = paise / 100;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
    minimumFractionDigits: 2,
  }).format(inr);
}
