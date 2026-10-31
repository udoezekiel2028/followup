import React, { useState, useEffect } from 'react';
import { 
  X, Mail, ArrowUpRight, ArrowDownLeft, Clock, 
  Sparkles, RefreshCw, CheckCircle2, AlertOctagon, Send 
} from 'lucide-react';
import { apiClient } from '../services/api';
import { ThreadDetail, TrackedThread } from '../types';
import { StatusBadge } from './StatusBadge';

interface ThreadModalProps {
  threadId: string;
  onClose: () => void;
  onOpenDraftModal: (thread: any) => void;
  onStatusUpdated: () => void;
}

export const ThreadModal: React.FC<ThreadModalProps> = ({
  threadId,
  onClose,
  onOpenDraftModal,
  onStatusUpdated,
}) => {
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const fetchDetail = async () => {
    try {
      setLoading(true);
      const data = await apiClient.getThreadDetail(threadId);
      setDetail(data);
    } catch (err: any) {
      setActionMessage('Failed to load thread details: ' + (err.message || 'Unknown error'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDetail();
  }, [threadId]);

  if (!detail && loading) {
    return (
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
        <div className="flex items-center gap-3 rounded-2xl bg-slate-900 border border-slate-800 p-6 shadow-xl">
          <RefreshCw className="h-6 w-6 animate-spin text-blue-400" />
          <span className="text-sm font-medium text-slate-300">Loading conversation history...</span>
        </div>
      </div>
    );
  }

  const thread = detail?.thread;
  const prospect = detail?.prospect;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-sm p-3 sm:p-4 overflow-y-auto">
      <div className="relative flex flex-col w-full max-w-4xl max-h-[90vh] rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl overflow-hidden">
        {/* Modal Header */}
        <div className="flex items-start justify-between border-b border-slate-800 p-5 bg-slate-950/50">
          <div className="flex items-start gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-blue-500/10 border border-blue-500/20 text-blue-400">
              <Mail className="h-6 w-6" />
            </div>
            <div>
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-lg font-bold text-white">
                  {prospect?.name || prospect?.email || 'Prospect Conversation'}
                </h2>
                {thread && <StatusBadge status={thread.status} />}
                {prospect?.company && (
                  <span className="rounded bg-slate-800 px-2 py-0.5 text-xs text-slate-300 border border-slate-700">
                    {prospect.company}
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-400 mt-1 font-mono">
                {prospect?.email} • Gmail Thread: {thread?.gmail_thread_id}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800 hover:text-white transition-colors"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Action Alert Banner */}
        {actionMessage && (
          <div className="px-5 py-2.5 bg-blue-500/10 border-b border-blue-500/20 text-xs text-blue-300 flex items-center justify-between">
            <span>{actionMessage}</span>
            <button onClick={() => setActionMessage(null)}>
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* Modal Body - Conversation Timeline */}
        <div className="flex-1 overflow-y-auto p-5 space-y-4">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
            Gmail Conversation Timeline ({detail?.messages.length || 0} messages)
          </div>

          {detail?.messages && detail.messages.length > 0 ? (
            detail.messages.map((msg, index) => {
              const isInbound = msg.message_type.startsWith('INBOUND');
              const isOOO = msg.message_type === 'INBOUND_OOO';

              return (
                <div
                  key={msg.id || index}
                  className={`rounded-xl border p-4 transition-all ${
                    isOOO
                      ? 'border-amber-500/30 bg-amber-950/15 ml-4 sm:ml-8'
                      : isInbound
                      ? 'border-emerald-500/30 bg-emerald-950/15 ml-4 sm:ml-8'
                      : 'border-slate-800 bg-slate-950/40 mr-4 sm:mr-8'
                  }`}
                >
                  <div className="flex items-center justify-between border-b border-slate-800/60 pb-2 mb-3">
                    <div className="flex items-center gap-2">
                      {isOOO ? (
                        <span className="flex items-center gap-1 rounded bg-amber-500/20 text-amber-300 px-2 py-0.5 text-xs font-medium border border-amber-500/30">
                          <Clock className="h-3.5 w-3.5" />
                          Out-Of-Office Auto-Reply
                        </span>
                      ) : isInbound ? (
                        <span className="flex items-center gap-1 rounded bg-emerald-500/20 text-emerald-300 px-2 py-0.5 text-xs font-medium border border-emerald-500/30">
                          <ArrowDownLeft className="h-3.5 w-3.5" />
                          Prospect Reply
                        </span>
                      ) : msg.message_type === 'OUTBOUND_FOLLOWUP' ? (
                        <span className="flex items-center gap-1 rounded bg-blue-500/20 text-blue-300 px-2 py-0.5 text-xs font-medium border border-blue-500/30">
                          <ArrowUpRight className="h-3.5 w-3.5" />
                          In-Thread Follow-Up Sent
                        </span>
                      ) : (
                        <span className="flex items-center gap-1 rounded bg-slate-800 text-slate-300 px-2 py-0.5 text-xs font-medium border border-slate-700">
                          <ArrowUpRight className="h-3.5 w-3.5" />
                          Initial Cold Outreach
                        </span>
                      )}

                      <span className="text-xs text-slate-300 font-medium">
                        {msg.sender}
                      </span>
                    </div>

                    <div className="flex items-center gap-1 text-xs text-slate-400">
                      <Clock className="h-3 w-3" />
                      <span>{new Date(msg.sent_at).toLocaleString()}</span>
                    </div>
                  </div>

                  <div className="text-xs font-semibold text-slate-200 mb-2">
                    Subject: {msg.subject}
                  </div>

                  <div className="text-sm text-slate-300 whitespace-pre-line leading-relaxed font-sans bg-slate-900/60 rounded-lg p-3 border border-slate-800/80">
                    {msg.body || '(No text content)'}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-5">
              <div className="text-xs text-slate-400 font-semibold mb-2">Original Outreach Body:</div>
              <p className="text-sm text-slate-300 whitespace-pre-line leading-relaxed bg-slate-900/80 p-3 rounded-lg border border-slate-800">
                {thread?.original_body || '(No original body content)'}
              </p>
            </div>
          )}

          {/* Generated Follow-Up Draft */}
          {detail?.draft && (
            <div className="rounded-xl border border-purple-500/30 bg-purple-950/20 p-4 mt-4">
              <div className="flex items-center justify-between mb-2">
                <span className="flex items-center gap-1.5 text-xs font-semibold text-purple-300">
                  <Sparkles className="h-3.5 w-3.5 text-purple-400" />
                  Generated AI Follow-Up Draft (Status: {detail.draft.status})
                </span>
              </div>
              <p className="text-xs text-slate-200 whitespace-pre-line bg-slate-900/90 rounded-lg p-3 border border-purple-500/20 leading-relaxed">
                {detail.draft.generated_content}
              </p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-800 p-4 bg-slate-950/60">
          <button
            onClick={fetchDetail}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700 transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh Thread
          </button>

          <div className="flex items-center gap-2">
            {thread && (
              <button
                onClick={() => {
                  onClose();
                  onOpenDraftModal({
                    id: thread.id,
                    prospect_id: prospect?.id,
                    prospect_name: prospect?.name,
                    prospect_email: prospect?.email,
                    prospect_company: prospect?.company,
                    gmail_thread_id: thread.gmail_thread_id,
                    original_subject: thread.original_subject,
                    original_body: thread.original_body,
                    status: thread.status
                  });
                }}
                className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-1.5 text-xs font-semibold text-white hover:from-blue-500 hover:to-indigo-500 shadow-md shadow-blue-600/20 transition-all"
              >
                <Sparkles className="h-3.5 w-3.5" />
                AI Follow-Up Studio
              </button>
            )}
            <button
              onClick={onClose}
              className="rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-1.5 text-xs font-medium text-slate-300 hover:bg-slate-700"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
