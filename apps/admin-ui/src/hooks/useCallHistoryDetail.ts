import { useCallback, useEffect, useRef, useState } from 'react';

import { getCallHistoryDetail, getCallHistorySignals } from '../call-history/api';
import type { CallHistoryRecord, CallHistorySignal } from '../call-history/types';
import { apiErrorMessage } from '../utils/apiErrors';

const sortSignals = (signals: CallHistorySignal[]): CallHistorySignal[] =>
    [...signals].sort((left, right) => left.sequence - right.sequence);

export const useCallHistoryDetail = () => {
    const [selectedCallId, setSelectedCallId] = useState<string | null>(null);
    const [selectedCall, setSelectedCall] = useState<CallHistoryRecord | null>(null);
    const [signals, setSignals] = useState<CallHistorySignal[]>([]);
    const [detailLoading, setDetailLoading] = useState(false);
    const [detailError, setDetailError] = useState<string | null>(null);
    const [signalsLoading, setSignalsLoading] = useState(false);
    const [signalsNextCursor, setSignalsNextCursor] = useState<string | null>(null);
    const [detailReloadVersion, setDetailReloadVersion] = useState(0);

    const detailRequestRef = useRef(0);
    const signalsRequestRef = useRef(0);
    const detailAbortRef = useRef<AbortController | null>(null);
    const signalsAbortRef = useRef<AbortController | null>(null);

    useEffect(() => {
        detailAbortRef.current?.abort();
        signalsAbortRef.current?.abort();
        ++detailRequestRef.current;
        ++signalsRequestRef.current;
        setSelectedCall(null);
        setSignals([]);
        setSignalsNextCursor(null);
        setDetailError(null);
        setDetailLoading(false);
        setSignalsLoading(false);

        if (!selectedCallId) return;

        const requestId = detailRequestRef.current;
        const controller = new AbortController();
        detailAbortRef.current = controller;
        setDetailLoading(true);

        void getCallHistoryDetail(selectedCallId, controller.signal)
            .then(async (call) => {
                if (controller.signal.aborted || requestId !== detailRequestRef.current) return;
                setSelectedCall(call);
                // Imported CDR summaries have no signal rows by design. A Gateway
                // record can also be incomplete after a durability interruption;
                // still fetch whatever status signals were persisted for it.
                if (call.source === 'imported') return;

                const signalRequestId = ++signalsRequestRef.current;
                const signalsController = new AbortController();
                signalsAbortRef.current = signalsController;
                setSignalsLoading(true);
                const page = await getCallHistorySignals(selectedCallId, undefined, signalsController.signal);
                if (
                    signalsController.signal.aborted ||
                    requestId !== detailRequestRef.current ||
                    signalRequestId !== signalsRequestRef.current
                ) return;
                setSignals(sortSignals(page.items));
                setSignalsNextCursor(page.next_cursor ?? null);
            })
            .catch((err) => {
                if (controller.signal.aborted || requestId !== detailRequestRef.current) return;
                setDetailError(apiErrorMessage(err));
            })
            .finally(() => {
                if (!controller.signal.aborted && requestId === detailRequestRef.current) {
                    setDetailLoading(false);
                    setSignalsLoading(false);
                }
            });

        return () => {
            controller.abort();
            signalsAbortRef.current?.abort();
        };
    }, [detailReloadVersion, selectedCallId]);

    const selectCall = useCallback((callId: string) => setSelectedCallId(callId), []);
    const clearSelection = useCallback(() => setSelectedCallId(null), []);
    const retryDetail = useCallback(() => setDetailReloadVersion((version) => version + 1), []);

    const loadMoreSignals = useCallback(async () => {
        if (!selectedCallId || !signalsNextCursor || signalsLoading) return;
        const detailRequestId = detailRequestRef.current;
        const signalRequestId = ++signalsRequestRef.current;
        signalsAbortRef.current?.abort();
        const controller = new AbortController();
        signalsAbortRef.current = controller;
        setSignalsLoading(true);
        try {
            const page = await getCallHistorySignals(selectedCallId, signalsNextCursor, controller.signal);
            if (
                controller.signal.aborted ||
                detailRequestId !== detailRequestRef.current ||
                signalRequestId !== signalsRequestRef.current
            ) return;
            setSignals((previous) => sortSignals([...previous, ...page.items]));
            setSignalsNextCursor(page.next_cursor ?? null);
        } catch (err) {
            if (!controller.signal.aborted && detailRequestId === detailRequestRef.current) {
                setDetailError(apiErrorMessage(err));
            }
        } finally {
            if (!controller.signal.aborted && detailRequestId === detailRequestRef.current) {
                setSignalsLoading(false);
            }
        }
    }, [selectedCallId, signalsLoading, signalsNextCursor]);

    return {
        selectedCallId,
        selectedCall,
        selectCall,
        clearSelection,
        retryDetail,
        signals,
        detailLoading,
        detailError,
        signalsLoading,
        signalsNextCursor,
        loadMoreSignals,
    };
};
