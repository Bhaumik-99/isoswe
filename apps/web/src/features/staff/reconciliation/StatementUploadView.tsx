import React, { useState } from 'react';
import {
  UploadCloud,
  FileCheck,
  AlertTriangle,
  CheckCircle,
  ArrowRight,
  RefreshCw,
} from 'lucide-react';
import { reconciliationService } from '../../../services/reconciliationService';
import {
  BankStatementImport,
  formatPaiseToINR,
  StatementUploadPreview,
} from '../../../types/reconciliation';
import { Alert } from '../../../components/ui/Alert';

interface StatementUploadViewProps {
  onImportConfirmed: (importRecord: BankStatementImport) => void;
}

export const StatementUploadView: React.FC<StatementUploadViewProps> = ({
  onImportConfirmed,
}) => {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [bankProfile, setBankProfile] = useState<string>('AUTO');
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isConfirming, setIsConfirming] = useState<boolean>(false);
  const [preview, setPreview] = useState<StatementUploadPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      if (!file.name.toLowerCase().endsWith('.csv')) {
        setError('Please select a valid CSV bank statement file (.csv)');
        return;
      }
      setSelectedFile(file);
      setError(null);
      setPreview(null);
    }
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      if (!file.name.toLowerCase().endsWith('.csv')) {
        setError('Please drop a valid CSV bank statement file (.csv)');
        return;
      }
      setSelectedFile(file);
      setError(null);
      setPreview(null);
    }
  };

  const handleUploadAndPreview = async () => {
    if (!selectedFile) {
      setError('Please select a file to upload');
      return;
    }

    setIsUploading(true);
    setError(null);
    try {
      const res = await reconciliationService.uploadStatement(selectedFile, bankProfile);
      setPreview(res);
      setSuccessMessage('File validated successfully! Review the detected rows and confirm import.');
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to parse statement file');
    } finally {
      setIsUploading(false);
    }
  };

  const handleConfirm = async () => {
    if (!preview) return;

    setIsConfirming(true);
    setError(null);
    try {
      const confirmed = await reconciliationService.confirmImport(preview.import_id);
      setSuccessMessage(
        `Import confirmed! ${confirmed.imported_rows} transactions imported (${confirmed.duplicate_rows} duplicates detected).`
      );
      setPreview(null);
      setSelectedFile(null);
      onImportConfirmed(confirmed);
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to confirm statement import');
    } finally {
      setIsConfirming(false);
    }
  };

  const handleCancel = async () => {
    if (!preview) return;
    try {
      await reconciliationService.cancelImport(preview.import_id);
      setPreview(null);
      setSelectedFile(null);
      setSuccessMessage('Import cancelled.');
    } catch (err: unknown) {
      setError((err as Error).message || 'Failed to cancel import');
    }
  };

  return (
    <div className="space-y-6">
      {/* Alert Banners */}
      {error && <Alert variant="error" title="Import Error">{error}</Alert>}
      {successMessage && <Alert variant="success" title="Success">{successMessage}</Alert>}

      {!preview ? (
        <div className="bg-white rounded-xl border border-slate-200 p-8 shadow-sm space-y-6">
          <div>
            <h2 className="text-lg font-bold text-slate-900">Upload Bank Statement</h2>
            <p className="text-sm text-slate-500 mt-1">
              Supports CSV statements from HDFC, ICICI, SBI, Axis, and standard Indian bank formats (UTF-8, max 10 MB).
            </p>
          </div>

          {/* Bank Profile Selection */}
          <div className="max-w-xs">
            <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1">
              Bank Format Profile
            </label>
            <select
              value={bankProfile}
              onChange={(e) => setBankProfile(e.target.value)}
              className="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white focus:ring-2 focus:ring-indigo-500"
            >
              <option value="AUTO">Auto-Detect Header Format</option>
              <option value="HDFC">HDFC Bank</option>
              <option value="ICICI">ICICI Bank</option>
              <option value="SBI">State Bank of India (SBI)</option>
              <option value="AXIS">Axis Bank</option>
              <option value="GENERIC">Generic Indian Bank CSV</option>
            </select>
          </div>

          {/* Dropzone */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            className="border-2 border-dashed border-slate-300 hover:border-indigo-500 rounded-xl p-10 flex flex-col items-center justify-center text-center transition bg-slate-50 hover:bg-indigo-50/20 cursor-pointer"
            onClick={() => document.getElementById('statement-file-input')?.click()}
          >
            <UploadCloud className="h-12 w-12 text-indigo-500 mb-3" />
            <input
              id="statement-file-input"
              type="file"
              accept=".csv"
              onChange={handleFileChange}
              className="hidden"
            />
            {selectedFile ? (
              <div className="flex items-center gap-2 text-indigo-700 font-semibold text-sm">
                <FileCheck className="h-5 w-5" />
                <span>{selectedFile.name}</span>
                <span className="text-xs text-slate-500">
                  ({(selectedFile.size / 1024).toFixed(1)} KB)
                </span>
              </div>
            ) : (
              <>
                <span className="font-semibold text-sm text-slate-700">
                  Drag and drop statement CSV here, or click to browse
                </span>
                <span className="text-xs text-slate-400 mt-1">
                  UTF-8 or UTF-8 BOM, up to 10 MB. Delimiters (comma, semicolon) auto-detected.
                </span>
              </>
            )}
          </div>

          {/* Action Button */}
          <div className="flex justify-end">
            <button
              onClick={handleUploadAndPreview}
              disabled={!selectedFile || isUploading}
              className="px-6 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold text-sm rounded-lg shadow transition flex items-center gap-2 disabled:opacity-50"
            >
              {isUploading ? (
                <>
                  <RefreshCw className="h-4 w-4 animate-spin" />
                  Validating Statement...
                </>
              ) : (
                <>
                  Validate & Preview
                  <ArrowRight className="h-4 w-4" />
                </>
              )}
            </button>
          </div>
        </div>
      ) : (
        /* Preview & Confirm View */
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden space-y-6 p-6">
          <div className="flex items-center justify-between border-b border-slate-200 pb-4">
            <div>
              <h2 className="text-lg font-bold text-slate-900">Statement Validation Summary</h2>
              <span className="text-xs font-mono text-slate-500">
                File: {preview.file_name} • Checksum: {preview.file_checksum.substring(0, 16)}...
              </span>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={handleCancel}
                disabled={isConfirming}
                className="px-4 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 font-medium text-sm rounded-lg transition"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirm}
                disabled={isConfirming || preview.valid_rows === 0}
                className="px-6 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold text-sm rounded-lg shadow transition flex items-center gap-2 disabled:opacity-50"
              >
                {isConfirming ? (
                  <>
                    <RefreshCw className="h-4 w-4 animate-spin" />
                    Importing & Matching...
                  </>
                ) : (
                  <>
                    <CheckCircle className="h-4 w-4" />
                    Confirm & Execute Matching ({preview.valid_rows} rows)
                  </>
                )}
              </button>
            </div>
          </div>

          {/* Metrics Tiles */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-slate-50 p-4 rounded-lg border border-slate-200">
              <span className="text-xs text-slate-500 font-semibold block uppercase">Total Rows Read</span>
              <span className="text-2xl font-bold text-slate-900">{preview.total_rows}</span>
            </div>
            <div className="bg-emerald-50 p-4 rounded-lg border border-emerald-200">
              <span className="text-xs text-emerald-700 font-semibold block uppercase">Valid Transactions</span>
              <span className="text-2xl font-bold text-emerald-800">{preview.valid_rows}</span>
            </div>
            <div className="bg-amber-50 p-4 rounded-lg border border-amber-200">
              <span className="text-xs text-amber-700 font-semibold block uppercase">Rejected Rows</span>
              <span className="text-2xl font-bold text-amber-800">{preview.rejected_rows}</span>
            </div>
          </div>

          {/* Detected Headers */}
          <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 text-xs">
            <span className="font-semibold text-slate-700 block mb-1">Detected Column Mapping:</span>
            <div className="flex flex-wrap gap-2">
              {Object.entries(preview.detected_headers).map(([key, val]) => (
                <span key={key} className="bg-white px-2 py-1 rounded border border-slate-200 text-slate-600">
                  <strong className="text-indigo-600">{key}:</strong> {val}
                </span>
              ))}
            </div>
          </div>

          {/* Rejected Rows Notice if any */}
          {preview.rejected_rows > 0 && (
            <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 text-xs space-y-2">
              <div className="flex items-center gap-2 font-semibold text-amber-800">
                <AlertTriangle className="h-4 w-4" />
                <span>Rejected Rows Detail ({preview.rejected_rows} total rejected)</span>
              </div>
              <ul className="list-disc list-inside space-y-1 text-amber-700">
                {preview.rejected_samples.map((rej, i) => (
                  <li key={i}>
                    Row {rej.row}: {rej.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Preview Table */}
          <div>
            <h3 className="text-sm font-bold text-slate-900 mb-2">
              Transaction Preview (First {preview.preview_transactions.length} rows)
            </h3>
            <div className="border border-slate-200 rounded-lg overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-100 text-slate-600 border-b border-slate-200">
                  <tr>
                    <th className="py-2.5 px-3">Row</th>
                    <th className="py-2.5 px-3">Date</th>
                    <th className="py-2.5 px-3">Description</th>
                    <th className="py-2.5 px-3">Ref / UTR</th>
                    <th className="py-2.5 px-3">Type</th>
                    <th className="py-2.5 px-3 text-right">Debit</th>
                    <th className="py-2.5 px-3 text-right">Credit</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {preview.preview_transactions.map((tx, idx) => (
                    <tr key={idx} className="hover:bg-slate-50">
                      <td className="py-2 px-3 text-slate-500">{tx.source_row_number}</td>
                      <td className="py-2 px-3 font-medium text-slate-800">
                        {new Date(tx.transaction_date).toLocaleDateString('en-IN')}
                      </td>
                      <td className="py-2 px-3 text-slate-700 max-w-xs truncate">{tx.description}</td>
                      <td className="py-2 px-3 font-mono text-slate-600">
                        {tx.utr_number || tx.reference_number || '—'}
                      </td>
                      <td className="py-2 px-3">
                        <span
                          className={`px-1.5 py-0.5 rounded font-semibold text-[10px] ${
                            tx.transaction_type === 'CREDIT'
                              ? 'bg-emerald-100 text-emerald-800'
                              : 'bg-rose-100 text-rose-800'
                          }`}
                        >
                          {tx.transaction_type}
                        </span>
                      </td>
                      <td className="py-2 px-3 text-right text-rose-700 font-medium">
                        {tx.debit_paise > 0 ? formatPaiseToINR(tx.debit_paise) : '—'}
                      </td>
                      <td className="py-2 px-3 text-right text-emerald-700 font-semibold">
                        {tx.credit_paise > 0 ? formatPaiseToINR(tx.credit_paise) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
