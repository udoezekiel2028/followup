import React, { useState, useEffect } from 'react';
import { History, RefreshCw, Filter, Code, Terminal, Clock, ShieldCheck, Mail } from 'lucide-react';
import { apiClient } from '../services/api';
import { ActivityLog } from '../types';

export const LogsPage: React.FC = () => {
  const [logs, setLogs] = useState<ActivityLog[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [filterType, setFilterType] = useState<string>('ALL');
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);

  const fetchLogs = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getLogs(100, filterType === 'ALL' ? undefined : filterType);
      setLogs(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchLogs();
  }, [filterType]);

  const eventTypes = [
    'ALL',
    'SYNC_COMPLETED',
    'REPLY_DETECTED',
    'FOLLOW_UP_DRAFT_CREATED',
    'FOLLOW_UP_SENT',
    'EMAIL_BOUNCED',
    'PROSPECT_UNSUBSCRIBED',
    'SETTINGS_UPDATED',
    'ACCOUNT_CONNECTED',
  ];

  return (
    <div className="space-y-5 max-w-5xl">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-white">System Audit Logs</h1>
          <p className="text-xs text-slate-400 mt-0.5">
            Immutable log of all email evaluations, reply detections, and follow-up dispatches
          </p>
        </div>

        <button
          onClick={fetchLogs}
          disabled={loading}
          className="flex items-center gap-1.5 rounded-xl border border-slate-700 bg-slate-800 px-3.5 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700 disabled:opacity-50"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh Logs</span>
        </button>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
        {eventTypes.map((et) => (
          <button
            key={et}
            onClick={() => setFilterType(et)}
            className={`whitespace-nowrap rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${
              filterType === et
                ? 'bg-blue-600 text-white'
                : 'bg-slate-900 text-slate-400 hover:bg-slate-800 hover:text-slate-200 border border-slate-800'
            }`}
          >
            {et.replace(/_/g, ' ')}
          </button>
        ))}
      </div>

      {/* Log Entries Container */}
      <div className="rounded-2xl border border-slate-800 bg-slate-900/70 p-4 shadow-xl backdrop-blur-sm space-y-2.5">
        {loading ? (
          <div className="py-12 text-center text-xs text-slate-400">
            <RefreshCw className="h-5 w-5 animate-spin mx-auto text-blue-400 mb-2" />
            Loading audit history...
          </div>
        ) : logs.length === 0 ? (
          <div className="py-12 text-center text-xs text-slate-500">
            No activity logs match the selected filter.
          </div>
        ) : (
          logs.map((log) => {
            const isExpanded = expandedLogId === log.id;
            return (
              <div
                key={log.id}
                className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-3.5 text-xs transition-colors hover:border-slate-700"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-start gap-2.5">
                    <span className="rounded-md bg-blue-500/10 border border-blue-500/20 px-2 py-0.5 text-[11px] font-mono font-semibold text-blue-300 uppercase shrink-0">
                      {log.event_type.replace(/_/g, ' ')}
                    </span>
                    <span className="text-slate-200 font-medium leading-relaxed">
                      {log.message}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 shrink-0">
                    <span className="text-[11px] text-slate-500 font-mono">
                      {new Date(log.created_at).toLocaleString()}
                    </span>
                    {log.metadata_json && Object.keys(log.metadata_json).length > 0 && (
                      <button
                        onClick={() => setExpandedLogId(isExpanded ? null : log.id)}
                        className="rounded p-1 text-slate-500 hover:text-slate-300 hover:bg-slate-800"
                        title="Inspect JSON Metadata"
                      >
                        <Code className="h-3.5 w-3.5" />
                      </button>
                    )}
                  </div>
                </div>

                {/* Expanded JSON Inspector */}
                {isExpanded && log.metadata_json && (
                  <div className="mt-3 rounded-lg border border-slate-800 bg-slate-950 p-3 font-mono text-[11px] text-emerald-400 overflow-x-auto">
                    <pre>{JSON.stringify(log.metadata_json, null, 2)}</pre>
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
