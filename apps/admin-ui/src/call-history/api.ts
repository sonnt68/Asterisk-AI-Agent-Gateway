import { api } from '../lib/api';
import type {
    CallHistoryAgents,
    CallHistoryFilters,
    CallHistoryPage,
    CallHistoryRecord,
    CallHistorySignal,
} from './types';

const asApiDate = (value: string): string | undefined => {
    if (!value) return undefined;
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString();
};

const normalizePage = <T,>(page: CallHistoryPage<T>): CallHistoryPage<T> => ({
    items: Array.isArray(page.items) ? page.items : [],
    next_cursor: page.next_cursor ?? null,
    page: page.page,
    page_size: page.page_size,
    total: page.total,
    total_pages: page.total_pages,
});

export const getCallHistory = async (
    filters: CallHistoryFilters,
    page: number,
    signal: AbortSignal,
): Promise<CallHistoryPage<CallHistoryRecord>> => {
    const params: Record<string, string | number> = { limit: 50, page };
    if (filters.agentSlug) params.agent_slug = filters.agentSlug;
    if (filters.status) params.status = filters.status;
    if (filters.direction) params.direction = filters.direction;
    const startedAfter = asApiDate(filters.startedAfter);
    const startedBefore = asApiDate(filters.startedBefore);
    if (startedAfter) params.started_after = startedAfter;
    if (startedBefore) params.started_before = startedBefore;

    const response = await api.get<CallHistoryPage<CallHistoryRecord>>('/call-history', { params, signal });
    return normalizePage(response.data);
};

export const getCallHistoryAgents = async (signal: AbortSignal): Promise<CallHistoryAgents> => {
    const response = await api.get<CallHistoryAgents>('/call-history/agents', { signal });
    return { items: Array.isArray(response.data.items) ? response.data.items : [] };
};

export const getCallHistoryDetail = async (
    callId: string,
    signal: AbortSignal,
): Promise<CallHistoryRecord> => {
    const response = await api.get<CallHistoryRecord>(`/call-history/${encodeURIComponent(callId)}`, { signal });
    return response.data;
};

export const getCallHistorySignals = async (
    callId: string,
    cursor: string | undefined,
    signal: AbortSignal,
): Promise<CallHistoryPage<CallHistorySignal>> => {
    const params: Record<string, string | number> = { limit: 100 };
    if (cursor) params.cursor = cursor;
    const response = await api.get<CallHistoryPage<CallHistorySignal>>(
        `/call-history/${encodeURIComponent(callId)}/signals`,
        { params, signal },
    );
    return normalizePage(response.data);
};
