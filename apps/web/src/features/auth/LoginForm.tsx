import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { KeyRound, Phone, Sparkles, AlertCircle, User, Lock, Eye, EyeOff, LogIn } from 'lucide-react';
import { useAuth } from './AuthContext';
import { Button } from '../../components/ui/Button';
import { Alert } from '../../components/ui/Alert';
import { supabaseAuth } from '../../services/supabaseAuth';

interface DemoAccount {
  id: string;
  userType: string;
  name: string;
  username: string;
  aliases: string[];
  password: string;
  role: string;
  unit?: string;
  token: string;
  targetPath: string;
  description: string;
}

// Deterministic demo credentials for each user type in the Pune township seed dataset
export const DEMO_ACCOUNTS: DemoAccount[] = [
  {
    id: 'resident-owner',
    userType: 'RESIDENT (Owner)',
    name: 'Neeraj Kulkarni',
    username: 'owner@demo.com',
    aliases: ['neeraj.kulkarni@example.com', 'owner', 'neeraj'],
    password: 'Owner@123',
    role: 'RESIDENT',
    unit: 'T07-1203 (1,150 sq ft)',
    token: 'dev-token-neeraj',
    targetPath: '/resident/overview',
    description: 'Flat owner with full access to invoices, amenities, visitors, notices & complaints',
  },
  {
    id: 'resident-tenant',
    userType: 'RESIDENT (Tenant)',
    name: 'Swati Joshi',
    username: 'tenant@demo.com',
    aliases: ['swati.joshi@example.com', 'tenant', 'swati'],
    password: 'Tenant@123',
    role: 'RESIDENT',
    unit: 'T12-0408 (980 sq ft)',
    token: 'dev-token-swati',
    targetPath: '/resident/overview',
    description: 'Tenant with active time-bound lease membership and overdue maintenance invoice',
  },
  {
    id: 'resident-owner-2',
    userType: 'RESIDENT (Penthouse Owner)',
    name: 'Aamir Shaikh',
    username: 'aamir@demo.com',
    aliases: ['aamir.shaikh@example.com', 'aamir'],
    password: 'Aamir@123',
    role: 'RESIDENT',
    unit: 'T21-1601 (1,640 sq ft)',
    token: 'dev-token-aamir',
    targetPath: '/resident/overview',
    description: 'Penthouse owner in Tower 21 with partial payment and receipt history',
  },
  {
    id: 'staff-helpdesk',
    userType: 'STAFF / HELPDESK ADMIN',
    name: 'Rajesh Shinde',
    username: 'staff@demo.com',
    aliases: ['helpdesk@example.com', 'staff', 'helpdesk', 'admin'],
    password: 'Staff@123',
    role: 'HELPDESK',
    token: 'dev-token-helpdesk',
    targetPath: '/staff/overview',
    description: 'Facility & finance staff managing helpdesk tickets, billing, reconciliation, notices & amenities',
  },
  {
    id: 'gate-security',
    userType: 'GATE SECURITY GUARD',
    name: 'Rajesh Shinde (Gate 1)',
    username: 'gate@demo.com',
    aliases: ['gate.security@example.com', 'gate', 'guard'],
    password: 'Gate@123',
    role: 'HELPDESK',
    unit: 'Gate 1 - North Main',
    token: 'dev-token-gate',
    targetPath: '/gate',
    description: 'Perimeter gate security tablet for visitor registration, guest pass QR/code check-in & offline sync',
  },
  {
    id: 'committee-member',
    userType: 'MANAGING COMMITTEE',
    name: 'Aniket Patwardhan',
    username: 'committee@demo.com',
    aliases: ['committee@example.com', 'committee'],
    password: 'Committee@123',
    role: 'HELPDESK',
    token: 'dev-token-committee',
    targetPath: '/staff/committee',
    description: 'Managing committee governance viewer for financial collection KPIs, SLA metrics & audit logs',
  },
];

