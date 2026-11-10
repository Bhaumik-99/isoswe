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

    if (!supabaseAuth.isConfigured()) {
      setError(
        'Live SMS OTP is only active after configuring Supabase Auth API credentials (VITE_SUPABASE_URL & VITE_SUPABASE_PUBLISHABLE_KEY). For this demo deployment, please use the "Demo Login (All Roles)" tab.'
      );
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
      {/* Header Title inside Card */}
      <div className="space-y-1">
        <h2 className="text-xl font-bold text-slate-900 tracking-tight">Sign in to Workspace</h2>
        <p className="text-sm text-slate-600">
          Choose a role account below for instant demo access or authenticate via Phone OTP.
        </p>
      </div>

      {/* Expired Session Alert */}
      {isSessionExpired && (
        <Alert variant="warning" title="Session Expired">
          Your active login session has expired or was terminated. Please sign in again to continue.
        </Alert>
      )}

      {/* Segmented Pill Tab Switcher (min 44px touch height per UI/UX Pro Max Priority 2) */}
      {isDemoEnabled && (
        <div
          role="tablist"
          aria-label="Authentication methods"
          className="grid grid-cols-2 gap-1.5 p-1 bg-slate-100 rounded-xl border border-slate-200/80"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'demo'}
            onClick={() => {
              setActiveTab('demo');
              setError(null);
            }}
            className={`min-h-[44px] px-3 rounded-lg text-xs font-semibold tracking-wide transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
              activeTab === 'demo'
                ? 'bg-white text-primary-700 shadow-sm border border-slate-200/70'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
            <span>Demo Login (All Roles)</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === 'otp'}
            onClick={() => {
              setActiveTab('otp');
              setError(null);
            }}
            className={`min-h-[44px] px-3 rounded-lg text-xs font-semibold tracking-wide transition-all cursor-pointer flex items-center justify-center gap-1.5 ${
              activeTab === 'otp'
                ? 'bg-white text-primary-700 shadow-sm border border-slate-200/70'
                : 'text-slate-600 hover:text-slate-900'
            }`}
          >
            <KeyRound className="w-3.5 h-3.5" aria-hidden="true" />
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
          <form
            onSubmit={handlePasswordSubmit}
            className="space-y-3.5 bg-slate-50/90 p-4 rounded-xl border border-slate-200"
          >
            <div>
              <label
                htmlFor="demo-username"
                className="block text-xs font-semibold text-slate-700 tracking-wide mb-1.5"
              >
                Username / Email
              </label>
              <div className="relative">
                <User className="absolute left-3.5 top-3 h-4 w-4 text-slate-500" aria-hidden="true" />
                <input
                  id="demo-username"
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="owner@demo.com"
                  className="w-full min-h-[44px] pl-10 pr-3 py-2 text-sm bg-white text-slate-900 placeholder-slate-400 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-600 focus:border-primary-600"
                  required
                />
              </div>
            </div>

            <div>
              <label
                htmlFor="demo-password"
                className="block text-xs font-semibold text-slate-700 tracking-wide mb-1.5"
              >
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3.5 top-3 h-4 w-4 text-slate-500" aria-hidden="true" />
                <input
                  id="demo-password"
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter demo password"
                  className="w-full min-h-[44px] pl-10 pr-11 py-2 text-sm bg-white text-slate-900 placeholder-slate-400 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-600 focus:border-primary-600 font-mono"
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-1 top-1 min-w-[36px] min-h-[36px] flex items-center justify-center text-slate-500 hover:text-slate-900 rounded-md cursor-pointer"
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff className="h-4 w-4" aria-hidden="true" /> : <Eye className="h-4 w-4" aria-hidden="true" />}
                </button>
              </div>
            </div>

            <Button type="submit" variant="primary" size="lg" isLoading={isSubmitting} className="w-full">
              Sign In with Credentials
            </Button>
          </form>

          <div className="p-3 bg-blue-50/70 border border-blue-200/80 rounded-xl text-xs text-slate-700 flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 text-primary-600 flex-shrink-0 mt-0.5" aria-hidden="true" />
            <span>
              <strong className="text-slate-900">Demo Accounts by Role:</strong> Select any persona card to autofill credentials, or click <strong className="text-slate-900">Instant Sign In</strong> to launch that portal directly.
            </span>
          </div>

          <div className="space-y-2.5 max-h-[340px] overflow-y-auto pr-1">
            {DEMO_ACCOUNTS.map((account, idx) => {
              const isSelected = username.toLowerCase() === account.username.toLowerCase();
              const roleDotColors = ['#0F766E', '#2563EB', '#EA580C', '#1D4ED8', '#0284C7', '#059669'];
              const dotColor = roleDotColors[idx % roleDotColors.length];
              return (
                <div
                  key={account.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => handleFillCredentials(account)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                      e.preventDefault();
                      handleFillCredentials(account);
                    }
                  }}
                  className={`w-full text-left p-3.5 rounded-xl border transition-all duration-150 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary-600 ${
                    isSelected
                      ? 'border-primary-600 bg-blue-50/50 ring-1 ring-primary-600 shadow-xs'
                      : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/80'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1 flex-wrap">
                    <div className="font-semibold text-sm text-slate-900 flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                        style={{ backgroundColor: dotColor }}
                      />
                      <span>{account.name}</span>
                      {account.unit && (
                        <span className="text-xs font-normal text-slate-600">
                          • {account.unit}
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] font-semibold px-2.5 py-0.5 rounded-full bg-slate-100 text-primary-700 border border-slate-200 whitespace-nowrap">
                      {account.userType}
                    </span>
                  </div>

                  <p className="text-xs text-slate-600 mb-2.5 pl-4 leading-relaxed">{account.description}</p>

                  <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200/80 pl-4">
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-mono">
                      <span>
                        <span className="text-slate-500">User:</span>{' '}
                        <strong className="text-slate-900 select-all">{account.username}</strong>
                      </span>
                      <span>
                        <span className="text-slate-500">Pass:</span>{' '}
                        <strong className="text-slate-900 select-all">{account.password}</strong>
                      </span>
                    </div>

                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDirectPersonaLogin(account);
                      }}
                      className="inline-flex items-center gap-1.5 min-h-[34px] px-3 py-1 rounded-lg text-xs font-semibold bg-primary-600 text-white hover:bg-primary-700 shadow-xs transition-colors cursor-pointer disabled:opacity-50"
                    >
                      <LogIn className="w-3.5 h-3.5" aria-hidden="true" />
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
        <div className="space-y-4">
          <div className="p-4 bg-amber-50/70 border border-amber-200 rounded-xl text-xs text-slate-800 space-y-2.5">
            <div className="flex items-start gap-2.5">
              <AlertCircle className="w-4 h-4 text-accent flex-shrink-0 mt-0.5" aria-hidden="true" />
              <div className="space-y-1">
                <p className="font-semibold text-slate-900">
                  Demo Deployment Notice — API Configuration Required for Live SMS OTP
                </p>
                <p className="text-slate-700 leading-relaxed">
                  Phone OTP authentication is enabled once production Supabase Auth &amp; SMS gateway API credentials (<code className="px-1.5 py-0.5 bg-white border border-slate-200 rounded text-[11px] font-mono text-slate-900">VITE_SUPABASE_URL</code> &amp; <code className="px-1.5 py-0.5 bg-white border border-slate-200 rounded text-[11px] font-mono text-slate-900">VITE_SUPABASE_PUBLISHABLE_KEY</code>) are configured. In Demo Mode, please use <strong>Demo Login (All Roles)</strong> to sign in across all portals.
                </p>
              </div>
            </div>
            {isDemoEnabled && (
              <div className="pl-6">
                <button
                  type="button"
                  onClick={() => {
                    setActiveTab('demo');
                    setError(null);
                  }}
                  className="inline-flex items-center gap-1.5 min-h-[36px] px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-white text-primary-700 border border-slate-200 hover:bg-primary-600 hover:text-white hover:border-primary-600 transition-colors cursor-pointer shadow-xs"
                >
                  <Sparkles className="w-3.5 h-3.5" aria-hidden="true" />
                  <span>Use Demo Login Instead</span>
                </button>
              </div>
            )}
          </div>

          {!otpSent ? (
            <form onSubmit={handleSendOtp} className="space-y-4">
              <div>
                <label
                  htmlFor="otp-phone-input"
                  className="block text-xs font-semibold text-slate-700 tracking-wide mb-1.5"
                >
                  Registered Mobile Number
                </label>
                <div className="relative">
                  <Phone className="absolute left-3.5 top-3 h-4 w-4 text-slate-500" aria-hidden="true" />
                  <input
                    id="otp-phone-input"
                    type="tel"
                    autoComplete="tel"
                    value={phoneNumber}
                    onChange={(e) => setPhoneNumber(e.target.value)}
                    placeholder="+91 98000 00001"
                    className="w-full min-h-[44px] pl-10 pr-3 py-2 text-sm bg-white text-slate-900 placeholder-slate-400 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-600 focus:border-primary-600"
                    required
                  />
                </div>
                <p className="mt-1.5 text-xs text-slate-600">
                  A 6-digit one-time passcode will be securely dispatched via SMS once the Supabase Auth API is configured.
                </p>
              </div>

              <Button type="submit" variant="primary" size="lg" isLoading={isSubmitting} className="w-full">
                Request Phone OTP
              </Button>
            </form>
          ) : (
            <form onSubmit={handleVerifyOtp} className="space-y-4">
              <div>
                <label
                  htmlFor="otp-code-input"
                  className="block text-xs font-semibold text-slate-700 tracking-wide mb-1.5"
                >
                  Enter 6-Digit OTP Code
                </label>
                <input
                  id="otp-code-input"
                  type="text"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  maxLength={6}
                  value={otpCode}
                  onChange={(e) => setOtpCode(e.target.value)}
                  placeholder="123456"
                  className="w-full min-h-[44px] px-3 py-2 text-center tracking-widest text-lg font-mono bg-white text-slate-900 placeholder-slate-400 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-600"
                  required
                  autoFocus
                />
              </div>

              <div className="flex gap-2.5">
                <Button
                  type="button"
                  variant="outline"
                  size="lg"
                  onClick={() => {
                    setOtpSent(false);
                    setOtpCode('');
                  }}
                  className="flex-1"
                >
                  Change Number
                </Button>
                <Button type="submit" variant="primary" size="lg" isLoading={isSubmitting} className="flex-1">
                  Verify &amp; Sign In
                </Button>
              </div>
            </form>
          )}
        </div>
      )}
    </div>
  );
};
