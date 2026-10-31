import React, { useState } from 'react';
import { 
  Users, Mail, Clock, Send, MessageSquare, 
  AlertTriangle, TrendingUp, Sparkles, RefreshCw, 
  Database, ArrowUpRight, ShieldCheck, ShieldAlert, Calendar,
  Globe, Power
} from 'lucide-react';
import { DashboardStats } from '../types';
import { apiClient } from '../services/api';

interface DashboardPageProps {
  stats: DashboardStats | null;
  selectedAccountId: string;
  onSelectAccount: (accountId: string) => void;
  onRefresh: () => void;
  onNavigateToEmails: (statusFilter?: string) => void;
  onOpenDraftModal: (thread: any) => void;
}

export const DashboardPage: React.FC<DashboardPageProps> = ({
  stats,
  selectedAccountId,
  onSelectAccount,
  onRefresh,
  onNavigateToEmails,
}) => {
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [isSeeding, setIsSeeding] = useState<boolean>(false);
  const [actionAlert, setActionAlert] = useState<string | null>(null);

  const handleSyncSent = async () => {
    try {
      setIsSyncing(true);
      setActionAlert(null);
      const res = await apiClient.syncSentEmails();
      setActionAlert(`Outbound Sync Finished across mailboxes: ${res.identified_cold_emails || 0} cold emails tracked.`);
      onRefresh();
    } catch (err: any) {
      setActionAlert('Sync notice: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsSyncing(false);
    }
  };

  const handleSeedDemo = async () => {
    try {
      setIsSeeding(true);
      setActionAlert(null);
      const res = await apiClient.seedDemoData();
      setActionAlert(res.message || 'Seeded 6 connected mailboxes and outreach data!');
      onRefresh();
    } catch (err: any) {
      setActionAlert('Failed to seed demo data: ' + err.message);
    } finally {
      setIsSeeding(false);
    }
  };

  const cards = [
    {
      title: 'Total Tracked Outreach',
      value: stats ? stats.total_tracked : 0,
      icon: Mail,
      color: 'from-blue-500/20 to-indigo-500/10 text-blue-400 border-blue-500/20',
      description: 'Outbound cold conversations monitored',
      statusKey: 'ALL'
    },
    {
      title: 'Awaiting Follow-Up',
      value: stats ? stats.awaiting_followup : 0,
      icon: Clock,
      color: 'from-amber-500/20 to-orange-500/10 text-amber-400 border-amber-500/20',
      description: 'Pending within 72h window',
      statusKey: 'PENDING'
    },
    {
      title: 'Follow-Ups Due Today',
      value: stats ? stats.followups_due_today : 0,
      icon: Calendar,
      color: 'from-indigo-500/20 to-purple-500/10 text-indigo-400 border-indigo-500/20',
      description: 'Elapsed 72 hours without response',
      statusKey: 'DUE FOR FOLLOW-UP'
    },
    {
      title: 'Follow-Ups Sent',
      value: stats ? stats.followups_sent : 0,
      icon: Send,
      color: 'from-purple-500/20 to-pink-500/10 text-purple-400 border-purple-500/20',
      description: 'In-thread follow-up dispatched',
      statusKey: 'FOLLOW-UP SENT'
    },
    {
      title: 'Prospects Who Replied',
      value: stats ? stats.responded : 0,
      icon: MessageSquare,
      color: 'from-emerald-500/20 to-teal-500/10 text-emerald-400 border-emerald-500/20',
      description: 'Genuine replies received from leads',
      statusKey: 'RESPONDED'
    },
    {
      title: 'Follow-Up Response Rate',
      value: `${stats ? stats.followup_response_rate : 0}%`,
      icon: TrendingUp,
      color: 'from-cyan-500/20 to-blue-500/10 text-cyan-400 border-cyan-500/20',
      description: 'Conversion rate of follow-ups',
      statusKey: 'RESPONDED'
    },
  ];

  return (
    <div className="space-y-6 pb-12">
      {/* Action alert banner */}
      {actionAlert && (
        <div className="rounded-xl border border-blue-500/30 bg-blue-950/40 p-4 text-xs sm:text-sm text-blue-200 flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-blue-400 shrink-0" />
            <span>{actionAlert}</span>
          </div>
          <button
            onClick={() => setActionAlert(null)}
            className="text-xs text-blue-400 hover:text-white underline ml-4"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Hero Banner */}
      <div className="rounded-2xl border border-slate-800 bg-gradient-to-r from-slate-900 via-slate-900 to-slate-950 p-6 shadow-xl">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-6">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
                Multi-Mailbox Cold Outreach Dashboard
              </h1>
              {selectedAccountId !== 'ALL' ? (
                <span className="rounded-full bg-blue-500/20 border border-blue-500/40 px-2.5 py-0.5 text-xs font-semibold text-blue-300">
                  Filtered Mailbox
                </span>
              ) : (
                <span className="rounded-full bg-slate-800 border border-slate-700 px-2.5 py-0.5 text-xs font-semibold text-slate-300">
                  All Mailboxes ({stats?.total_connected_accounts || 6} Total)
                </span>
              )}
              {stats?.test_mode_active ? (
                <span className="rounded-full bg-purple-500/20 border border-purple-500/40 px-2.5 py-0.5 text-xs font-semibold text-purple-300 flex items-center gap-1">
                  <ShieldAlert className="h-3.5 w-3.5 text-purple-400" />
                  Test Mode
                </span>
              ) : (
                <span className="rounded-full bg-emerald-500/20 border border-emerald-500/40 px-2.5 py-0.5 text-xs font-semibold text-emerald-300 flex items-center gap-1">
                  <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
                  Live Auto-Send
                </span>
              )}
            </div>
            <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-2xl leading-relaxed">
              Monitors cold outreach conversations across multiple Gmail and Professional SMTP/IMAP mailboxes. Automatically identifies prospect replies after 72 hours, and sends personalized in-thread follow-ups strictly from the original sending account.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={handleSyncSent}
              disabled={isSyncing}
              className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 transition-colors disabled:opacity-50"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isSyncing ? 'animate-spin' : ''}`} />
              <span>Sync Sent Mailboxes</span>
            </button>

            <button
              onClick={handleSeedDemo}
              disabled={isSeeding}
              className="flex items-center gap-2 rounded-xl border border-indigo-500/30 bg-indigo-950/40 px-3.5 py-2 text-xs font-semibold text-indigo-300 hover:bg-indigo-900/50 transition-colors disabled:opacity-50"
            >
              <Database className="h-3.5 w-3.5" />
              <span>Seed 6 Mailboxes</span>
            </button>
          </div>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {cards.map((card, idx) => {
          const Icon = card.icon;
          return (
            <div
              key={idx}
              onClick={() => onNavigateToEmails(card.statusKey)}
              className="group cursor-pointer rounded-2xl border border-slate-800/80 bg-slate-900/70 p-5 shadow-lg backdrop-blur-sm transition-all hover:border-slate-700 hover:bg-slate-900"
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                  {card.title}
                </span>
                <div className={`flex h-9 w-9 items-center justify-center rounded-xl border bg-gradient-to-br ${card.color}`}>
                  <Icon className="h-4 w-4" />
                </div>
              </div>

              <div className="mt-3 flex items-baseline justify-between">
                <div className="text-2xl sm:text-3xl font-extrabold tracking-tight text-white">
                  {card.value}
                </div>
                <ArrowUpRight className="h-4 w-4 text-slate-600 group-hover:text-blue-400 transition-colors" />
              </div>

              <p className="mt-1 text-xs text-slate-400">
                {card.description}
              </p>
            </div>
          );
        })}
      </div>

      {/* SECTION E: Individual Account Dashboards Table */}
      {stats?.accounts_summary && stats.accounts_summary.length > 0 && (
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl space-y-3">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h2 className="text-sm font-bold text-white">Connected Mailboxes Performance Breakdown</h2>
              <p className="text-xs text-slate-400">Account-level statistics across all connected Gmail and SMTP/IMAP mailboxes</p>
            </div>
            {selectedAccountId !== 'ALL' && (
              <button
                onClick={() => onSelectAccount('ALL')}
                className="text-xs text-blue-400 hover:underline font-semibold"
              >
                Clear Filter (View All)
              </button>
            )}
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-slate-800 text-[11px] uppercase font-semibold text-slate-500 bg-slate-950/50">
                <tr>
                  <th className="px-3 py-2.5">Mailbox</th>
                  <th className="px-3 py-2.5">Provider</th>
                  <th className="px-3 py-2.5">Status</th>
                  <th className="px-3 py-2.5">Daily Quota</th>
                  <th className="px-3 py-2.5 text-center">Tracked</th>
                  <th className="px-3 py-2.5 text-center">Pending</th>
                  <th className="px-3 py-2.5 text-center">Sent</th>
                  <th className="px-3 py-2.5 text-center">Replies</th>
                  <th className="px-3 py-2.5 text-center">Bounced</th>
                  <th className="px-3 py-2.5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {stats.accounts_summary.map((acc) => {
                  const isSelected = selectedAccountId === acc.account_id;
                  return (
                    <tr 
                      key={acc.account_id}
                      className={`hover:bg-slate-900/90 transition-colors ${
                        isSelected ? 'bg-blue-950/20 border-l-2 border-l-blue-500' : ''
                      }`}
                    >
                      <td className="px-3 py-3 font-semibold text-white">
                        <div className="flex items-center gap-1.5">
                          <Mail className="h-3.5 w-3.5 text-slate-400" />
                          <span>{acc.email_address}</span>
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold border ${
                          acc.provider_type === 'GMAIL'
                            ? 'bg-red-500/10 text-red-300 border-red-500/20'
                            : 'bg-blue-500/10 text-blue-300 border-blue-500/20'
                        }`}>
                          {acc.provider_type === 'GMAIL' ? 'Gmail' : 'SMTP/IMAP'}
                        </span>
                      </td>
                      <td className="px-3 py-3">
                        <span className={`rounded-full px-2 py-0.5 text-[10px] font-semibold border ${
                          acc.connection_status === 'CONNECTED'
                            ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                            : 'bg-rose-500/15 text-rose-300 border-rose-500/30'
                        }`}>
                          {acc.connection_status}
                        </span>
                      </td>
                      <td className="px-3 py-3 font-mono text-slate-300">
                        {acc.daily_sent_count} / {acc.daily_sending_limit}
                      </td>
                      <td className="px-3 py-3 text-center font-mono font-bold text-white">
                        {acc.total_tracked}
                      </td>
                      <td className="px-3 py-3 text-center font-mono text-indigo-300">
                        {acc.pending_followups}
                      </td>
                      <td className="px-3 py-3 text-center font-mono text-blue-300">
                        {acc.followups_sent}
                      </td>
                      <td className="px-3 py-3 text-center font-mono font-bold text-emerald-300">
                        {acc.replies_received}
                      </td>
                      <td className="px-3 py-3 text-center font-mono text-rose-300">
                        {acc.bounced_emails}
                      </td>
                      <td className="px-3 py-3 text-right">
                        <button
                          onClick={() => onSelectAccount(isSelected ? 'ALL' : acc.account_id)}
                          className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold border transition-colors ${
                            isSelected
                              ? 'bg-blue-600 text-white border-blue-500'
                              : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
                          }`}
                        >
                          {isSelected ? 'Viewing' : 'Filter View'}
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Lower Dashboard */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Pipeline Distribution */}
        <div className="lg:col-span-1 rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-xl">
          <h2 className="text-sm font-bold text-white mb-1">Cold Outreach Funnel</h2>
          <p className="text-xs text-slate-400 mb-4">Real-time status of monitored conversations</p>

          <div className="space-y-3">
            {[
              { label: 'Pending (Under 72h)', count: stats?.status_counts?.['PENDING'] || 0, color: 'bg-amber-500' },
              { label: 'Due For Follow-Up', count: stats?.status_counts?.['DUE FOR FOLLOW-UP'] || 0, color: 'bg-indigo-500' },
              { label: 'Follow-Up Sent', count: stats?.status_counts?.['FOLLOW-UP SENT'] || 0, color: 'bg-blue-500' },
              { label: 'Responded (Won)', count: stats?.status_counts?.['RESPONDED'] || 0, color: 'bg-emerald-500' },
              { label: 'Bounced / NDR', count: stats?.status_counts?.['BOUNCED'] || 0, color: 'bg-rose-500' },
              { label: 'Unsubscribed', count: stats?.status_counts?.['UNSUBSCRIBED'] || 0, color: 'bg-orange-500' },
            ].map((st, i) => {
              const total = stats?.total_tracked || 1;
              const pct = Math.round((st.count / total) * 100);
              return (
                <div key={i} className="text-xs">
                  <div className="flex justify-between text-slate-300 font-medium mb-1">
                    <span>{st.label}</span>
                    <span className="font-mono text-slate-400">{st.count} ({pct}%)</span>
                  </div>
                  <div className="h-1.5 w-full bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className={`h-full ${st.color} rounded-full transition-all duration-500`}
                      style={{ width: `${Math.max(pct, st.count > 0 ? 5 : 0)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-5 pt-4 border-t border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <span>Overall Reply Rate:</span>
            <span className="font-bold text-emerald-400 font-mono">
              {stats?.overall_response_rate || 0}%
            </span>
          </div>
        </div>

        {/* Live Activity Stream */}
        <div className="lg:col-span-2 rounded-2xl border border-slate-800 bg-slate-900/80 p-5 shadow-xl">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h2 className="text-sm font-bold text-white">SmartFollow Activity Stream</h2>
              <p className="text-xs text-slate-400">Real-time audit log of replies detected, drafts created, and sent emails</p>
            </div>
            <button
              onClick={onRefresh}
              className="rounded-lg p-1 text-slate-400 hover:text-white hover:bg-slate-800"
            >
              <RefreshCw className="h-4 w-4" />
            </button>
          </div>

          <div className="space-y-3 max-h-[340px] overflow-y-auto pr-1">
            {stats?.recent_activity && stats.recent_activity.length > 0 ? (
              stats.recent_activity.map((act) => (
                <div
                  key={act.id}
                  className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-3 text-xs flex items-start gap-3 hover:border-slate-700 transition-colors"
                >
                  <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
                    <Mail className="h-3 w-3" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-semibold text-slate-200 truncate">
                        {act.event_type.replace(/_/g, ' ')}
                      </span>
                      <span className="text-[11px] text-slate-500 font-mono shrink-0">
                        {new Date(act.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </span>
                    </div>
                    <p className="text-slate-400 mt-0.5 leading-relaxed break-words">
                      {act.message}
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <div className="text-center py-10 text-xs text-slate-500">
                No recent activity recorded yet.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
