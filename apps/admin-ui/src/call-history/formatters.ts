import type { CallHistorySignal } from './types';

export const humanize = (value: string | null | undefined): string => {
    if (!value) return '—';
    return value
        .replace(/[_-]+/g, ' ')
        .replace(/\b\w/g, (letter) => letter.toUpperCase());
};

export const formatDateTime = (value: string | null | undefined): string => {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
};

export const formatDuration = (value: number | null | undefined): string => {
    if (value === null || value === undefined || !Number.isFinite(value)) return '—';
    const seconds = Math.max(0, Math.round(value));
    const minutes = Math.floor(seconds / 60);
    return `${minutes}:${String(seconds % 60).padStart(2, '0')}`;
};

export const signalTime = (signal: CallHistorySignal): string | null =>
    signal.occurred_at ?? signal.created_at ?? signal.updated_at ?? signal.timestamp ?? null;

export const statusTone = (status: string): 'success' | 'warning' | 'error' | 'neutral' | 'info' => {
    if (status === 'completed' || status === 'answered') return 'success';
    if (status === 'dialing' || status === 'ringing') return 'info';
    if (status === 'busy' || status === 'no_answer' || status === 'cancelled') return 'warning';
    if (status === 'failed' || status === 'rejected' || status === 'unavailable') return 'error';
    return 'neutral';
};

export const sourceLabel = (source: string | null | undefined): string => {
    if (!source) return 'Gateway';
    const normalized = source.toLowerCase();
    if (normalized.includes('import') || normalized.includes('legacy') || normalized.includes('cdr')) {
        return 'Imported summary';
    }
    return 'Gateway';
};
