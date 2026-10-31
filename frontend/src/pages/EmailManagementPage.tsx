import React, { useState, useEffect } from 'react';
import { 
  Search, Filter, ArrowUpDown, ChevronLeft, ChevronRight, 
  Mail, Sparkles, MessageSquare, Pause, Play, Ban, 
  Send, RefreshCw, PlusCircle, CheckCircle2, Clock, Globe 
} from 'lucide-react';
import { TrackedThread, SentExplorerItem } from '../types';
import { apiClient } from '../services/api';
import { StatusBadge } from '../components/StatusBadge';

interface EmailManagementPageProps {
  initialStatusFilter?: string;
  selectedAccountId?: string;
  onOpenThreadModal: (threadId: string) => void;
  onOpenDraftModal: (thread: TrackedThread) => void;
}

export const EmailManagementPage: React.FC<EmailManagementPageProps> = ({
  initialStatusFilter = 'ALL',
  selectedAccountId = 'ALL',
  onOpenThreadModal,
  onOpenDraftModal,
}) => {
  const [activeSubTab, setActiveSubTab] = useState<'tracked' | 'explorer'>('tracked');
  const [threads, setThreads] = useState<TrackedThread[]>([]);
  const [total, setTotal] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [pageSize, setPageSize] = useState<number>(10);
  const [search, setSearch] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<string>(initialStatusFilter);
  const [sortBy, setSortBy] = useState<string>('original_sent_at');
  const [sortOrder, setSortOrder] = useState<string>('desc');
  const [loading, setLoading] = useState<boolean>(true);
  const [alertNotice, setAlertNotice] = useState<string | null>(null);

  // Sent Explorer state
  const [sentEmails, setSentEmails] = useState<SentExplorerItem[]>([]);
  const [loadingSent, setLoadingSent] = useState<boolean>(false);
  const [trackingId, setTrackingId] = useState<string | null>(null);

  const fetchTrackedThreads = async () => {
    try {
      setLoading(true);
      const res = await apiClient.getTrackedThreads({
        search: search.trim() || undefined,
        status: statusFilter === 'ALL' ? undefined : statusFilter,
        account_id: selectedAccountId,
        sort_by: sortBy,
        sort_order: sortOrder,
        page,
        page_size: pageSize,
      });
      setThreads(res.items);
      setTotal(res.total);
    } catch (err: any) {
      setAlertNotice('Failed to fetch tracked conversations: ' + err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSentExplorer = async () => {
    try {
      setLoadingSent(true);
      const data = await apiClient.getSentExplorer(selectedAccountId);
      setSentEmails(data);
    } catch (err: any) {
      setAlertNotice('Notice: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoadingSent(false);
    }
  };

  useEffect(() => {
    if (activeSubTab === 'tracked') {
      fetchTrackedThreads();
    } else {
      fetchSentExplorer();
    }
  }, [activeSubTab, page, pageSize, statusFilter, sortBy, sortOrder, selectedAccountId]);

  const handleTrackSent = async (gmailThreadId: string, accountId?: string) => {
    try {
      setTrackingId(gmailThreadId);
      await apiClient.trackSentEmail(gmailThreadId, accountId);
      setAlertNotice('Email is now monitored for 72-hour reply detection and follow-up!');
      await fetchSentExplorer();
    } catch (err: any) {
      setAlertNotice('Failed to track email: ' + err.message);
    } finally {
      setTrackingId(null);
    }
  };

  const handlePause = async (threadId: string) => {
    try {
      await apiClient.pauseThread(threadId);
      setAlertNotice('Automation paused for this conversation.');
      fetchTrackedThreads();
    } catch (err: any) {
      setAlertNotice('Failed to pause.');
    }
  };

  const handleResume = async (threadId: string) => {
    try {
      await apiClient.resumeThread(threadId);
      setAlertNotice('Automation resumed for this conversation.');
      fetchTrackedThreads();
    } catch (err: any) {
      setAlertNotice('Failed to resume.');
    }
  };

  const handleStop = async (threadId: string) => {
    if (!confirm('Stop tracking this cold email conversation?')) return;
    try {
      await apiClient.stopTrackingThread(threadId);
      setAlertNotice('Tracking stopped.');
      fetchTrackedThreads();
    } catch (err: any) {
      setAlertNotice('Failed to stop tracking.');
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / pageSize));

  const statuses = [
    { label: 'All Outreach', value: 'ALL' },
    { label: 'Pending', value: 'PENDING' },
    { label: 'Due For Follow-Up', value: 'DUE FOR FOLLOW-UP' },
    { label: 'Follow-Up Sent', value: 'FOLLOW-UP SENT' },
    { label: 'Responded', value: 'RESPONDED' },
    { label: 'Bounced', value: 'BOUNCED' },
    { label: 'Unsubscribed', value: 'UNSUBSCRIBED' },
    { label: 'Paused', value: 'PAUSED' },
  ];

  return (
    <div className="space-y-6 max-w-7xl pb-16">
      {/* Header and Sub-Tab Navigation */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold tracking-tight text-white">Outreach Hub</h1>
            {selectedAccountId !== 'ALL' && (
              <span className="rounded-full bg-blue-500/10 border border-blue-500/30 px-2 py-0.5 text-xs text-blue-300 font-semibold">
                Mailbox Filter Active
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Manage tracked cold email conversations across all connected mailboxes with automated in-thread delivery
          </p>
        </div>

        {/* Tab switchers */}
        <div className="flex rounded-xl bg-slate-900 p-1 border border-slate-800 text-xs font-semibold">
          <button
            onClick={() => setActiveSubTab('tracked')}
            className={`rounded-lg px-4 py-1.5 transition-all ${
              activeSubTab === 'tracked'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Tracked Outreach ({total})
          </button>
          <button
            onClick={() => setActiveSubTab('explorer')}
            className={`rounded-lg px-4 py-1.5 transition-all ${
              activeSubTab === 'explorer'
                ? 'bg-blue-600 text-white shadow-sm'
                : 'text-slate-400 hover:text-white'
            }`}
          >
            Sent Mailbox Explorer
          </button>
        </div>
      </div>

      {/* Alert Notice */}
      {alertNotice && (
        <div className="rounded-xl border border-blue-500/30 bg-blue-950/40 p-3 text-xs text-blue-200 flex items-center justify-between">
          <span>{alertNotice}</span>
          <button onClick={() => setAlertNotice(null)} className="text-blue-400 hover:text-white">
            Dismiss
          </button>
        </div>
      )}

      {activeSubTab === 'tracked' ? (
        <>
          {/* Search & Filters */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3">
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
              {statuses.map((st) => (
                <button
                  key={st.value}
                  onClick={() => {
                    setStatusFilter(st.value);
                    setPage(1);
                  }}
                  className={`whitespace-nowrap rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                    statusFilter === st.value
                      ? 'bg-blue-600 text-white shadow-sm'
                      : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-slate-800'
                  }`}
                >
                  {st.label}
                </button>
              ))}
            </div>

            <div className="relative">
              <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search subject, prospect..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && fetchTrackedThreads()}
                className="w-full sm:w-64 rounded-xl border border-slate-800 bg-slate-900/90 pl-8 pr-3 py-1.5 text-xs text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>

          {/* Tracked Threads Table */}
          <div className="rounded-2xl border border-slate-800 bg-slate-900/70 overflow-hidden shadow-xl backdrop-blur-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs text-slate-300">
                <thead className="border-b border-slate-800 bg-slate-950/60 uppercase tracking-wider text-[11px] font-semibold text-slate-400">
                  <tr>
                    <th className="px-4 py-3.5">Prospect & Mailbox</th>
                    <th className="px-4 py-3.5">Subject & Pitch</th>
                    <th className="px-4 py-3.5">Initial Outreach</th>
                    <th className="px-4 py-3.5">Time Remaining</th>
                    <th className="px-4 py-3.5">Follow-Up Status</th>
                    <th className="px-4 py-3.5">Follow-Up Sent</th>
                    <th className="px-4 py-3.5 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {loading ? (
                    <tr>
                      <td colSpan={7} className="text-center py-12 text-slate-400">
                        <RefreshCw className="h-6 w-6 animate-spin mx-auto text-blue-400 mb-2" />
                        <span>Loading tracked conversations...</span>
                      </td>
                    </tr>
                  ) : threads.length === 0 ? (
                    <tr>
                      <td colSpan={7} className="text-center py-12 text-slate-500">
                        No conversations currently match the filter.
                      </td>
                    </tr>
                  ) : (
                    threads.map((t) => (
                      <tr key={t.id} className="hover:bg-slate-800/40 transition-colors">
                        {/* Prospect & Sending Mailbox Badge */}
                        <td className="px-4 py-3.5">
                          <div className="font-semibold text-white">
                            {t.prospect_name || 'Prospect'}
                          </div>
                          <div className="text-[11px] text-slate-400 font-mono">
                            {t.prospect_email}
                          </div>
                          {t.sending_account_email && (
                            <div className="mt-1 flex items-center gap-1 text-[10px] text-slate-400">
                              <span className={`inline-block w-1.5 h-1.5 rounded-full ${
                                t.email_provider === 'GMAIL' ? 'bg-red-400' : 'bg-blue-400'
                              }`} />
                              <span className="truncate max-w-[150px]" title={t.sending_account_email}>
                                {t.sending_account_email}
                              </span>
                            </div>
                          )}
                        </td>

                        {/* Subject */}
                        <td className="px-4 py-3.5">
                          <div className="font-medium text-slate-200 truncate max-w-[220px]" title={t.original_subject || ''}>
                            {t.original_subject || '(No Subject)'}
                          </div>
                          <div className="text-[10px] text-slate-500 font-mono">
                            Thread: {t.gmail_thread_id.substring(0, 16)}...
                          </div>
                        </td>

                        {/* Initial Sent Date */}
                        <td className="px-4 py-3.5 whitespace-nowrap text-slate-300">
                          <div>{new Date(t.original_sent_at).toLocaleDateString()}</div>
                          <div className="text-[11px] text-slate-500">
                            {t.days_elapsed} {t.days_elapsed === 1 ? 'day' : 'days'} ago
                          </div>
                        </td>

                        {/* Time Remaining */}
                        <td className="px-4 py-3.5">
                          <span className={`inline-flex items-center gap-1 font-mono text-xs ${
                            t.time_remaining === 'Eligible Now' ? 'text-purple-300 font-bold' : 'text-slate-400'
                          }`}>
                            <Clock className="h-3 w-3" />
                            {t.time_remaining}
                          </span>
                        </td>

                        {/* Status */}
                        <td className="px-4 py-3.5">
                          <StatusBadge status={t.status} />
                        </td>

                        {/* Follow-Up Sent Date */}
                        <td className="px-4 py-3.5">
                          {t.followup_count > 0 ? (
                            <div className="text-blue-300 font-medium">
                              Sent ({t.followup_count})
                              {t.last_followup_at && (
                                <div className="text-[10px] text-slate-500">
                                  {new Date(t.last_followup_at).toLocaleDateString()}
                                </div>
                              )}
                            </div>
                          ) : (
                            <span className="text-slate-500">None yet</span>
                          )}
                        </td>

                        {/* Actions */}
                        <td className="px-4 py-3.5 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {/* View Conversation */}
                            <button
                              onClick={() => onOpenThreadModal(t.gmail_thread_id)}
                              className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-300 hover:bg-slate-700 hover:text-white"
                              title="View Conversation"
                            >
                              <MessageSquare className="h-3.5 w-3.5" />
                            </button>

                            {/* AI Follow-Up Studio */}
                            <button
                              onClick={() => onOpenDraftModal(t)}
                              className="rounded-lg border border-purple-500/30 bg-purple-950/40 p-1.5 text-purple-300 hover:bg-purple-900/50"
                              title="Generate / Edit Follow-Up"
                            >
                              <Sparkles className="h-3.5 w-3.5" />
                            </button>

                            {/* Pause / Resume */}
                            {t.status === 'PAUSED' ? (
                              <button
                                onClick={() => handleResume(t.id)}
                                className="rounded-lg border border-emerald-900/40 bg-emerald-950/30 p-1.5 text-emerald-400 hover:bg-emerald-900/50"
                                title="Resume Automation"
                              >
                                <Play className="h-3.5 w-3.5" />
                              </button>
                            ) : (
                              <button
                                onClick={() => handlePause(t.id)}
                                className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-400 hover:bg-slate-700 hover:text-amber-300"
                                title="Pause Automation"
                              >
                                <Pause className="h-3.5 w-3.5" />
                              </button>
                            )}

                            {/* Stop Tracking */}
                            <button
                              onClick={() => handleStop(t.id)}
                              className="rounded-lg border border-slate-800 bg-slate-900 p-1.5 text-slate-500 hover:text-rose-400 hover:bg-rose-950/30"
                              title="Stop Monitoring"
                            >
                              <Ban className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="flex items-center justify-between border-t border-slate-800 bg-slate-950/60 px-4 py-3 text-xs text-slate-400">
              <div>
                Showing <span className="font-semibold text-white">{threads.length}</span> of{' '}
                <span className="font-semibold text-white">{total}</span> conversations
              </div>

              <div className="flex items-center gap-2">
                <button
                  disabled={page <= 1}
                  onClick={() => setPage(page - 1)}
                  className="rounded-lg border border-slate-800 bg-slate-900 p-1.5 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <span className="font-mono">
                  Page {page} of {totalPages}
                </span>
                <button
                  disabled={page >= totalPages}
                  onClick={() => setPage(page + 1)}
                  className="rounded-lg border border-slate-800 bg-slate-900 p-1.5 text-slate-300 hover:bg-slate-800 disabled:opacity-40"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          </div>
        </>
      ) : (
        /* Sent Mailbox Explorer (Method A) */
        <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-5 shadow-xl space-y-4">
          <div className="flex items-center justify-between border-b border-slate-800 pb-3">
            <div>
              <h2 className="text-sm font-bold text-white">Sent Mailbox Explorer</h2>
              <p className="text-xs text-slate-400">Select any sent outreach email and click "Track This Email" to monitor for replies</p>
            </div>
            <button
              onClick={fetchSentExplorer}
              disabled={loadingSent}
              className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-300 hover:bg-slate-700"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loadingSent ? 'animate-spin' : ''}`} />
              <span>Refresh Sent</span>
            </button>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs text-slate-300">
              <thead className="border-b border-slate-800 bg-slate-950/60 uppercase tracking-wider text-[11px] font-semibold text-slate-400">
                <tr>
                  <th className="px-4 py-3">Recipient</th>
                  <th className="px-4 py-3">Sending Account</th>
                  <th className="px-4 py-3">Subject & Preview</th>
                  <th className="px-4 py-3">Date Sent</th>
                  <th className="px-4 py-3 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {loadingSent ? (
                  <tr>
                    <td colSpan={5} className="text-center py-12 text-slate-400">
                      <RefreshCw className="h-6 w-6 animate-spin mx-auto text-blue-400 mb-2" />
                      <span>Scanning Sent Mailbox...</span>
                    </td>
                  </tr>
                ) : sentEmails.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="text-center py-12 text-slate-500">
                      No sent outreach emails found in connected accounts.
                    </td>
                  </tr>
                ) : (
                  sentEmails.map((se) => (
                    <tr key={se.gmail_message_id} className="hover:bg-slate-800/40">
                      <td className="px-4 py-3 font-semibold text-white">
                        <div>{se.recipient_name || 'Prospect'}</div>
                        <div className="text-[11px] text-slate-400 font-mono">{se.recipient_email}</div>
                      </td>
                      <td className="px-4 py-3 text-slate-300">
                        <span className="font-mono text-xs">{se.sending_account || se.sending_account_email || 'Default'}</span>
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-slate-200">{se.subject}</div>
                        <div className="text-[11px] text-slate-500 truncate max-w-md">{se.snippet}</div>
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-slate-400">
                        {new Date(se.date).toLocaleString()}
                      </td>
                      <td className="px-4 py-3 text-right">
                        {se.is_already_tracked ? (
                          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 px-2.5 py-1 text-[11px] font-semibold text-emerald-300">
                            <CheckCircle2 className="h-3 w-3" />
                            Already Tracked
                          </span>
                        ) : (
                          <button
                            onClick={() => handleTrackSent(se.gmail_thread_id, se.sending_account_id)}
                            disabled={trackingId === se.gmail_thread_id}
                            className="inline-flex items-center gap-1 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-blue-500 transition-colors disabled:opacity-50"
                          >
                            <PlusCircle className="h-3.5 w-3.5" />
                            <span>{trackingId === se.gmail_thread_id ? 'Tracking...' : 'Track This Email'}</span>
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
