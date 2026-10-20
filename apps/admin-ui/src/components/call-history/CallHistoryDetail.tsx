import type { ReactNode } from 'react';

import Button from '../ui/Button';
import ErrorPanel from '../ui/ErrorPanel';
import { LoadingSpinner } from '../ui/LoadingSpinner';
import { Modal } from '../ui/Modal';
import { StatusPill } from '../ui/StatusPill';
import type { CallHistoryRecord, CallHistorySignal } from '../../call-history/types';
import {
    formatDateTime,
    formatDuration,
    humanize,
    sourceLabel,
    statusTone,
} from '../../call-history/formatters';
import SignalTimeline from './SignalTimeline';

type CallHistoryDetailProps = {
    call: CallHistoryRecord | null;
    signals: CallHistorySignal[];
    loading: boolean;
    error: string | null;
    signalsLoading: boolean;
    signalsNextCursor: string | null;
    onRetry: () => void;
    onClose: () => void;
    onLoadMoreSignals: () => void;
};

const DetailField = ({ label, value }: { label: string; value: ReactNode }) => (
    <div className="min-w-0">
        <dt className="text-xs text-muted-foreground">{label}</dt>
        <dd className="mt-0.5 break-words text-sm">{value}</dd>
    </div>
);

const isImportedSummary = (call: CallHistoryRecord) => call.source === 'imported';

export const CallHistoryDetail = ({
    call,
    signals,
    loading,
    error,
    signalsLoading,
    signalsNextCursor,
    onRetry,
    onClose,
    onLoadMoreSignals,
}: CallHistoryDetailProps) => (
    <Modal isOpen onClose={onClose} title="Call details" size="xl">
        <p className="mb-4 text-xs text-muted-foreground">Metadata and recorded Gateway status signals.</p>

        {loading && (
            <div className="flex min-h-[180px] items-center justify-center">
                <LoadingSpinner size="lg" className="text-primary" />
            </div>
        )}
        {!loading && error && (
            <div>
                <ErrorPanel type="error" message={error} className="mb-3" />
                <Button variant="outline" size="sm" onClick={onRetry}>Retry</Button>
            </div>
        )}
        {!loading && !error && call && (
            <>
                {isImportedSummary(call) && (
                    <ErrorPanel
                        type="info"
                        title="Summary only"
                        message="This imported record has no detailed signals."
                        className="mb-4"
                    />
                )}
                {call.history_complete === false && !isImportedSummary(call) && (
                    <ErrorPanel
                        type="warning"
                        title="Incomplete Gateway timeline"
                        message="Some status signals may be missing. Available persisted signals are shown below."
                        className="mb-4"
                    />
                )}
                <dl className="grid gap-4 sm:grid-cols-2">
                    <DetailField label="Call ID" value={<code className="text-xs">{call.call_id}</code>} />
                    <DetailField label="Agent slug" value={<code className="text-primary">{call.agent_slug || '—'}</code>} />
                    <DetailField label="Status" value={<StatusPill tone={statusTone(call.status)}>{humanize(call.status)}</StatusPill>} />
                    <DetailField label="Direction" value={humanize(call.direction)} />
                    <DetailField label="Source" value={sourceLabel(call.source)} />
                    <DetailField label="Answered" value={call.answered ? 'Yes' : 'No'} />
                    <DetailField label="Reason" value={humanize(call.reason)} />
                    <DetailField label="Dial status" value={call.dial_status || '—'} />
                    <DetailField label="Hangup cause" value={call.hangup_cause ?? '—'} />
                    <DetailField label="Sequence" value={call.sequence ?? '—'} />
                    <DetailField label="Started" value={formatDateTime(call.created_at)} />
                    <DetailField label="Answered at" value={formatDateTime(call.answered_at)} />
                    <DetailField label="Ended" value={formatDateTime(call.ended_at)} />
                    <DetailField label="Duration" value={formatDuration(call.duration_seconds)} />
                    <DetailField label="Talk time" value={formatDuration(call.talk_seconds)} />
                    <DetailField label="Updated" value={formatDateTime(call.updated_at)} />
                </dl>
                {!isImportedSummary(call) && (
                    <SignalTimeline
                        signals={signals}
                        loading={signalsLoading}
                        nextCursor={signalsNextCursor}
                        onLoadMore={onLoadMoreSignals}
                    />
                )}
            </>
        )}
    </Modal>
);

export default CallHistoryDetail;
