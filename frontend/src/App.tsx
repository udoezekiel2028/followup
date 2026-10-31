import React, { useState, useEffect } from 'react';
import { Navbar } from './components/Navbar';
import { DashboardPage } from './pages/DashboardPage';
import { EmailManagementPage } from './pages/EmailManagementPage';
import { AccountsPage } from './pages/AccountsPage';
import { SettingsPage } from './pages/SettingsPage';
import { LogsPage } from './pages/LogsPage';
import { ThreadModal } from './components/ThreadModal';
import { DraftModal } from './components/DraftModal';
import { apiClient } from './services/api';
import { DashboardStats, ConnectedAccount, TrackedThread } from './types';

export function App() {
  const [currentTab, setCurrentTab] = useState<'dashboard' | 'emails' | 'accounts' | 'logs' | 'settings'>('dashboard');
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [accountsList, setAccountsList] = useState<ConnectedAccount[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('ALL');
  const [isRunningCycle, setIsRunningCycle] = useState<boolean>(false);
  const [statusFilterForEmails, setStatusFilterForEmails] = useState<string>('ALL');

  // Modals
  const [selectedThreadIdForModal, setSelectedThreadIdForModal] = useState<string | null>(null);
  const [selectedThreadForDraft, setSelectedThreadForDraft] = useState<any | null>(null);

  const fetchGlobalData = async () => {
    try {
      const [statsData, accountsData] = await Promise.all([
        apiClient.getStats(selectedAccountId),
        apiClient.getAccounts(),
      ]);
      setStats(statsData);
      setAccountsList(accountsData);
    } catch (err) {
      console.error('Failed to load initial data:', err);
    }
  };

  useEffect(() => {
    fetchGlobalData();
    const interval = setInterval(fetchGlobalData, 30000);
    return () => clearInterval(interval);
  }, [selectedAccountId]);

  const handleRunCycle = async () => {
    try {
      setIsRunningCycle(true);
      await apiClient.runAutomationCycle(selectedAccountId);
      await fetchGlobalData();
    } catch (err: any) {
      alert('Automation notice: ' + (err.response?.data?.detail || err.message));
    } finally {
      setIsRunningCycle(false);
    }
  };

  const handleNavigateToEmails = (statusKey: string = 'ALL') => {
    setStatusFilterForEmails(statusKey);
    setCurrentTab('emails');
  };

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col font-sans">
      <Navbar
        currentTab={currentTab}
        setCurrentTab={setCurrentTab}
        stats={stats}
        accountsList={accountsList}
        selectedAccountId={selectedAccountId}
        onSelectAccount={(accId) => setSelectedAccountId(accId)}
        onRunCycle={handleRunCycle}
        isRunningCycle={isRunningCycle}
      />

      <main className="flex-1 mx-auto w-full max-w-7xl px-4 sm:px-6 lg:px-8 py-6">
        {currentTab === 'dashboard' && (
          <DashboardPage
            stats={stats}
            selectedAccountId={selectedAccountId}
            onSelectAccount={(accId) => setSelectedAccountId(accId)}
            onRefresh={fetchGlobalData}
            onNavigateToEmails={handleNavigateToEmails}
            onOpenDraftModal={(thread) => setSelectedThreadForDraft(thread)}
          />
        )}

        {currentTab === 'emails' && (
          <EmailManagementPage
            initialStatusFilter={statusFilterForEmails}
            selectedAccountId={selectedAccountId}
            onOpenThreadModal={(id) => setSelectedThreadIdForModal(id)}
            onOpenDraftModal={(thread) => setSelectedThreadForDraft(thread)}
          />
        )}

        {currentTab === 'accounts' && (
          <AccountsPage onAccountListUpdated={fetchGlobalData} />
        )}

        {currentTab === 'logs' && <LogsPage />}

        {currentTab === 'settings' && (
          <SettingsPage onSettingsSaved={fetchGlobalData} />
        )}
      </main>

      {/* Conversation Thread Modal */}
      {selectedThreadIdForModal && (
        <ThreadModal
          threadId={selectedThreadIdForModal}
          onClose={() => setSelectedThreadIdForModal(null)}
          onOpenDraftModal={(thread) => {
            setSelectedThreadIdForModal(null);
            setSelectedThreadForDraft(thread);
          }}
          onStatusUpdated={fetchGlobalData}
        />
      )}

      {/* AI Follow-Up Studio Modal */}
      {selectedThreadForDraft && (
        <DraftModal
          thread={selectedThreadForDraft}
          onClose={() => setSelectedThreadForDraft(null)}
          onSuccess={fetchGlobalData}
        />
      )}
    </div>
  );
}

export default App;
