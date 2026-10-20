import { useCallback, useEffect, useRef, useState } from 'react';

import { getCallHistory, getCallHistoryAgents } from '../call-history/api';
import {
    EMPTY_CALL_HISTORY_FILTERS,
    type CallHistoryFilters,
    type CallHistoryRecord,
} from '../call-history/types';
import { apiErrorMessage } from '../utils/apiErrors';
import { useCallHistoryDetail } from './useCallHistoryDetail';

export const useCallHistory = () => {
    const [filters, setFilters] = useState<CallHistoryFilters>(EMPTY_CALL_HISTORY_FILTERS);
    const [draftFilters, setDraftFilters] = useState<CallHistoryFilters>(EMPTY_CALL_HISTORY_FILTERS);
    const [currentPage, setCurrentPage] = useState(1);
    const [reloadVersion, setReloadVersion] = useState(0);
    const [items, setItems] = useState<CallHistoryRecord[]>([]);
    const [pageSize, setPageSize] = useState(50);
    const [total, setTotal] = useState(0);
    const [totalPages, setTotalPages] = useState(1);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [agents, setAgents] = useState<string[]>([]);
    const [agentsLoading, setAgentsLoading] = useState(true);
    const [agentsError, setAgentsError] = useState<string | null>(null);
    const [agentsReloadVersion, setAgentsReloadVersion] = useState(0);
    const listRequestRef = useRef(0);
    const listAbortRef = useRef<AbortController | null>(null);
    const agentsRequestRef = useRef(0);
    const agentsAbortRef = useRef<AbortController | null>(null);
    const detail = useCallHistoryDetail();
    const { clearSelection } = detail;

    useEffect(() => {
        const requestId = ++listRequestRef.current;
        listAbortRef.current?.abort();
        const controller = new AbortController();
        listAbortRef.current = controller;
        setLoading(true);
        setError(null);

        void getCallHistory(filters, currentPage, controller.signal)
            .then((page) => {
                if (controller.signal.aborted || requestId !== listRequestRef.current) return;
                setItems(page.items);
                setPageSize(page.page_size ?? 50);
                setTotal(page.total ?? page.items.length);
                setTotalPages(Math.max(1, page.total_pages ?? page.page ?? currentPage));
            })
            .catch((err) => {
                if (controller.signal.aborted || requestId !== listRequestRef.current) return;
                setItems([]);
                setTotal(0);
                setTotalPages(1);
                setError(apiErrorMessage(err));
            })
            .finally(() => {
                if (!controller.signal.aborted && requestId === listRequestRef.current) setLoading(false);
            });

        return () => controller.abort();
    }, [currentPage, filters, reloadVersion]);

    useEffect(() => {
        const requestId = ++agentsRequestRef.current;
        agentsAbortRef.current?.abort();
        const controller = new AbortController();
        agentsAbortRef.current = controller;
        setAgentsLoading(true);
        setAgentsError(null);

        void getCallHistoryAgents(controller.signal)
            .then((response) => {
                if (controller.signal.aborted || requestId !== agentsRequestRef.current) return;
                setAgents([...response.items].sort((left, right) => left.localeCompare(right)));
            })
            .catch((err) => {
                if (controller.signal.aborted || requestId !== agentsRequestRef.current) return;
                setAgentsError(apiErrorMessage(err));
            })
            .finally(() => {
                if (!controller.signal.aborted && requestId === agentsRequestRef.current) setAgentsLoading(false);
            });

        return () => controller.abort();
    }, [agentsReloadVersion]);

    const updateDraftFilter = useCallback((name: keyof CallHistoryFilters, value: string) => {
        setDraftFilters((previous) => ({ ...previous, [name]: value }));
    }, []);

    const applyFilters = useCallback(() => {
        setFilters(draftFilters);
        setCurrentPage(1);
        setReloadVersion((version) => version + 1);
        clearSelection();
    }, [clearSelection, draftFilters]);

    const resetFilters = useCallback(() => {
        setDraftFilters(EMPTY_CALL_HISTORY_FILTERS);
        setFilters(EMPTY_CALL_HISTORY_FILTERS);
        setCurrentPage(1);
        setReloadVersion((version) => version + 1);
        clearSelection();
    }, [clearSelection]);

    const refresh = useCallback(() => {
        setReloadVersion((version) => version + 1);
        setAgentsReloadVersion((version) => version + 1);
    }, []);

    const goToPage = useCallback((targetPage: number) => {
        if (!loading && targetPage >= 1 && targetPage <= totalPages && targetPage !== currentPage) {
            setCurrentPage(targetPage);
            clearSelection();
        }
    }, [clearSelection, currentPage, loading, totalPages]);

    const loadNext = useCallback(() => goToPage(currentPage + 1), [currentPage, goToPage]);

    const loadPrevious = useCallback(() => goToPage(currentPage - 1), [currentPage, goToPage]);

    return {
        items,
        filters,
        draftFilters,
        updateDraftFilter,
        applyFilters,
        resetFilters,
        loading,
        error,
        agents,
        agentsLoading,
        agentsError,
        refresh,
        currentPage,
        pageSize,
        total,
        totalPages,
        goToPage,
        hasPrevious: currentPage > 1,
        hasNext: currentPage < totalPages,
        loadNext,
        loadPrevious,
        ...detail,
    };
};
