import React from 'react';

type Tone = 'success' | 'warning' | 'error' | 'neutral' | 'info';

const TONES: Record<Tone, string> = {
    success: 'bg-green-500/10 text-green-600 dark:text-green-400 border-green-500/30',
    warning: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/30',
    error: 'bg-destructive/10 text-destructive border-destructive/30',
    info: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30',
    neutral: 'bg-muted text-muted-foreground border-border',
};

export const StatusPill = ({ tone = 'neutral', children }: { tone?: Tone; children: React.ReactNode }) => (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONES[tone]}`}>
        {children}
    </span>
);

export default StatusPill;
