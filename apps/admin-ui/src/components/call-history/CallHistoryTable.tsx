import { Eye, History, Loader2 } from 'lucide-react';

import Button from '../ui/Button';
import { DataTable } from '../ui/DataTable';
import { EmptyState } from '../ui/EmptyState';
import { StatusPill } from '../ui/StatusPill';
import type { CallHistoryRecord } from '../../call-history/types';
import {
    formatDateTime,
    formatDuration,
    humanize,
    sourceLabel,
    statusTone,
} from '../../call-history/formatters';

type CallHistoryTableProps = {
    rows: CallHistoryRecord[];
    selectedCallId: string | null;
    loading: boolean;
    onSelect: (callId: string) => void;
};

export const CallHistoryTable = ({ rows, selectedCallId, loading, onSelect }: CallHistoryTableProps) => {
    if (loading && rows.length === 0) {
        return (
            <div className="flex min-h-[180px] items-center justify-center rounded-lg border border-border bg-card">
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Loading call history…
                </div>
            </div>
        );
    }

    return (
        <DataTable
            rows={rows}
            rowKey={(row) => row.call_id}
            empty={
                <EmptyState
                    icon={History}
                    title="No call history"
                    description="Completed and in-progress Gateway calls will appear here."
                />
            }
            columns={[
                {
                    header: 'Agent',
                    cell: (row) => <code className="text-primary">{row.agent_slug || '—'}</code>,
                },
                {
                    header: 'Status',
                    cell: (row) => <StatusPill tone={statusTone(row.status)}>{humanize(row.status)}</StatusPill>,
                },
                {
                    header: 'Direction',
                    cell: (row) => <span className="text-sm">{humanize(row.direction)}</span>,
                },
                {
                    header: 'Started',
                    cell: (row) => <span className="whitespace-nowrap text-xs">{formatDateTime(row.created_at)}</span>,
                },
                {
                    header: 'Duration',
                    cell: (row) => <span className="font-mono text-xs">{formatDuration(row.duration_seconds)}</span>,
                },
                {
                    header: 'Source',
                    cell: (row) => (
                        <StatusPill tone={row.history_complete === false ? 'warning' : 'neutral'}>
                            {sourceLabel(row.source)}
                        </StatusPill>
                    ),
                },
                {
                    header: '',
                    className: 'text-right',
                    cell: (row) => (
                        <Button
                            variant={selectedCallId === row.call_id ? 'secondary' : 'ghost'}
                            size="sm"
                            onClick={() => onSelect(row.call_id)}
                            aria-label={`View call ${row.call_id}`}
                        >
                            <Eye className="h-3.5 w-3.5" />
                            View
                        </Button>
                    ),
                },
            ]}
        />
    );
};

export default CallHistoryTable;
