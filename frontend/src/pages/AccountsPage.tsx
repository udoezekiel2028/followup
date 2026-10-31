import React, { useState, useEffect } from 'react';
import { 
  Mail, ShieldCheck, AlertTriangle, RefreshCw, Plus, 
  Trash2, Power, Settings2, CheckCircle2, XCircle, 
  Send, MessageSquare, Clock, Globe, Database, ArrowUpRight,
  Shield, Copy, Check, ExternalLink, Sparkles
} from 'lucide-react';
import { apiClient } from '../services/api';
import { ConnectedAccount, ConnectSmtpImapPayload, DeliverabilityCheckResult } from '../types';

interface AccountsPageProps {
  onAccountListUpdated: () => void;
}

export const AccountsPage: React.FC<AccountsPageProps> = ({ onAccountListUpdated }) => {
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionLoading, setActionLoading] = useState<string | null>(null);
  const [alert, setAlert] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // SMTP/IMAP Modal State
  const [isSmtpModalOpen, setIsSmtpModalOpen] = useState<boolean>(false);
  const [smtpForm, setSmtpForm] = useState<ConnectSmtpImapPayload>({
    email_address: '',
    smtp_host: 'smtp.hostinger.com',
    smtp_port: 465,
    smtp_username: '',
    smtp_password: '',
    smtp_encryption: 'SSL',
    imap_host: 'imap.hostinger.com',
    imap_port: 993,
    imap_username: '',
    imap_password: '',
    imap_encryption: 'SSL',
    daily_sending_limit: 50,
  });

  // Limit Edit Modal State
  const [editingLimitAccount, setEditingLimitAccount] = useState<ConnectedAccount | null>(null);
  const [newLimitVal, setNewLimitVal] = useState<number>(50);

  // Deliverability Modal State
  const [deliverabilityAccount, setDeliverabilityAccount] = useState<ConnectedAccount | null>(null);
  const [deliverabilityData, setDeliverabilityData] = useState<DeliverabilityCheckResult | null>(null);
  const [deliverabilityLoading, setDeliverabilityLoading] = useState<boolean>(false);
  const [isDeliverabilityModalOpen, setIsDeliverabilityModalOpen] = useState<boolean>(false);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const handleCopy = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleOpenHostingerPreset = () => {
    setSmtpForm({
      email_address: '',
      smtp_host: 'smtp.hostinger.com',
      smtp_port: 465,
      smtp_username: '',
      smtp_password: '',
      smtp_encryption: 'SSL',
      imap_host: 'imap.hostinger.com',
      imap_port: 993,
      imap_username: '',
      imap_password: '',
      imap_encryption: 'SSL',
      daily_sending_limit: 50,
    });
    setIsSmtpModalOpen(true);
  };

  const handleOpenGenericSmtp = () => {
    setSmtpForm({
      email_address: '',
      smtp_host: '',
      smtp_port: 465,
      smtp_username: '',
      smtp_password: '',
      smtp_encryption: 'SSL',
      imap_host: '',
      imap_port: 993,
      imap_username: '',
      imap_password: '',
      imap_encryption: 'SSL',
      daily_sending_limit: 50,
    });
    setIsSmtpModalOpen(true);
  };

  const handleCheckDeliverability = async (acc: ConnectedAccount) => {
    try {
      setDeliverabilityAccount(acc);
      setDeliverabilityLoading(true);
      setIsDeliverabilityModalOpen(true);
      const data = await apiClient.getAccountDeliverability(acc.id);
      setDeliverabilityData(data);
    } catch (err: any) {
      setAlert({ 
        type: 'error', 
        text: 'Deliverability check failed: ' + (err.response?.data?.detail || err.message) 
      });
    } finally {
      setDeliverabilityLoading(false);
    }
  };

  const loadAccounts = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getAccounts();
      setAccounts(data);
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to load email accounts: ' + err.message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAccounts();

    // Check for Google OAuth callback parameters in URL
    const params = new URLSearchParams(window.location.search);
    if (params.get('connected') === 'true') {
      setAlert({
        type: 'success',
        text: `Mailbox ${params.get('email') || ''} connected successfully via Google OAuth 2.0!`,
      });
      window.history.replaceState({}, '', window.location.pathname);
      loadAccounts();
      onAccountListUpdated();
    } else if (params.get('error')) {
      setAlert({
        type: 'error',
        text: 'OAuth Notice: ' + params.get('error'),
      });
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const handleConnectGoogle = async () => {
    try {
      const data = await apiClient.getGoogleAuthUrl();
      if (data.warning) {
        setAlert({
          type: 'error',
          text: data.warning + ' — Please configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env',
        });
      }
      if (data.auth_url) {
        window.location.href = data.auth_url;
      }
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to initiate Google OAuth: ' + err.message });
    }
  };

  const handleConnectSmtpSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      setActionLoading('smtp-connecting');
      const res = await apiClient.connectSmtpImap(smtpForm);
      setAlert({ type: 'success', text: res.message || 'SMTP/IMAP mailbox connected successfully!' });
      setIsSmtpModalOpen(false);
      await loadAccounts();
      onAccountListUpdated();
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Connection failed: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setActionLoading(null);
    }
  };

  const handleTestConnection = async (accountId: string) => {
    try {
      setActionLoading(`test-${accountId}`);
      const res = await apiClient.testAccount(accountId);
      if (res.healthy) {
        setAlert({ type: 'success', text: `Test successful: ${res.message}` });
      } else {
        setAlert({ type: 'error', text: `Test failed: ${res.message}` });
      }
      await loadAccounts();
      onAccountListUpdated();
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Test connection failed: ' + err.message });
    } finally {
      setActionLoading(null);
    }
  };

  const handleToggleAutomation = async (acc: ConnectedAccount) => {
    try {
      setActionLoading(`toggle-${acc.id}`);
      await apiClient.toggleAccountAutomation(acc.id);
      await loadAccounts();
      onAccountListUpdated();
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to toggle automation: ' + err.message });
    } finally {
      setActionLoading(null);
    }
  };

  const handleSaveLimit = async () => {
    if (!editingLimitAccount) return;
    try {
      setActionLoading(`limit-${editingLimitAccount.id}`);
      await apiClient.updateAccountLimits(editingLimitAccount.id, newLimitVal);
      setEditingLimitAccount(null);
      await loadAccounts();
      onAccountListUpdated();
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to update limit: ' + err.message });
    } finally {
      setActionLoading(null);
    }
  };

  const handleDisconnect = async (accountId: string, email: string) => {
    if (!confirm(`Are you sure you want to disconnect ${email}? The other mailboxes will continue operating.`)) return;
    try {
      setActionLoading(`disconnect-${accountId}`);
      await apiClient.disconnectAccount(accountId);
      setAlert({ type: 'success', text: `Mailbox ${email} disconnected safely.` });
      await loadAccounts();
      onAccountListUpdated();
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to disconnect account: ' + err.message });
    } finally {
      setActionLoading(null);
    }
  };

  const handleDelete = async (accountId: string, email: string) => {
    if (!confirm(`Delete mailbox ${email}? All associated conversation history will be permanently removed.`)) return;
    try {
      setActionLoading(`delete-${accountId}`);
      await apiClient.deleteAccount(accountId);
      setAlert({ type: 'success', text: `Mailbox ${email} deleted.` });
      await loadAccounts();
      onAccountListUpdated();
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to delete account: ' + err.message });
    } finally {
      setActionLoading(null);
    }
  };

  const handleSeedSixMailboxes = async () => {
    try {
      setActionLoading('seed-demo');
      const res = await apiClient.seedDemoData();
      setAlert({ type: 'success', text: res.message || 'Seeded 6 initial mailboxes successfully!' });
      await loadAccounts();
      onAccountListUpdated();
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to seed mailboxes: ' + err.message });
    } finally {
      setActionLoading(null);
    }
  };

  return (
    <div className="space-y-6 max-w-7xl pb-16">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-white">Email Accounts Management</h1>
            <span className="rounded-full bg-blue-500/10 border border-blue-500/30 px-2 py-0.5 text-xs font-semibold text-blue-400">
              {accounts.length} Connected Mailboxes
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Manage multiple Gmail and Professional SMTP/IMAP mailboxes with isolated credentials, health checks, and independent daily sending quotas
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {/* Seed Demo Configuration Button */}
          <button
            type="button"
            onClick={handleSeedSixMailboxes}
            disabled={actionLoading === 'seed-demo'}
            className="flex items-center gap-1.5 rounded-xl border border-indigo-500/30 bg-indigo-950/30 px-3.5 py-2 text-xs font-semibold text-indigo-300 hover:bg-indigo-900/40 transition-all disabled:opacity-50"
            title="Seeds initial configuration: 4 Gmail + 2 Hostinger/Professional SMTP/IMAP mailboxes"
          >
            <Database className="h-3.5 w-3.5" />
            <span>{actionLoading === 'seed-demo' ? 'Seeding...' : 'Seed 6 Mailboxes'}</span>
          </button>

          {/* Connect Gmail Button */}
          <button
            type="button"
            onClick={handleConnectGoogle}
            className="flex items-center gap-2 rounded-xl bg-white px-3.5 py-2 text-xs font-bold text-slate-900 shadow-md hover:bg-slate-100 transition-all"
          >
            <svg className="h-3.5 w-3.5" viewBox="0 0 24 24">
              <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.65v3h3.88c2.27-2.09 3.66-5.17 3.66-9.09z" />
              <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.27v3.09C3.29 21.43 7.37 24 12 24z" />
              <path fill="#FBBC05" d="M5.28 14.32c-.25-.72-.38-1.49-.38-2.32s.13-1.6.38-2.32V6.59H1.27C.46 8.21 0 10.05 0 12s.46 3.79 1.27 5.41l4.01-3.09z" />
              <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.37 0 3.29 2.57 1.27 6.59l4.01 3.09c.95-2.83 3.6-4.93 6.72-4.93z" />
            </svg>
            <span>Connect Gmail</span>
          </button>

          {/* Connect Hostinger Email Button */}
          <button
            type="button"
            onClick={handleOpenHostingerPreset}
            className="flex items-center gap-1.5 rounded-xl border border-purple-500/40 bg-purple-950/40 px-3.5 py-2 text-xs font-semibold text-purple-200 hover:bg-purple-900/50 transition-all shadow-md shadow-purple-950/40"
            title="Connect Hostinger professional mailbox with pre-filled IMAP/SMTP host and port settings"
          >
            <Globe className="h-3.5 w-3.5 text-purple-400" />
            <span>Connect Hostinger Email</span>
          </button>

          {/* Connect Custom SMTP/IMAP */}
          <button
            type="button"
            onClick={handleOpenGenericSmtp}
            className="flex items-center gap-1.5 rounded-xl bg-slate-800 border border-slate-700 px-3.5 py-2 text-xs font-semibold text-slate-300 hover:bg-slate-700 transition-all"
          >
            <Plus className="h-3.5 w-3.5" />
            <span>Custom SMTP / IMAP</span>
          </button>
        </div>
      </div>

      {/* Alert Notice */}
      {alert && (
        <div
          className={`rounded-xl p-4 text-xs sm:text-sm flex items-center justify-between shadow-lg ${
            alert.type === 'success'
              ? 'bg-emerald-950/40 border border-emerald-500/30 text-emerald-300'
              : 'bg-rose-950/40 border border-rose-500/30 text-rose-300'
          }`}
        >
          <span>{alert.text}</span>
          <button type="button" onClick={() => setAlert(null)} className="underline text-xs">
            Dismiss
          </button>
        </div>
      )}

      {/* Mailbox Cards Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-20 text-slate-400">
          <RefreshCw className="h-6 w-6 animate-spin text-blue-400 mr-2" />
          <span>Loading connected email accounts...</span>
        </div>
      ) : accounts.length === 0 ? (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/50 p-12 text-center space-y-4">
          <Mail className="h-10 w-10 text-slate-600 mx-auto" />
          <h2 className="text-base font-bold text-white">No Mailboxes Connected Yet</h2>
          <p className="text-xs text-slate-400 max-w-md mx-auto">
            Connect your Gmail or Professional SMTP/IMAP accounts above, or click "Seed 6 Mailboxes" to instantly explore the multi-account architecture.
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {accounts.map((acc) => {
            const isGmail = acc.provider_type === 'GMAIL';
            const isConnected = acc.connection_status === 'CONNECTED';
            const isError = acc.connection_status === 'ERROR';
            const isDisconnected = acc.connection_status === 'DISCONNECTED';
            const limitPct = Math.min(100, Math.round(((acc.daily_sent_count || 0) / (acc.daily_sending_limit || 50)) * 100));

            return (
              <div
                key={acc.id}
                className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl flex flex-col justify-between space-y-4 hover:border-slate-700/80 transition-all"
              >
                <div>
                  {/* Card Header: Provider & Status */}
                  <div className="flex items-start justify-between gap-2 border-b border-slate-800/80 pb-3">
                    <div className="flex items-center gap-2">
                      <div className={`flex h-8 w-8 items-center justify-center rounded-xl border ${
                        isGmail 
                          ? 'bg-red-500/10 border-red-500/20 text-red-400' 
                          : 'bg-blue-500/10 border-blue-500/20 text-blue-400'
                      }`}>
                        <Mail className="h-4 w-4" />
                      </div>
                      <div>
                        <span className="text-[11px] font-semibold tracking-wider uppercase text-slate-400 block">
                          {isGmail ? 'Gmail / Workspace' : 'SMTP & IMAP'}
                        </span>
                        <h3 className="text-sm font-bold text-white truncate max-w-[190px]" title={acc.email_address}>
                          {acc.email_address}
                        </h3>
                      </div>
                    </div>

                    {/* Status Badge */}
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold border ${
                      isConnected
                        ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                        : isError
                        ? 'bg-rose-500/15 border-rose-500/40 text-rose-300'
                        : 'bg-slate-800 border-slate-700 text-slate-400'
                    }`}>
                      {acc.connection_status}
                    </span>
                  </div>

                  {/* Automation Switch & Quota */}
                  <div className="pt-3 space-y-3">
                    {/* Automation Active / Paused Switch */}
                    <div className="flex items-center justify-between text-xs rounded-xl bg-slate-950/50 p-2.5 border border-slate-800/60">
                      <span className="text-slate-300 font-medium">Follow-Up Automation</span>
                      <button
                        type="button"
                        onClick={() => handleToggleAutomation(acc)}
                        disabled={actionLoading === `toggle-${acc.id}`}
                        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-[10px] font-bold border transition-colors ${
                          acc.auto_followup_enabled
                            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 hover:bg-emerald-500/30'
                            : 'bg-amber-500/15 text-amber-300 border-amber-500/40 hover:bg-amber-500/25'
                        }`}
                      >
                        <Power className="h-3 w-3" />
                        <span>{acc.auto_followup_enabled ? 'Active' : 'Paused'}</span>
                      </button>
                    </div>

                    {/* Daily Sending Limit Bar */}
                    <div className="space-y-1">
                      <div className="flex items-center justify-between text-[11px]">
                        <span className="text-slate-400">Daily Quota Usage:</span>
                        <div className="flex items-center gap-1">
                          <span className="font-mono font-bold text-white">
                            {acc.daily_sent_count} / {acc.daily_sending_limit}
                          </span>
                          <button
                            type="button"
                            onClick={() => {
                              setEditingLimitAccount(acc);
                              setNewLimitVal(acc.daily_sending_limit);
                            }}
                            className="text-slate-500 hover:text-blue-400"
                            title="Edit daily sending limit"
                          >
                            <Settings2 className="h-3 w-3" />
                          </button>
                        </div>
                      </div>
                      <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                        <div 
                          className={`h-full transition-all rounded-full ${
                            limitPct > 90 ? 'bg-rose-500' : limitPct > 60 ? 'bg-amber-500' : 'bg-blue-500'
                          }`}
                          style={{ width: `${limitPct}%` }}
                        />
                      </div>
                    </div>

                    {/* Account Level Metrics */}
                    <div className="grid grid-cols-4 gap-2 pt-1 text-center">
                      <div className="rounded-lg bg-slate-950/60 p-1.5 border border-slate-800/60">
                        <span className="text-[10px] text-slate-500 block">Tracked</span>
                        <span className="text-xs font-bold font-mono text-white">
                          {acc.stats?.total_tracked ?? 0}
                        </span>
                      </div>
                      <div className="rounded-lg bg-slate-950/60 p-1.5 border border-slate-800/60">
                        <span className="text-[10px] text-slate-500 block">Pending</span>
                        <span className="text-xs font-bold font-mono text-indigo-300">
                          {acc.stats?.pending_followups ?? 0}
                        </span>
                      </div>
                      <div className="rounded-lg bg-slate-950/60 p-1.5 border border-slate-800/60">
                        <span className="text-[10px] text-slate-500 block">Sent</span>
                        <span className="text-xs font-bold font-mono text-blue-300">
                          {acc.stats?.followups_sent ?? 0}
                        </span>
                      </div>
                      <div className="rounded-lg bg-slate-950/60 p-1.5 border border-slate-800/60">
                        <span className="text-[10px] text-slate-500 block">Replies</span>
                        <span className="text-xs font-bold font-mono text-emerald-300">
                          {acc.stats?.replies_received ?? 0}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Card Footer: Action Buttons */}
                <div className="pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs">
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleTestConnection(acc.id)}
                      disabled={actionLoading === `test-${acc.id}`}
                      className="flex items-center gap-1 text-[11px] font-semibold text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-50"
                    >
                      <RefreshCw className={`h-3 w-3 ${actionLoading === `test-${acc.id}` ? 'animate-spin' : ''}`} />
                      <span>Test</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => handleCheckDeliverability(acc)}
                      className="flex items-center gap-1 text-[11px] font-semibold text-purple-400 hover:text-purple-300 transition-colors"
                      title="Inspect SPF, DKIM, DMARC, and MX domain health"
                    >
                      <ShieldCheck className="h-3 w-3" />
                      <span>Domain Health</span>
                    </button>
                  </div>

                  <div className="flex items-center gap-2">
                    {isConnected ? (
                      <button
                        type="button"
                        onClick={() => handleDisconnect(acc.id, acc.email_address)}
                        disabled={actionLoading === `disconnect-${acc.id}`}
                        className="text-[11px] font-medium text-slate-400 hover:text-rose-400 transition-colors"
                      >
                        Disconnect
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => handleTestConnection(acc.id)}
                        className="text-[11px] font-medium text-emerald-400 hover:text-emerald-300 transition-colors"
                      >
                        Reconnect
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => handleDelete(acc.id, acc.email_address)}
                      className="text-slate-500 hover:text-rose-400 transition-colors"
                      title="Delete account"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Modal: Connect Professional SMTP / IMAP Account */}
      {isSmtpModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="w-full max-w-lg rounded-2xl border border-slate-800 bg-[#0f172a] p-6 shadow-2xl space-y-4 my-8">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Globe className="h-5 w-5 text-blue-400" />
                <h3 className="text-base font-bold text-white">Connect Professional Domain Email</h3>
              </div>
              <button
                type="button"
                onClick={() => setIsSmtpModalOpen(false)}
                className="text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            {/* Quick Presets Bar */}
            <div className="flex items-center justify-between p-2.5 rounded-xl bg-purple-950/30 border border-purple-800/40 text-xs">
              <span className="text-purple-300 font-semibold flex items-center gap-1.5">
                <Sparkles className="h-3.5 w-3.5 text-purple-400" />
                Quick Provider Presets:
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => setSmtpForm(prev => ({
                    ...prev,
                    smtp_host: 'smtp.hostinger.com',
                    smtp_port: 465,
                    smtp_encryption: 'SSL',
                    imap_host: 'imap.hostinger.com',
                    imap_port: 993,
                    imap_encryption: 'SSL'
                  }))}
                  className="px-2.5 py-1 rounded-lg bg-purple-600/40 text-purple-200 border border-purple-500/50 hover:bg-purple-600/60 transition-colors font-semibold text-[11px]"
                >
                  Hostinger Defaults
                </button>
                <button
                  type="button"
                  onClick={() => setSmtpForm(prev => ({
                    ...prev,
                    smtp_host: '',
                    smtp_port: 465,
                    smtp_encryption: 'SSL',
                    imap_host: '',
                    imap_port: 993,
                    imap_encryption: 'SSL'
                  }))}
                  className="px-2 py-1 rounded-lg bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700 transition-colors text-[11px]"
                >
                  Clear
                </button>
              </div>
            </div>

            <form onSubmit={handleConnectSmtpSubmit} className="space-y-4 text-xs">
              {/* Email Address */}
              <div>
                <label className="text-slate-300 font-semibold block mb-1">
                  Email Address:
                </label>
                <input
                  type="email"
                  required
                  placeholder="e.g. david@acmeenterprises.com"
                  value={smtpForm.email_address}
                  onChange={(e) => setSmtpForm({ ...smtpForm, email_address: e.target.value })}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-white focus:border-blue-500 focus:outline-none"
                />
              </div>

              {/* SMTP Configuration */}
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 space-y-3">
                <span className="text-[11px] font-bold text-blue-300 uppercase tracking-wider block">
                  Outbound SMTP Configuration (Sending)
                </span>
                <div className="grid grid-cols-3 gap-2">
                  <div className="col-span-2">
                    <label className="text-slate-400 block mb-1">SMTP Host:</label>
                    <input
                      type="text"
                      required
                      placeholder="smtp.domain.com"
                      value={smtpForm.smtp_host}
                      onChange={(e) => setSmtpForm({ ...smtpForm, smtp_host: e.target.value })}
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">Port:</label>
                    <input
                      type="number"
                      required
                      value={smtpForm.smtp_port}
                      onChange={(e) => setSmtpForm({ ...smtpForm, smtp_port: parseInt(e.target.value) || 465 })}
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none font-mono"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-slate-400 block mb-1">SMTP Username:</label>
                    <input
                      type="text"
                      required
                      placeholder="david@acmeenterprises.com"
                      value={smtpForm.smtp_username}
                      onChange={(e) => setSmtpForm({ ...smtpForm, smtp_username: e.target.value })}
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">SMTP Password / App Password:</label>
                    <input
                      type="password"
                      required
                      value={smtpForm.smtp_password}
                      onChange={(e) => setSmtpForm({ ...smtpForm, smtp_password: e.target.value })}
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-slate-400 block mb-1">Encryption:</label>
                  <select
                    value={smtpForm.smtp_encryption}
                    onChange={(e) => setSmtpForm({ ...smtpForm, smtp_encryption: e.target.value as any })}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="SSL">SSL / TLS (Port 465)</option>
                    <option value="STARTTLS">STARTTLS (Port 587)</option>
                    <option value="NONE">None</option>
                  </select>
                </div>
              </div>

              {/* IMAP Configuration */}
              <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 space-y-3">
                <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider block">
                  Inbound IMAP Configuration (Reply Detection)
                </span>
                <div className="grid grid-cols-3 gap-2">
                  <div className="col-span-2">
                    <label className="text-slate-400 block mb-1">IMAP Host:</label>
                    <input
                      type="text"
                      required
                      placeholder="imap.domain.com"
                      value={smtpForm.imap_host}
                      onChange={(e) => setSmtpForm({ ...smtpForm, imap_host: e.target.value })}
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">Port:</label>
                    <input
                      type="number"
                      required
                      value={smtpForm.imap_port}
                      onChange={(e) => setSmtpForm({ ...smtpForm, imap_port: parseInt(e.target.value) || 993 })}
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none font-mono"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-slate-400 block mb-1">IMAP Username:</label>
                    <input
                      type="text"
                      required
                      placeholder="david@acmeenterprises.com"
                      value={smtpForm.imap_username}
                      onChange={(e) => setSmtpForm({ ...smtpForm, imap_username: e.target.value })}
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">IMAP Password / App Password:</label>
                    <input
                      type="password"
                      required
                      value={smtpForm.imap_password}
                      onChange={(e) => setSmtpForm({ ...smtpForm, imap_password: e.target.value })}
                      className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none"
                    />
                  </div>
                </div>

                <div>
                  <label className="text-slate-400 block mb-1">Encryption:</label>
                  <select
                    value={smtpForm.imap_encryption}
                    onChange={(e) => setSmtpForm({ ...smtpForm, imap_encryption: e.target.value as any })}
                    className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white focus:border-blue-500 focus:outline-none"
                  >
                    <option value="SSL">SSL / TLS (Port 993)</option>
                    <option value="STARTTLS">STARTTLS (Port 143)</option>
                    <option value="NONE">None</option>
                  </select>
                </div>
              </div>

              {/* Daily Sending Limit */}
              <div>
                <label className="text-slate-300 font-semibold block mb-1">
                  Daily Sending Limit:
                </label>
                <input
                  type="number"
                  min={1}
                  max={2000}
                  value={smtpForm.daily_sending_limit}
                  onChange={(e) => setSmtpForm({ ...smtpForm, daily_sending_limit: parseInt(e.target.value) || 50 })}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-white font-mono focus:border-blue-500 focus:outline-none"
                />
              </div>

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsSmtpModalOpen(false)}
                  className="px-4 py-2 rounded-xl border border-slate-700 text-slate-300 hover:bg-slate-800 transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={actionLoading === 'smtp-connecting'}
                  className="flex items-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-2 font-bold text-white shadow-md shadow-blue-600/25 hover:from-blue-500 hover:to-indigo-500 transition-all disabled:opacity-50"
                >
                  <CheckCircle2 className="h-4 w-4" />
                  <span>{actionLoading === 'smtp-connecting' ? 'Verifying & Saving...' : 'Verify & Connect Mailbox'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Edit Daily Sending Limit */}
      {editingLimitAccount && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
          <div className="w-full max-w-sm rounded-2xl border border-slate-800 bg-[#0f172a] p-5 shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-white">
              Update Daily Sending Limit
            </h3>
            <p className="text-xs text-slate-400">
              Set maximum automated follow-ups sent per day for <span className="text-slate-200 font-semibold">{editingLimitAccount.email_address}</span>
            </p>
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">Daily Limit:</label>
              <input
                type="number"
                min={1}
                max={5000}
                value={newLimitVal}
                onChange={(e) => setNewLimitVal(parseInt(e.target.value) || 1)}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-white font-mono text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setEditingLimitAccount(null)}
                className="px-3 py-1.5 rounded-lg border border-slate-700 text-xs text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleSaveLimit}
                className="px-4 py-1.5 rounded-lg bg-blue-600 text-xs font-semibold text-white hover:bg-blue-500"
              >
                Save Limit
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: Domain Deliverability & DNS Health Checklist (Section 8) */}
      {isDeliverabilityModalOpen && deliverabilityAccount && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="w-full max-w-2xl rounded-2xl border border-slate-800 bg-[#0f172a] p-6 shadow-2xl space-y-5 my-8">
            {/* Header */}
            <div className="flex items-start justify-between border-b border-slate-800 pb-4">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10 border border-purple-500/30 text-purple-400">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <h3 className="text-base font-bold text-white">Domain Deliverability & DNS Health</h3>
                    {deliverabilityData && (
                      <span className={`rounded-full px-2.5 py-0.5 text-[10px] font-bold border ${
                        deliverabilityData.overall_status === 'EXCELLENT'
                          ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-300'
                          : deliverabilityData.overall_status === 'GOOD'
                          ? 'bg-amber-500/15 border-amber-500/40 text-amber-300'
                          : 'bg-rose-500/15 border-rose-500/40 text-rose-300'
                      }`}>
                        {deliverabilityData.overall_status.replace('_', ' ')}
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 font-mono mt-0.5">
                    {deliverabilityAccount.email_address}
                  </p>
                </div>
              </div>

              <button
                type="button"
                onClick={() => {
                  setIsDeliverabilityModalOpen(false);
                  setDeliverabilityData(null);
                }}
                className="text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            {deliverabilityLoading ? (
              <div className="py-16 text-center space-y-3">
                <RefreshCw className="h-8 w-8 animate-spin text-purple-400 mx-auto" />
                <p className="text-xs text-slate-300">
                  Querying DNS resolvers for SPF, DKIM, DMARC, and MX records...
                </p>
              </div>
            ) : deliverabilityData ? (
              <div className="space-y-4 text-xs">
                {/* Score bar */}
                <div className="rounded-xl border border-slate-800 bg-slate-950/80 p-4 space-y-2">
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-slate-300">Domain Deliverability Score</span>
                    <span className="font-mono font-bold text-base text-white">
                      {deliverabilityData.score} / 100
                    </span>
                  </div>
                  <div className="h-2 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all rounded-full ${
                        deliverabilityData.score >= 90
                          ? 'bg-emerald-500'
                          : deliverabilityData.score >= 60
                          ? 'bg-amber-500'
                          : 'bg-rose-500'
                      }`}
                      style={{ width: `${deliverabilityData.score}%` }}
                    />
                  </div>
                  <p className="text-[11px] text-slate-400">
                    High deliverability ensures your cold emails reach the primary inbox rather than Spam or Promotions.
                  </p>
                </div>

                {/* 4 Checks Grid: SPF, DKIM, DMARC, MX */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {/* SPF Check */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white text-[11px]">SPF Record (Sender Policy)</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        deliverabilityData.checks.spf.passed
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-rose-500/20 text-rose-300'
                      }`}>
                        {deliverabilityData.checks.spf.passed ? 'PASSED' : 'MISSING'}
                      </span>
                    </div>
                    <div className="rounded bg-slate-900 p-2 font-mono text-[10px] text-slate-300 break-all">
                      {deliverabilityData.checks.spf.record || 'No SPF record found on domain'}
                    </div>
                    {deliverabilityData.checks.spf.recommended_record && (
                      <div className="flex items-center justify-between gap-2 text-[10px] text-purple-300 pt-1">
                        <span className="truncate">Hostinger SPF: {deliverabilityData.checks.spf.recommended_record}</span>
                        <button
                          type="button"
                          onClick={() => handleCopy(deliverabilityData.checks.spf.recommended_record, 'spf')}
                          className="text-slate-400 hover:text-white flex-shrink-0"
                          title="Copy recommended record"
                        >
                          {copiedKey === 'spf' ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                        </button>
                      </div>
                    )}
                  </div>

                  {/* DKIM Check */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white text-[11px]">DKIM Signature (DomainKeys)</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        deliverabilityData.checks.dkim.passed
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-rose-500/20 text-rose-300'
                      }`}>
                        {deliverabilityData.checks.dkim.passed ? 'PASSED' : 'MISSING'}
                      </span>
                    </div>
                    <div className="rounded bg-slate-900 p-2 font-mono text-[10px] text-slate-300 break-all">
                      Selector: {deliverabilityData.checks.dkim.selector}
                      <br />
                      {deliverabilityData.checks.dkim.record || 'DKIM signature not active in DNS'}
                    </div>
                    <p className="text-[10px] text-slate-400 pt-1">
                      DKIM keys can be generated with 1 click in your Hostinger hPanel Email section.
                    </p>
                  </div>

                  {/* DMARC Check */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white text-[11px]">DMARC Policy</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        deliverabilityData.checks.dmarc.passed
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-rose-500/20 text-rose-300'
                      }`}>
                        {deliverabilityData.checks.dmarc.passed ? `POLICY: ${deliverabilityData.checks.dmarc.policy.toUpperCase()}` : 'MISSING'}
                      </span>
                    </div>
                    <div className="rounded bg-slate-900 p-2 font-mono text-[10px] text-slate-300 break-all">
                      {deliverabilityData.checks.dmarc.record || 'No _dmarc TXT record found'}
                    </div>
                    {deliverabilityData.checks.dmarc.recommended_record && (
                      <div className="flex items-center justify-between gap-2 text-[10px] text-purple-300 pt-1">
                        <span className="truncate">Rec: {deliverabilityData.checks.dmarc.recommended_record}</span>
                        <button
                          type="button"
                          onClick={() => handleCopy(deliverabilityData.checks.dmarc.recommended_record, 'dmarc')}
                          className="text-slate-400 hover:text-white flex-shrink-0"
                          title="Copy recommended record"
                        >
                          {copiedKey === 'dmarc' ? <Check className="h-3 w-3 text-emerald-400" /> : <Copy className="h-3 w-3" />}
                        </button>
                      </div>
                    )}
                  </div>

                  {/* MX Routing */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-white text-[11px]">MX Records (Mail Routing)</span>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                        deliverabilityData.checks.mx.passed
                          ? 'bg-emerald-500/20 text-emerald-300'
                          : 'bg-rose-500/20 text-rose-300'
                      }`}>
                        {deliverabilityData.checks.mx.passed ? 'ACTIVE' : 'NO ROUTING'}
                      </span>
                    </div>
                    <div className="rounded bg-slate-900 p-2 font-mono text-[10px] text-slate-300 space-y-1">
                      {deliverabilityData.checks.mx.records.length > 0 ? (
                        deliverabilityData.checks.mx.records.map((r, i) => (
                          <div key={i} className="truncate">• {r}</div>
                        ))
                      ) : (
                        <div>No MX records configured</div>
                      )}
                    </div>
                  </div>
                </div>

                {/* Recommendations */}
                {deliverabilityData.recommendations.length > 0 && (
                  <div className="rounded-xl border border-purple-900/40 bg-purple-950/20 p-3.5 space-y-2">
                    <span className="text-[11px] font-bold text-purple-300 flex items-center gap-1.5">
                      <Sparkles className="h-3.5 w-3.5" />
                      Actionable Deliverability Recommendations:
                    </span>
                    <ul className="list-disc list-inside space-y-1 text-slate-300 text-[11px]">
                      {deliverabilityData.recommendations.map((rec, i) => (
                        <li key={i}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            ) : null}

            <div className="flex items-center justify-between pt-2 border-t border-slate-800 text-xs">
              <span className="text-slate-500 text-[11px]">
                SmartFollow AI Hostinger & Custom Domain Deliverability Inspector
              </span>
              <button
                type="button"
                onClick={() => {
                  setIsDeliverabilityModalOpen(false);
                  setDeliverabilityData(null);
                }}
                className="px-4 py-2 rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors font-medium"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
