import axios from 'axios';
import { 
  TrackedThread, TrackedThreadListResponse, SentExplorerItem, 
  DashboardStats, ThreadDetail, AutomationSettings, 
  SuppressionItem, ActivityLog, ConnectedAccount, ConnectSmtpImapPayload,
  DeliverabilityCheckResult
} from '../types';

const api = axios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
});

export const apiClient = {
  // Dashboard
  getStats: async (accountId?: string): Promise<DashboardStats> => {
    const params = accountId && accountId !== 'ALL' ? { account_id: accountId } : {};
    const res = await api.get<DashboardStats>('/dashboard/stats', { params });
    return res.data;
  },

  // Multi-Account Management
  getAccounts: async (): Promise<ConnectedAccount[]> => {
    const res = await api.get<ConnectedAccount[]>('/accounts');
    return res.data;
  },

  connectSmtpImap: async (payload: ConnectSmtpImapPayload): Promise<any> => {
    const res = await api.post('/accounts/smtp-imap', payload);
    return res.data;
  },

  testAccount: async (accountId: string): Promise<any> => {
    const res = await api.post(`/accounts/${accountId}/test`);
    return res.data;
  },

  toggleAccountAutomation: async (accountId: string, enabled?: boolean): Promise<any> => {
    const res = await api.post(`/accounts/${accountId}/toggle-automation`, { enabled });
    return res.data;
  },

  updateAccountLimits: async (accountId: string, dailyLimit: number): Promise<any> => {
    const res = await api.put(`/accounts/${accountId}/limits`, { daily_sending_limit: dailyLimit });
    return res.data;
  },

  disconnectAccount: async (accountId: string): Promise<any> => {
    const res = await api.post(`/accounts/${accountId}/disconnect`);
    return res.data;
  },

  deleteAccount: async (accountId: string): Promise<any> => {
    const res = await api.delete(`/accounts/${accountId}`);
    return res.data;
  },

  getAccountDeliverability: async (accountId: string): Promise<DeliverabilityCheckResult> => {
    const res = await api.get<DeliverabilityCheckResult>(`/accounts/${accountId}/deliverability`);
    return res.data;
  },

  // Email Management & Tracked Threads
  getTrackedThreads: async (params: {
    search?: string;
    status?: string;
    account_id?: string;
    sort_by?: string;
    sort_order?: string;
    page?: number;
    page_size?: number;
  }): Promise<TrackedThreadListResponse> => {
    const cleanParams = { ...params };
    if (cleanParams.account_id === 'ALL') {
      delete cleanParams.account_id;
    }
    const res = await api.get<TrackedThreadListResponse>('/email-management/threads', { params: cleanParams });
    return res.data;
  },

  getThreadDetail: async (threadId: string): Promise<ThreadDetail> => {
    const res = await api.get<ThreadDetail>(`/email-management/threads/${threadId}/detail`);
    return res.data;
  },

  getSentExplorer: async (accountId?: string): Promise<SentExplorerItem[]> => {
    const params = accountId && accountId !== 'ALL' ? { account_id: accountId } : {};
    const res = await api.get<SentExplorerItem[]>('/email-management/sent-explorer', { params });
    return res.data;
  },

  trackSentEmail: async (gmailThreadId: string, accountId?: string): Promise<any> => {
    const payload: any = { gmail_thread_id: gmailThreadId };
    if (accountId && accountId !== 'ALL') {
      payload.account_id = accountId;
    }
    const res = await api.post('/email-management/track-sent', payload);
    return res.data;
  },

  pauseThread: async (threadId: string): Promise<any> => {
    const res = await api.post(`/email-management/threads/${threadId}/pause`);
    return res.data;
  },

  resumeThread: async (threadId: string): Promise<any> => {
    const res = await api.post(`/email-management/threads/${threadId}/resume`);
    return res.data;
  },

  stopTrackingThread: async (threadId: string): Promise<any> => {
    const res = await api.post(`/email-management/threads/${threadId}/stop`);
    return res.data;
  },

  sendNowManual: async (threadId: string, payload: { body?: string; subject?: string; force_live_send?: boolean }): Promise<any> => {
    const res = await api.post(`/email-management/threads/${threadId}/send-now`, payload);
    return res.data;
  },

  // Settings
  getSettings: async (): Promise<AutomationSettings> => {
    const res = await api.get<AutomationSettings>('/settings');
    return res.data;
  },

  updateSettings: async (settings: Partial<AutomationSettings>): Promise<any> => {
    const res = await api.put('/settings', settings);
    return res.data;
  },

  getSuppressionList: async (): Promise<SuppressionItem[]> => {
    const res = await api.get<SuppressionItem[]>('/settings/suppression');
    return res.data;
  },

  addSuppression: async (email: string, reason: string): Promise<SuppressionItem> => {
    const res = await api.post<SuppressionItem>('/settings/suppression', {
      email,
      reason,
    });
    return res.data;
  },

  removeSuppression: async (id: string): Promise<any> => {
    const res = await api.delete(`/settings/suppression/${id}`);
    return res.data;
  },

  // Accounts & OAuth (Google)
  getGoogleAuthUrl: async (): Promise<{ auth_url: string; state: string; warning?: string }> => {
    const res = await api.get('/auth/google/url');
    return res.data;
  },

  getConnectedAccounts: async (): Promise<ConnectedAccount[]> => {
    const res = await api.get<ConnectedAccount[]>('/accounts');
    return res.data;
  },

  // Automation
  runAutomationCycle: async (accountId?: string): Promise<any> => {
    const params = accountId && accountId !== 'ALL' ? { account_id: accountId } : {};
    const res = await api.post('/automation/run-cycle', null, { params });
    return res.data;
  },

  syncSentEmails: async (): Promise<any> => {
    const res = await api.post('/automation/sync-sent');
    return res.data;
  },

  seedDemoData: async (): Promise<any> => {
    const res = await api.post('/automation/seed-demo');
    return res.data;
  },

  resetData: async (): Promise<any> => {
    const res = await api.post('/automation/reset-data');
    return res.data;
  },

  syncNow: async (): Promise<any> => {
    const res = await api.post('/automation/sync-now');
    return res.data;
  },

  // Logs
  getLogs: async (limit: number = 50, action?: string): Promise<ActivityLog[]> => {
    const res = await api.get<ActivityLog[]>('/logs', {
      params: { limit, action },
    });
    return res.data;
  },
};
