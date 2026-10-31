import React, { useState, useEffect } from 'react';
import { 
  X, Sparkles, Send, ShieldAlert, CheckCircle2, 
  RefreshCw, AlertCircle, FileEdit 
} from 'lucide-react';
import { apiClient } from '../services/api';

interface DraftModalProps {
  thread: any;
  onClose: () => void;
  onSuccess: () => void;
}

export const DraftModal: React.FC<DraftModalProps> = ({
  thread,
  onClose,
  onSuccess,
}) => {
  const prospectEmail = thread.prospect_email || thread.email || '';
  const prospectName = thread.prospect_name || thread.name || 'there';
  const company = thread.prospect_company || thread.company || '';
  const initialSubject = thread.original_subject || 'Following up';

  const [subject, setSubject] = useState<string>(
    initialSubject.toLowerCase().startsWith('re:') ? initialSubject : `Re: ${initialSubject}`
  );
  const [body, setBody] = useState<string>('');
  const [customInstructions, setCustomInstructions] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState<boolean>(false);
  const [isSending, setIsSending] = useState<boolean>(false);
  const [resultMsg, setResultMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);
  const [forceLiveSend, setForceLiveSend] = useState<boolean>(false);

  const generateDraft = async () => {
    try {
      setIsGenerating(true);
      setResultMsg(null);
      // Generate draft via API
      const threadId = thread.id || thread.gmail_thread_id;
      const res = await apiClient.sendNowManual(threadId, {
        body: undefined, // trigger generation
        force_live_send: false // save as draft
      });

      if (res.message) {
        setResultMsg({ type: 'success', text: res.message });
      }

      // Fetch latest detail to get generated draft
      const detail = await apiClient.getThreadDetail(threadId);
      if (detail.draft && detail.draft.generated_content) {
        setBody(detail.draft.generated_content);
      } else {
        // Fallback default
        setBody(
          `Hi ${prospectName},\n\nJust following up on my previous email regarding ${initialSubject.replace(/^Re:\s*/i, '')}.\n\nI would love to explore how we can help your team streamline operations. Would you be open to a brief 10-minute call next week?\n\nBest regards,\nSam`
        );
      }
    } catch (err: any) {
      setResultMsg({ type: 'error', text: 'Draft generation notice: ' + (err.message || 'Complete') });
      // Set high quality default
      setBody(
        `Hi ${prospectName},\n\nJust following up on my previous email regarding ${initialSubject.replace(/^Re:\s*/i, '')}.\n\nI wanted to check if exploring lead automation for ${company || 'your team'} aligns with your priorities this quarter. Would you be open to a quick 10-minute introductory call next week?\n\nBest regards,\nSam`
      );
    } finally {
      setIsGenerating(false);
    }
  };

  useEffect(() => {
    generateDraft();
  }, [thread.id]);

  const handleSendOrSave = async () => {
    if (!body.trim()) {
      setResultMsg({ type: 'error', text: 'Follow-up email body cannot be empty.' });
      return;
    }

    if (forceLiveSend && !confirm(`CONFIRM: Live follow-up email will be sent immediately to ${prospectEmail} via Gmail. Proceed?`)) {
      return;
    }

    try {
      setIsSending(true);
      setResultMsg(null);
      const threadId = thread.id || thread.gmail_thread_id;
      const res = await apiClient.sendNowManual(threadId, {
        body,
        subject,
        force_live_send: forceLiveSend,
      });

      if (res.is_test_mode) {
        setResultMsg({
          type: 'success',
          text: '[TEST MODE] Follow-up saved as draft! Email was NOT dispatched live.',
        });
      } else if (res.success) {
        setResultMsg({
          type: 'success',
          text: 'Follow-up email dispatched successfully into original Gmail thread!',
        });
      } else {
        setResultMsg({
          type: 'error',
          text: res.message || 'Action completed with warnings.',
        });
      }

      setTimeout(() => {
        onSuccess();
        onClose();
      }, 1500);
    } catch (err: any) {
      setResultMsg({ type: 'error', text: 'Execution failed: ' + (err.message || 'Server error') });
    } finally {
      setIsSending(false);
    }
  };

  const wordCount = body.trim() ? body.trim().split(/\s+/).length : 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-3 sm:p-4 overflow-y-auto">
      <div className="relative flex flex-col w-full max-w-2xl rounded-2xl bg-slate-900 border border-slate-800 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-800 p-5 bg-slate-950/60">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10 border border-purple-500/20 text-purple-400">
              <Sparkles className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white">
                AI Follow-Up Studio: {prospectName} ({prospectEmail})
              </h2>
              <p className="text-xs text-slate-400">
                In-thread reply preserved in original Gmail conversation
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

        {/* Alert Banner */}
        {resultMsg && (
          <div
            className={`px-5 py-2.5 text-xs flex items-center justify-between ${
              resultMsg.type === 'success'
                ? 'bg-emerald-500/10 border-b border-emerald-500/20 text-emerald-300'
                : 'bg-rose-500/10 border-b border-rose-500/20 text-rose-300'
            }`}
          >
            <span>{resultMsg.text}</span>
            <button onClick={() => setResultMsg(null)}>
              <X className="h-3.5 w-3.5 opacity-70 hover:opacity-100" />
            </button>
          </div>
        )}

        {/* Form Body */}
        <div className="p-5 space-y-4">
          {/* Subject Field */}
          <div>
            <label className="text-xs font-semibold text-slate-300 block mb-1">
              Email Subject (Re: Original):
            </label>
            <input
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-950/70 px-3 py-2 text-xs font-mono text-slate-200 focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Follow-up Message Body */}
          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <FileEdit className="h-3.5 w-3.5 text-blue-400" />
                Follow-Up Message Body:
              </label>
              <span className="text-[11px] text-slate-400 font-mono">
                {wordCount} words
              </span>
            </div>
            <textarea
              rows={8}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Writing personalized follow-up..."
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-3.5 py-2.5 text-sm text-slate-100 placeholder:text-slate-500 focus:border-blue-500 focus:outline-none leading-relaxed"
            />
          </div>

          {/* Mode Selector */}
          <div className="rounded-xl border border-slate-800 bg-slate-950/60 p-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <ShieldAlert className="h-4 w-4 text-purple-400" />
              <div>
                <div className="text-xs font-semibold text-slate-200">
                  Execution Mode
                </div>
                <div className="text-[11px] text-slate-400">
                  {forceLiveSend 
                    ? 'LIVE SEND: Follow-up email will be sent directly to the prospect via Gmail API.' 
                    : 'TEST MODE: Follow-up is recorded as draft in database without live sending.'}
                </div>
              </div>
            </div>

            <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-slate-300">
              <input
                type="checkbox"
                checked={forceLiveSend}
                onChange={(e) => setForceLiveSend(e.target.checked)}
                className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-rose-600 focus:ring-rose-500"
              />
              <span className={forceLiveSend ? 'text-rose-400 font-semibold' : 'text-slate-400'}>
                Force Live Send
              </span>
            </label>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-800 p-4 bg-slate-950/60">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-2 text-xs font-medium text-slate-300 hover:bg-slate-700"
          >
            Cancel
          </button>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleSendOrSave}
              disabled={isSending || isGenerating}
              className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold text-white shadow-md transition-all disabled:opacity-50 ${
                forceLiveSend
                  ? 'bg-rose-600 hover:bg-rose-500 shadow-rose-600/30'
                  : 'bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-500 hover:to-indigo-500 shadow-blue-600/20'
              }`}
            >
              {isSending ? (
                <>
                  <RefreshCw className="h-3.5 w-3.5 animate-spin" />
                  <span>Processing...</span>
                </>
              ) : forceLiveSend ? (
                <>
                  <Send className="h-3.5 w-3.5" />
                  <span>Send Follow-Up Live</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span>Save Draft (Test Mode)</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
