export type CallHistoryFilters = {
    agentSlug: string;
    status: string;
    direction: string;
    startedAfter: string;
    startedBefore: string;
};

export type CallHistoryRecord = {
    call_id: string;
    partner_app_id?: string | null;
    agent_slug?: string | null;
    direction?: string | null;
    source?: string | null;
    status: string;
    terminal?: boolean;
    answered?: boolean;
    reason?: string | null;
    hangup_cause?: number | null;
    dial_status?: string | null;
    sequence?: number | null;
    created_at?: string | null;
    updated_at?: string | null;
    answered_at?: string | null;
    ended_at?: string | null;
    duration_seconds?: number | null;
    talk_seconds?: number | null;
    history_complete?: boolean;
};

export type CallHistorySignal = {
    type?: string;
    call_id: string;
    status: string;
    terminal?: boolean;
    answered?: boolean;
    reason?: string | null;
    hangup_cause?: number | null;
    dial_status?: string | null;
    sequence: number;
    created_at?: string | null;
    updated_at?: string | null;
    occurred_at?: string | null;
    timestamp?: string | null;
};

export type CallHistoryPage<T> = {
    items: T[];
    next_cursor?: string | null;
    page?: number;
    page_size?: number;
    total?: number;
    total_pages?: number;
};

export type CallHistoryAgents = {
    items: string[];
};

export const EMPTY_CALL_HISTORY_FILTERS: CallHistoryFilters = {
    agentSlug: '',
    status: '',
    direction: '',
    startedAfter: '',
    startedBefore: '',
};

export const CALL_HISTORY_STATUSES = [
    'dialing',
    'ringing',
    'answered',
    'completed',
    'busy',
    'no_answer',
    'rejected',
    'unavailable',
    'failed',
    'cancelled',
] as const;

export const CALL_HISTORY_DIRECTIONS = ['inbound', 'outbound', 'unknown'] as const;
