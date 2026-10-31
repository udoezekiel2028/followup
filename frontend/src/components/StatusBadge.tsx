import React from 'react';
import { ProspectStatus } from '../types';

interface StatusBadgeProps {
  status: ProspectStatus | string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md' }) => {
  const getBadgeStyle = (st: string) => {
    switch (st) {
      case 'PENDING':
        return 'bg-amber-500/15 text-amber-300 border-amber-500/30';
      case 'DUE FOR FOLLOW-UP':
        return 'bg-indigo-500/15 text-indigo-300 border-indigo-500/30 animate-pulse';
      case 'FOLLOW-UP SENT':
        return 'bg-blue-500/15 text-blue-300 border-blue-500/30';
      case 'RESPONDED':
        return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30 font-semibold';
      case 'BOUNCED':
        return 'bg-rose-500/15 text-rose-300 border-rose-500/30';
      case 'UNSUBSCRIBED':
        return 'bg-orange-500/15 text-orange-300 border-orange-500/30';
      case 'FAILED':
        return 'bg-red-600/15 text-red-300 border-red-500/30';
      case 'EXCLUDED':
        return 'bg-slate-500/15 text-slate-300 border-slate-500/30';
      default:
        return 'bg-slate-700/30 text-slate-300 border-slate-600/30';
    }
  };

  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-medium tracking-wide ${sizeClass} ${getBadgeStyle(
        status
      )}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />
      {status}
    </span>
  );
};
