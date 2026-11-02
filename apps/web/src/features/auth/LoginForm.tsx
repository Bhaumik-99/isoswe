import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KeyRound, Mail, Sparkles } from 'lucide-react';
import { useAuth } from './AuthContext';
import { Button } from '../../components/ui/Button';
import { Alert } from '../../components/ui/Alert';

interface DevPersona {
  name: string;
  role: string;
  unit?: string;
  token: string;
  description: string;
}

const DEV_PERSONAS: DevPersona[] = [
  {
    name: 'Neeraj Kulkarni',
    role: 'RESIDENT (Owner)',
    unit: 'T07-1203 (1,150 sq ft)',
    token: 'dev-token-neeraj',
    description: 'Owner of Tower 7 unit 1203 with full resident access',
  },
  {
    name: 'Swati Joshi',
    role: 'RESIDENT (Tenant)',
    unit: 'T12-0408 (980 sq ft)',
    token: 'dev-token-swati',
    description: 'Tenant with time-bound approved lease membership',
  },
  {
    name: 'Aamir Shaikh',
    role: 'RESIDENT (Owner)',
    unit: 'T21-1601 (1,640 sq ft)',
    token: 'dev-token-aamir',
    description: 'Owner of penthouse unit in Tower 21',
  },
  {
    name: 'Rajesh Shinde',
    role: 'HELPDESK',
    token: 'dev-token-helpdesk',
    description: 'Facility management staff handling resident maintenance tickets',
  },
  {
    name: 'Priya Deshmukh',
    role: 'FINANCE',
    token: 'dev-token-finance',
    description: 'Society accountant managing maintenance billing and bank matching',
  },
  {
    name: 'Aniket Patwardhan',
    role: 'COMMITTEE_VIEWER',
    token: 'dev-token-committee',
    description: 'Managing committee member with read-only audit & reporting access',
  },
  {
    name: 'Vikram Joshi',
    role: 'PLATFORM_ADMIN',
    token: 'dev-token-admin',
    description: 'Township system administrator with platform-wide oversight',
  },
];

export const LoginForm: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState<'dev' | 'otp'>('dev');
  const [emailOrPhone, setEmailOrPhone] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleDevLogin = async (token: string, role: string) => {
    setError(null);
    setIsSubmitting(true);
    try {
      await login(token);
      if (role.includes('RESIDENT')) {
        navigate('/resident/overview');
      } else if (role.includes('COMMITTEE')) {
        navigate('/committee/overview');
      } else {
        navigate('/staff/overview');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Login failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleSendOtp = (e: React.FormEvent) => {
    e.preventDefault();
    if (!emailOrPhone) {
      setError('Please provide an email or phone number');
      return;
    }
    setError(null);
    setOtpSent(true);
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otpCode) {
      setError('Please enter the OTP verification code');
      return;
    }
    setError(null);
    setIsSubmitting(true);
    try {
      // In production, this completes Cognito Custom Auth Challenge flow
      await login(`otp-token-${emailOrPhone}-${otpCode}`);
      navigate('/resident/overview');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'OTP verification failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Tab Switcher */}
      <div className="flex border-b border-slate-200">
        <button
          onClick={() => setActiveTab('dev')}
          className={`flex-1 pb-3 text-xs font-semibold uppercase tracking-wider transition-colors border-b-2 flex items-center justify-center gap-1.5 ${
            activeTab === 'dev'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <Sparkles className="w-3.5 h-3.5" />
          <span>Local Dev Personas</span>
        </button>
        <button
          onClick={() => setActiveTab('otp')}
          className={`flex-1 pb-3 text-xs font-semibold uppercase tracking-wider transition-colors border-b-2 flex items-center justify-center gap-1.5 ${
            activeTab === 'otp'
              ? 'border-indigo-600 text-indigo-600'
              : 'border-transparent text-slate-500 hover:text-slate-800'
          }`}
        >
          <KeyRound className="w-3.5 h-3.5" />
          <span>OTP Passwordless</span>
        </button>
      </div>

      {error && (
        <Alert variant="error" title="Authentication Error">
          {error}
        </Alert>
      )}

      {/* Dev Personas Panel */}
      {activeTab === 'dev' && (
        <div className="space-y-3">
          <p className="text-xs text-slate-500 leading-relaxed">
            Deterministic synthetic accounts seeded in the local PostgreSQL database for testing RBAC and unit boundaries.
          </p>

          <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
            {DEV_PERSONAS.map((persona) => (
              <button
                key={persona.token}
                onClick={() => handleDevLogin(persona.token, persona.role)}
                disabled={isSubmitting}
                className="w-full text-left p-3 rounded-lg border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/50 transition-all group focus:outline-none focus:ring-2 focus:ring-indigo-600"
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="font-semibold text-xs text-slate-900 group-hover:text-indigo-900">
                    {persona.name}
                  </div>
                  <span className="text-[10px] font-mono font-medium px-2 py-0.5 rounded bg-slate-100 text-slate-700 group-hover:bg-indigo-100 group-hover:text-indigo-800">
                    {persona.role}
                  </span>
                </div>
                {persona.unit && (
                  <div className="text-[11px] font-medium text-slate-600 mb-0.5">
                    Unit: {persona.unit}
                  </div>
                )}
                <div className="text-[11px] text-slate-500 line-clamp-1">{persona.description}</div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Production OTP Flow */}
      {activeTab === 'otp' && (
        <div>
          {!otpSent ? (
            <form onSubmit={handleSendOtp} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Mobile Number or Email
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                  <input
                    type="text"
                    value={emailOrPhone}
                    onChange={(e) => setEmailOrPhone(e.target.value)}
                    placeholder="+91 98000 00001 or resident@example.com"
                    className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-indigo-600"
                    required
                  />
                </div>
                <p className="mt-1.5 text-xs text-slate-500">
                  A 6-digit one-time passcode will be dispatched via SMS / email.
                </p>
              </div>

              <Button type="submit" variant="primary" className="w-full">
                Request Login OTP
              </Button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Enter 6-Digit OTP Code
                </label>
                <input
                  type="text"
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  placeholder="123456"
                  className="w-full px-3 py-2 text-center tracking-widest text-lg font-mono border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-600"
                  required
                  autoFocus
                />
              </div>

              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setOtpSent(false)}
                  className="flex-1"
                >
                  Change Email/Phone
                </Button>
                <Button type="submit" variant="primary" isLoading={isSubmitting} className="flex-1">
                  Verify & Sign In
                </Button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
};
