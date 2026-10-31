import React, { useState, useEffect } from 'react';
import { 
  Save, Mail, ShieldAlert, Sparkles, Clock, Globe, 
  Trash2, Plus, RefreshCw, CheckCircle2, AlertTriangle, ExternalLink, ShieldCheck 
} from 'lucide-react';
import { apiClient } from '../services/api';
import { AutomationSettings, ConnectedAccount, SuppressionItem } from '../types';

interface SettingsPageProps {
  onSettingsSaved: () => void;
}

export const SettingsPage: React.FC<SettingsPageProps> = ({ onSettingsSaved }) => {
  const [settings, setSettings] = useState<AutomationSettings | null>(null);
  const [accounts, setAccounts] = useState<ConnectedAccount[]>([]);
  const [suppressionList, setSuppressionList] = useState<SuppressionItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [saving, setSaving] = useState<boolean>(false);
  const [alert, setAlert] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // New exclusion inputs
  const [newDomain, setNewDomain] = useState<string>('');
  const [newEmail, setNewEmail] = useState<string>('');
  const [newSuppressionVal, setNewSuppressionVal] = useState<string>('');
  const [newSuppressionReason, setNewSuppressionReason] = useState<string>('DO_NOT_CONTACT');

  const loadData = async () => {
    try {
      setLoading(true);
      const [sets, accs, supps] = await Promise.all([
        apiClient.getSettings(),
        apiClient.getConnectedAccounts(),
        apiClient.getSuppressionList(),
      ]);
      setSettings(sets);
      setAccounts(accs);
      setSuppressionList(supps);
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to load settings: ' + err.message });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();

    // Check URL parameters for OAuth status
    const params = new URLSearchParams(window.location.search);
    if (params.get('connected') === 'true') {
      setAlert({
        type: 'success',
        text: `Gmail account ${params.get('email') || ''} connected successfully via OAuth 2.0!`,
      });
      window.history.replaceState({}, '', window.location.pathname);
    } else if (params.get('error')) {
      setAlert({
        type: 'error',
        text: 'OAuth Notice: ' + params.get('error'),
      });
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  const handleSave = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!settings) return;

    try {
      setSaving(true);
      setAlert(null);
      await apiClient.updateSettings(settings);
      setAlert({ type: 'success', text: 'Automation settings saved and applied successfully.' });
      onSettingsSaved();
      await loadData();
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to save settings: ' + err.message });
    } finally {
      setSaving(false);
    }
  };

  const handleConnectGmail = async () => {
    try {
      const data = await apiClient.getGoogleAuthUrl();
      if (data.warning) {
        setAlert({
          type: 'error',
          text: data.warning + ' — Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in backend/.env',
        });
      }
      if (data.auth_url) {
        window.location.href = data.auth_url;
      }
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to initiate Google OAuth: ' + err.message });
    }
  };

  const handleDisconnect = async (accId: string) => {
    if (!confirm('Are you sure you want to disconnect this Gmail account?')) return;
    try {
      await apiClient.disconnectAccount(accId);
      setAlert({ type: 'success', text: 'Account disconnected.' });
      loadData();
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to disconnect account.' });
    }
  };

  const handleAddDomain = () => {
    if (!newDomain.trim() || !settings) return;
    const clean = newDomain.trim().toLowerCase().replace(/^@/, '');
    if (!settings.excluded_domains.includes(clean)) {
      setSettings({
        ...settings,
        excluded_domains: [...settings.excluded_domains, clean],
      });
    }
    setNewDomain('');
  };

  const handleRemoveDomain = (dom: string) => {
    if (!settings) return;
    setSettings({
      ...settings,
      excluded_domains: settings.excluded_domains.filter((d) => d !== dom),
    });
  };

  const handleAddEmail = () => {
    if (!newEmail.trim() || !settings) return;
    const clean = newEmail.trim().toLowerCase();
    if (!settings.excluded_emails.includes(clean)) {
      setSettings({
        ...settings,
        excluded_emails: [...settings.excluded_emails, clean],
      });
    }
    setNewEmail('');
  };

  const handleRemoveEmail = (em: string) => {
    if (!settings) return;
    setSettings({
      ...settings,
      excluded_emails: settings.excluded_emails.filter((e) => e !== em),
    });
  };

  const handleAddSuppression = async () => {
    if (!newSuppressionVal.trim()) return;
    try {
      const item = await apiClient.addSuppression(newSuppressionVal.trim(), newSuppressionReason);
      setSuppressionList([item, ...suppressionList]);
      setNewSuppressionVal('');
      setAlert({ type: 'success', text: 'Suppression entry added successfully.' });
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to add suppression entry: ' + (err.response?.data?.detail || err.message) });
    }
  };

  const handleRemoveSuppression = async (id: string) => {
    try {
      await apiClient.removeSuppression(id);
      setSuppressionList(suppressionList.filter((s) => s.id !== id));
      setAlert({ type: 'success', text: 'Suppression entry removed.' });
    } catch (err: any) {
      setAlert({ type: 'error', text: 'Failed to remove entry.' });
    }
  };

  if (loading || !settings) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-400">
        <RefreshCw className="h-6 w-6 animate-spin text-blue-400 mr-2" />
        <span>Loading automation settings...</span>
      </div>
    );
  }

  // Parse window start and end safely
  const [windowStart, windowEnd] = (settings.sending_window || '09:00-17:00').split('-');

  const handleWindowChange = (part: 'start' | 'end', val: string) => {
    const s = part === 'start' ? val : (windowStart || '09:00');
    const e = part === 'end' ? val : (windowEnd || '17:00');
    setSettings({ ...settings, sending_window: `${s}-${e}` });
  };

  const activeAccounts = accounts.filter((a) => a.status === 'ACTIVE' || a.is_active);

  return (
    <form onSubmit={handleSave} className="space-y-6 max-w-4xl pb-12">
      {/* Page Title & Save Button */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white">System Settings</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Configure Gmail OAuth, 72-hour delay rules, AI follow-up tone, and safety constraints
          </p>
        </div>

        <button
          type="submit"
          disabled={saving}
          className="flex items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 px-5 py-2 text-xs font-semibold text-white shadow-md shadow-blue-600/25 hover:from-blue-500 hover:to-indigo-500 transition-all disabled:opacity-50"
        >
          <Save className="h-4 w-4" />
          <span>{saving ? 'Saving Changes...' : 'Save Settings'}</span>
        </button>
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

      {/* 1. Gmail Account Connection */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl space-y-4">
        <div className="flex items-center gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
            <Mail className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">Gmail / Google Workspace Integration</h2>
            <p className="text-xs text-slate-400">Connect the email account you send cold outreach from</p>
          </div>
        </div>

        {activeAccounts.length > 0 ? (
          activeAccounts.map((acc) => (
            <div key={acc.id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 rounded-xl border border-emerald-500/30 bg-emerald-950/15 p-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-semibold text-white text-sm">{acc.gmail_address || acc.email_address}</span>
                  <span className="rounded-full bg-emerald-500/20 px-2 py-0.5 text-[10px] font-semibold text-emerald-300 border border-emerald-500/40">
                    Connected & Active
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-1">
                  Connected At: {acc.connected_at ? new Date(acc.connected_at).toLocaleString() : 'Recently'}
                </p>
              </div>

              <button
                type="button"
                onClick={() => handleDisconnect(acc.id)}
                className="rounded-lg border border-rose-900/40 bg-rose-950/30 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-900/50 transition-colors"
              >
                Disconnect
              </button>
            </div>
          ))
        ) : (
          <div className="rounded-xl border border-slate-800 bg-slate-950/50 p-5 text-center space-y-3">
            <p className="text-xs text-slate-300 max-w-md mx-auto">
              No active Gmail account connected. Click below to authenticate via Google OAuth 2.0 with read & send scopes.
            </p>
            <button
              type="button"
              onClick={handleConnectGmail}
              className="inline-flex items-center gap-2 rounded-xl bg-white px-4 py-2 text-xs font-bold text-slate-900 shadow-md hover:bg-slate-100 transition-colors"
            >
              <svg className="h-4 w-4" viewBox="0 0 24 24">
                <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.8-2.4 3.65v3h3.88c2.27-2.09 3.66-5.17 3.66-9.09z" />
                <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.27v3.09C3.29 21.43 7.37 24 12 24z" />
                <path fill="#FBBC05" d="M5.28 14.32c-.25-.72-.38-1.49-.38-2.32s.13-1.6.38-2.32V6.59H1.27C.46 8.21 0 10.05 0 12s.46 3.79 1.27 5.41l4.01-3.09z" />
                <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.37 0 3.29 2.57 1.27 6.59l4.01 3.09c.95-2.83 3.6-4.93 6.72-4.93z" />
              </svg>
              <span>Connect Gmail Account (OAuth 2.0)</span>
            </button>
          </div>
        )}
      </div>

      {/* 2. Safety Controls & Automation Switches */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl space-y-4">
        <div className="flex items-center gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
            <ShieldAlert className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">Automation Safety Switches</h2>
            <p className="text-xs text-slate-400">Guardrails against unwanted or duplicate email dispatch</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Test Mode Switch */}
          <div className="rounded-xl border border-purple-500/30 bg-purple-950/20 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-purple-300">Test Mode (Drafts Only)</span>
              <input
                type="checkbox"
                checked={settings.test_mode}
                onChange={(e) => setSettings({ ...settings, test_mode: e.target.checked })}
                className="h-5 w-5 rounded border-purple-500/40 bg-slate-900 text-purple-600 focus:ring-purple-500"
              />
            </div>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              When ON, the AI generates and saves follow-up drafts to the database. Emails are NEVER sent live to prospects until you approve them.
            </p>
          </div>

          {/* Auto Send Switch */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-slate-200">Automatic Live Sending</span>
              <input
                type="checkbox"
                checked={settings.auto_send_enabled}
                onChange={(e) => setSettings({ ...settings, auto_send_enabled: e.target.checked })}
                className="h-5 w-5 rounded border-slate-700 bg-slate-900 text-blue-600 focus:ring-blue-500"
              />
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              When ON (and Test Mode is OFF), follow-ups are automatically dispatched via Gmail at the 72-hour mark without manual confirmation.
            </p>
          </div>
        </div>
      </div>

      {/* 3. Follow-Up Schedule & Timezone */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl space-y-4">
        <div className="flex items-center gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <Clock className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">Follow-Up Schedule & Window</h2>
            <p className="text-xs text-slate-400">Configure waiting interval and business sending hours</p>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {/* Delay in Hours */}
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              Follow-Up Waiting Period (Hours):
            </label>
            <input
              type="number"
              min={1}
              max={720}
              value={settings.followup_delay_hours}
              onChange={(e) => setSettings({ ...settings, followup_delay_hours: parseInt(e.target.value) || 72 })}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs font-mono text-white focus:border-blue-500 focus:outline-none"
            />
            <div className="flex gap-1.5 mt-2">
              {[24, 48, 72, 96].map((h) => (
                <button
                  type="button"
                  key={h}
                  onClick={() => setSettings({ ...settings, followup_delay_hours: h })}
                  className={`rounded-lg px-2 py-0.5 text-[10px] font-medium border ${
                    settings.followup_delay_hours === h
                      ? 'bg-blue-600 text-white border-blue-500'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                >
                  {h}h ({h / 24}d)
                </button>
              ))}
            </div>
          </div>

          {/* Timezone */}
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              Target Business Timezone:
            </label>
            <select
              value={settings.timezone}
              onChange={(e) => setSettings({ ...settings, timezone: e.target.value })}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="America/New_York">Eastern Time (US & Canada)</option>
              <option value="America/Chicago">Central Time (US & Canada)</option>
              <option value="America/Denver">Mountain Time (US & Canada)</option>
              <option value="America/Los_Angeles">Pacific Time (US & Canada)</option>
              <option value="Europe/London">London (GMT / BST)</option>
              <option value="Europe/Paris">Paris, Berlin, Rome (CET)</option>
              <option value="UTC">Universal Time Coordinated (UTC)</option>
              <option value="Asia/Tokyo">Tokyo, Japan (JST)</option>
            </select>
          </div>

          {/* Sending Window Start/End */}
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              Daily Sending Window:
            </label>
            <div className="flex items-center gap-2">
              <input
                type="time"
                value={windowStart || '09:00'}
                onChange={(e) => handleWindowChange('start', e.target.value)}
                className="w-1/2 rounded-xl border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs font-mono text-white focus:border-blue-500 focus:outline-none"
              />
              <span className="text-xs text-slate-500">to</span>
              <input
                type="time"
                value={windowEnd || '17:00'}
                onChange={(e) => handleWindowChange('end', e.target.value)}
                className="w-1/2 rounded-xl border border-slate-700 bg-slate-950 px-2.5 py-1.5 text-xs font-mono text-white focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>
        </div>
      </div>

      {/* 4. AI Copywriting Configuration */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl space-y-4">
        <div className="flex items-center gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
            <Sparkles className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">AI Follow-Up Copywriting Engine</h2>
            <p className="text-xs text-slate-400">Personalize model instructions, tone, and signature</p>
          </div>
        </div>

        <div className="space-y-4">
          <div>
            {/* AI Model */}
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              OpenAI Model:
            </label>
            <select
              value={settings.ai_model}
              onChange={(e) => setSettings({ ...settings, ai_model: e.target.value })}
              className="w-full sm:w-1/2 rounded-xl border border-slate-700 bg-slate-950 px-3 py-2 text-xs text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="gpt-4o-mini">gpt-4o-mini (Fast & High Quality - Recommended)</option>
              <option value="gpt-4o">gpt-4o (Most Intelligent)</option>
              <option value="gpt-3.5-turbo">gpt-3.5-turbo</option>
            </select>
          </div>

          {/* AI Instructions */}
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              Custom AI Instructions & Tone:
            </label>
            <textarea
              rows={3}
              value={settings.ai_instructions}
              onChange={(e) => setSettings({ ...settings, ai_instructions: e.target.value })}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-xs text-white placeholder:text-slate-500 focus:border-blue-500 focus:outline-none leading-relaxed"
            />
          </div>

          {/* Email Signature */}
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              Email Signature:
            </label>
            <textarea
              rows={2}
              value={settings.email_signature}
              onChange={(e) => setSettings({ ...settings, email_signature: e.target.value })}
              className="w-full rounded-xl border border-slate-700 bg-slate-950 p-3 text-xs text-white placeholder:text-slate-500 focus:border-blue-500 focus:outline-none font-mono"
            />
          </div>
        </div>
      </div>

      {/* 5. Exclusions & Global Suppression List */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl space-y-4">
        <div className="flex items-center gap-3 border-b border-slate-800/80 pb-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-400">
            <Globe className="h-4 w-4" />
          </div>
          <div>
            <h2 className="text-sm font-bold text-white">Excluded Domains & Global Suppression List</h2>
            <p className="text-xs text-slate-400">Prevent monitoring or emailing unwanted domains and blacklisted contacts</p>
          </div>
        </div>

        {/* Excluded Domains */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-300 block">
            Excluded Domains (Never monitored):
          </label>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="e.g. competitor.com"
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              className="w-72 rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={handleAddDomain}
              className="flex items-center gap-1 rounded-xl bg-slate-800 px-3 py-1.5 text-xs font-semibold text-slate-200 hover:bg-slate-700"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Domain
            </button>
          </div>

          <div className="flex flex-wrap gap-1.5 pt-1">
            {settings.excluded_domains.map((dom) => (
              <span
                key={dom}
                className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800/80 px-2 py-1 text-xs text-slate-300"
              >
                {dom}
                <button
                  type="button"
                  onClick={() => handleRemoveDomain(dom)}
                  className="text-slate-400 hover:text-rose-400"
                >
                  <Trash2 className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        </div>

        {/* Suppression List Table */}
        <div className="pt-4 border-t border-slate-800 space-y-3">
          <label className="text-xs font-semibold text-slate-300 block">
            Suppression List (Bounced, Unsubscribed & Opt-Outs):
          </label>

          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Email address or domain"
              value={newSuppressionVal}
              onChange={(e) => setNewSuppressionVal(e.target.value)}
              className="w-72 rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
            />
            <select
              value={newSuppressionReason}
              onChange={(e) => setNewSuppressionReason(e.target.value)}
              className="rounded-xl border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-white focus:border-blue-500 focus:outline-none"
            >
              <option value="DO_NOT_CONTACT">DO NOT CONTACT</option>
              <option value="UNSUBSCRIBED">UNSUBSCRIBED</option>
              <option value="BOUNCED">BOUNCED</option>
            </select>
            <button
              type="button"
              onClick={handleAddSuppression}
              className="flex items-center gap-1 rounded-xl bg-rose-600/20 border border-rose-500/30 px-3 py-1.5 text-xs font-semibold text-rose-300 hover:bg-rose-600/30"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Suppression
            </button>
          </div>

          <div className="max-h-48 overflow-y-auto rounded-xl border border-slate-800 bg-slate-950/40">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-800 text-[11px] uppercase font-semibold text-slate-500 bg-slate-950/80">
                <tr>
                  <th className="px-3 py-2">Target</th>
                  <th className="px-3 py-2">Type</th>
                  <th className="px-3 py-2">Reason</th>
                  <th className="px-3 py-2 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {suppressionList.length === 0 ? (
                  <tr>
                    <td colSpan={4} className="text-center py-4 text-slate-500">
                      Suppression list is currently empty.
                    </td>
                  </tr>
                ) : (
                  suppressionList.map((item) => (
                    <tr key={item.id} className="hover:bg-slate-900/60">
                      <td className="px-3 py-2 font-mono text-slate-200">{item.email}</td>
                      <td className="px-3 py-2 text-slate-400">
                        {item.email.includes('@') ? 'EMAIL' : 'DOMAIN'}
                      </td>
                      <td className="px-3 py-2">
                        <span className="rounded bg-rose-500/10 border border-rose-500/20 px-1.5 py-0.5 text-[10px] text-rose-300">
                          {item.reason}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          type="button"
                          onClick={() => handleRemoveSuppression(item.id)}
                          className="text-slate-500 hover:text-rose-400"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </form>
  );
};