export const LoginForm: React.FC = () => {
  const isDemoEnabled = import.meta.env.VITE_DISABLE_DEMO_AUTH !== 'true';
  const { login, isSessionExpired, clearSessionExpired } = useAuth();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<'demo' | 'otp'>(isDemoEnabled ? 'demo' : 'otp');
  const [username, setUsername] = useState('owner@demo.com');
  const [password, setPassword] = useState('Owner@123');
  const [showPassword, setShowPassword] = useState(false);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [otpCode, setOtpCode] = useState('');
  const [otpSent, setOtpSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleDirectPersonaLogin = async (account: DemoAccount) => {
    setUsername(account.username);
    setPassword(account.password);
    setError(null);
    clearSessionExpired();
    setIsSubmitting(true);
    try {
      await login(account.token);
      navigate(account.targetPath);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Demo login failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePasswordSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const cleanUser = username.trim().toLowerCase();
    const cleanPass = password.trim();

    if (!cleanUser || !cleanPass) {
      setError('Please enter both a demo username and password.');
      return;
    }

    const matchedAccount = DEMO_ACCOUNTS.find(
      (acc) =>
        acc.username.toLowerCase() === cleanUser ||
        acc.aliases.some((alias) => alias.toLowerCase() === cleanUser)
    );

    if (!matchedAccount || matchedAccount.password !== cleanPass) {
      setError(
        'Invalid demo username or password. Select any user type card below to auto-fill valid demo credentials.'
      );
      return;
    }

    await handleDirectPersonaLogin(matchedAccount);
  };

  const handleFillCredentials = (account: DemoAccount) => {
    setUsername(account.username);
    setPassword(account.password);
    setError(null);
  };

  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phoneNumber.trim()) {
      setError('Please provide a mobile phone number');
      return;
    }

    setError(null);
    clearSessionExpired();
    setIsSubmitting(true);

    try {
      // Genuine Supabase Auth Phone OTP dispatch
      await supabaseAuth.requestPhoneOtp(phoneNumber);
      setOtpSent(true);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to dispatch authentication code');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleVerifyOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!otpCode.trim()) {
      setError('Please enter the 6-digit OTP code sent to your mobile');
      return;
    }

    setError(null);
    setIsSubmitting(true);

    try {
      // Genuine Supabase Auth OTP verification returning signed bearer JWT
      const tokens = await supabaseAuth.verifyPhoneOtp(phoneNumber, otpCode);
      const userRoles = await login(tokens.accessToken, tokens.expiresIn);
      if (userRoles.includes('HELPDESK')) {
        navigate('/staff/overview');
      } else {
        navigate('/resident/overview');
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'OTP verification failed');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-5">
      {/* Expired Session Alert */}
      {isSessionExpired && (
        <Alert variant="warning" title="Session Expired">
          Your active login session has expired or was terminated. Please sign in again to continue.
        </Alert>
      )}

      {/* Tab Switcher */}
      {isDemoEnabled && (
        <div className="flex border-b border-slate-200">
          <button
            type="button"
            onClick={() => {
              setActiveTab('demo');
              setError(null);
            }}
            className={`flex-1 pb-3 text-xs font-semibold uppercase tracking-wider transition-colors border-b-2 flex items-center justify-center gap-1.5 ${
              activeTab === 'demo'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>Demo Login (All Roles)</span>
          </button>
          <button
            type="button"
            onClick={() => {
              setActiveTab('otp');
              setError(null);
            }}
            className={`flex-1 pb-3 text-xs font-semibold uppercase tracking-wider transition-colors border-b-2 flex items-center justify-center gap-1.5 ${
              activeTab === 'otp'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <KeyRound className="w-3.5 h-3.5" />
            <span>Supabase Phone OTP</span>
          </button>
        </div>
      )}

      {error && (
        <Alert variant="error" title="Authentication Error">
          {error}
        </Alert>
      )}

      {/* Demo Username & Password Login + Role Credentials Directory */}
      {isDemoEnabled && activeTab === 'demo' && (
        <div className="space-y-4">
          <form onSubmit={handlePasswordSubmit} className="space-y-3 bg-slate-50 p-3.5 rounded-lg border border-slate-200">
            <div>
              <label
                htmlFor="demo-username"
                className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1"
              >
                Username / Email
              </label>
              <div className="relative">
                <User className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                <input
                  id="demo-username"
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="owner@demo.com"
                  className="w-full pl-9 pr-3 py-2 text-sm bg-white border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-indigo-600"
                  required
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="demo-password"
                className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1"
              >
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                <input
                  id="demo-password"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter demo password"
                  className="w-full pl-9 pr-9 py-2 text-sm bg-white border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-indigo-600 font-mono"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            <Button type="submit" variant="primary" isLoading={isSubmitting} className="w-full">
              Sign In with Credentials
            </Button>
          </form>

          <div className="p-2.5 bg-amber-50 border border-amber-200 rounded-md text-[11px] text-amber-800 flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
            <span>
              <strong>Demo Accounts by Role:</strong> Click any account below to fill its username &amp; password, or click <strong>Instant Sign In</strong> to open that portal directly.
            </span>
          </div>

          <div className="space-y-2 max-h-[320px] overflow-y-auto pr-1">
            {DEMO_ACCOUNTS.map((account) => {
              const isSelected = username.toLowerCase() === account.username.toLowerCase();
              return (
                <div
                  key={account.id}
                  onClick={() => handleFillCredentials(account)}
                  className={`w-full text-left p-3 rounded-lg border transition-all cursor-pointer ${
                    isSelected
                      ? 'border-indigo-500 bg-indigo-50/60 ring-1 ring-indigo-500'
                      : 'border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/30'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <div className="font-semibold text-xs text-slate-900">
                      {account.name}
                      {account.unit && (
                        <span className="ml-1.5 text-[11px] font-normal text-slate-500">
                          • {account.unit}
                        </span>
                      )}
                    </div>
                    <span className="text-[10px] font-mono font-semibold px-2 py-0.5 rounded bg-indigo-100 text-indigo-800 whitespace-nowrap">
                      {account.userType}
                    </span>
                  </div>

                  <div className="text-[11px] text-slate-500 mb-2">{account.description}</div>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-1.5 border-t border-slate-200/70">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] font-mono">
                      <span>
                        <span className="text-slate-400">User:</span>{' '}
                        <strong className="text-slate-800 select-all">{account.username}</strong>
                      </span>
                      <span>
                        <span className="text-slate-400">Pass:</span>{' '}
                        <strong className="text-slate-800 select-all">{account.password}</strong>
                      </span>
                    </div>

                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDirectPersonaLogin(account);
                      }}
                      className="inline-flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-semibold bg-indigo-600 text-white hover:bg-indigo-700 transition-colors disabled:opacity-50"
                    >
                      <LogIn className="w-3 h-3" />
                      <span>Instant Sign In</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Genuine Production Supabase Phone OTP Flow */}
      {(!isDemoEnabled || activeTab === 'otp') && (
        <div>
          {!otpSent ? (
            <form onSubmit={handleSendOtp} className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1.5">
                  Registered Mobile Number
                </label>
                <div className="relative">
                  <Phone className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                  <input
                    type="tel"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    placeholder="+91 98000 00001"
                    className="w-full pl-9 pr-3 py-2 text-sm border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-600 focus:border-indigo-600"
                    required
                  />
                </div>
                <p className="mt-1.5 text-xs text-slate-500">
                  A 6-digit one-time passcode will be securely sent via SMS through Supabase Auth.
                </p>
              </div>

              <Button type="submit" variant="primary" isLoading={isSubmitting} className="w-full">
                Request Phone OTP
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
                  onClick={() => {
                    setOtpSent(false);
                    setOtpCode('');
                  }}
                  className="flex-1"
                >
                  Change Number
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
