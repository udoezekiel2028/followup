import React from 'react';
import { 
  Mail, LayoutDashboard, Send, Settings, 
  History, ShieldAlert, CheckCircle2, AlertCircle, RefreshCw, Users, Globe
} from 'lucide-react';
import { DashboardStats, ConnectedAccount } from '../types';

interface NavbarProps {
  currentTab: 'dashboard' | 'emails' | 'accounts' | 'logs' | 'settings';
  setCurrentTab: (tab: 'dashboard' | 'emails' | 'accounts' | 'logs' | 'settings') => void;
  stats: DashboardStats | null;
  accountsList: ConnectedAccount[];
  selectedAccountId: string;
  onSelectAccount: (accountId: string) => void;
  onRunCycle: () => void;
  isRunningCycle: boolean;
}

export const Navbar: React.FC<NavbarProps> = ({
  currentTab,
  setCurrentTab,
  stats,
  accountsList,
  selectedAccountId,
  onSelectAccount,
  onRunCycle,
  isRunningCycle
}) => {
  const isTestMode = stats ? stats.test_mode_active : true;
  const isAutoSend = stats ? stats.auto_send_active : false;

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-800 bg-slate-950/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-tr from-blue-600 to-indigo-500 shadow-md shadow-blue-500/25">
            <Mail className="h-5 w-5 text-white" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-lg font-bold tracking-tight text-white">SmartFollow</span>
              <span className="rounded bg-blue-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-blue-400 border border-blue-500/20">
                MULTI-MAILBOX AI
              </span>
            </div>
            <p className="text-xs text-slate-400 hidden sm:block">Cold Email Reply Detection & In-Thread Follow-Ups</p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center space-x-1 sm:space-x-2">
          <button
            onClick={() => setCurrentTab('dashboard')}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              currentTab === 'dashboard'
                ? 'bg-slate-800 text-blue-400 shadow-sm'
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
            }`}
          >
            <LayoutDashboard className="h-4 w-4" />
            <span>Dashboard</span>
          </button>

          <button
            onClick={() => setCurrentTab('emails')}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              currentTab === 'emails'
                ? 'bg-slate-800 text-blue-400 shadow-sm'
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
            }`}
          >
            <Send className="h-4 w-4" />
            <span>Outreach</span>
            {stats && stats.total_tracked > 0 && (
              <span className="ml-1 rounded-full bg-slate-700 px-1.5 py-0.2 text-[11px] text-slate-300">
                {stats.total_tracked}
              </span>
            )}
          </button>

          <button
            onClick={() => setCurrentTab('accounts')}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              currentTab === 'accounts'
                ? 'bg-slate-800 text-blue-400 shadow-sm'
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
            }`}
          >
            <Users className="h-4 w-4" />
            <span>Mailboxes</span>
            {accountsList.length > 0 && (
              <span className="ml-1 rounded-full bg-blue-500/20 border border-blue-500/30 px-1.5 py-0.2 text-[11px] text-blue-300 font-bold">
                {accountsList.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setCurrentTab('logs')}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              currentTab === 'logs'
                ? 'bg-slate-800 text-blue-400 shadow-sm'
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
            }`}
          >
            <History className="h-4 w-4" />
            <span className="hidden md:inline">Logs</span>
          </button>

          <button
            onClick={() => setCurrentTab('settings')}
            className={`flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              currentTab === 'settings'
                ? 'bg-slate-800 text-blue-400 shadow-sm'
                : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'
            }`}
          >
            <Settings className="h-4 w-4" />
            <span>Settings</span>
          </button>
        </nav>

        {/* Right Action: Mailbox Selector & Run Cycle */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* Global Mailbox Filter Switcher */}
          <div className="hidden md:flex items-center gap-1.5">
            <Globe className="h-3.5 w-3.5 text-slate-400" />
            <select
              value={selectedAccountId}
              onChange={(e) => onSelectAccount(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-xs text-white focus:border-blue-500 focus:outline-none max-w-[190px] truncate"
              title="Filter views to a specific mailbox or view all"
            >
              <option value="ALL">All Mailboxes ({accountsList.length})</option>
              {accountsList.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.email_address} ({acc.provider_type === 'GMAIL' ? 'Gmail' : 'SMTP'})
                </option>
              ))}
            </select>
          </div>

          {/* Test Mode / Live Badge */}
          <div className="hidden lg:flex items-center">
            {isTestMode ? (
              <span className="flex items-center gap-1 rounded-full border border-purple-500/30 bg-purple-500/10 px-2.5 py-1 text-xs font-medium text-purple-300">
                <ShieldAlert className="h-3.5 w-3.5 text-purple-400" />
                Test Mode
              </span>
            ) : isAutoSend ? (
              <span className="flex items-center gap-1 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                Auto-Send
              </span>
            ) : (
              <span className="flex items-center gap-1 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-xs font-medium text-amber-300">
                <AlertCircle className="h-3.5 w-3.5 text-amber-400" />
                Paused
              </span>
            )}
          </div>

          <button
            onClick={onRunCycle}
            disabled={isRunningCycle}
            className="flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-3.5 py-2 text-xs font-semibold text-white shadow-md shadow-blue-600/25 transition-all hover:from-blue-500 hover:to-indigo-500 disabled:opacity-50"
            title="Scan for replies and execute 72-hour follow-up logic across all mailboxes"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isRunningCycle ? 'animate-spin' : ''}`} />
            <span className="hidden sm:inline">
              {isRunningCycle ? 'Scanning...' : 'Run Cycle'}
            </span>
          </button>
        </div>
      </div>
    </header>
  );
};
