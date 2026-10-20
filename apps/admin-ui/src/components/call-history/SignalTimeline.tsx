import { Circle, Loader2 } from 'lucide-react';

import Button from '../ui/Button';
import { StatusPill } from '../ui/StatusPill';
import type { CallHistorySignal } from '../../call-history/types';
import { formatDateTime, humanize, signalTime, statusTone } from '../../call-history/formatters';

type SignalTimelineProps = {
    signals: CallHistorySignal[];
    loading: boolean;
    nextCursor: string | null;
    onLoadMore: () => void;
};

export const SignalTimeline = ({ signals, loading, nextCursor, onLoadMore }: SignalTimelineProps) => (
    <section className="mt-6">
        <div className="mb-3 flex items-center justify-between gap-3">
            <h3 className="text-sm font-semibold">Signal timeline</h3>
            {loading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        </div>
        {signals.length === 0 && !loading ? (
            <p className="rounded-md border border-dashed border-border p-4 text-xs text-muted-foreground">
                No status signals are currently available for this call.
            </p>
        ) : (
            <ol className="space-y-0">
                {signals.map((signal, index) => (
                    <li key={`${signal.sequence}-${signalTime(signal) ?? index}`} className="relative flex gap-3 pb-5 last:pb-0">
                        {index < signals.length - 1 && (
                            <span className="absolute left-[7px] top-3 h-full w-px bg-border" aria-hidden="true" />
                        )}
                        <Circle className="relative z-10 mt-0.5 h-4 w-4 shrink-0 fill-background text-primary" />
                        <div className="min-w-0 flex-1 rounded-md border border-border/70 bg-muted/20 px-3 py-2">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <StatusPill tone={statusTone(signal.status)}>{humanize(signal.status)}</StatusPill>
                                <span className="text-xs text-muted-foreground">
                                    {formatDateTime(signalTime(signal))}
                                </span>
                            </div>
                            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-muted-foreground">
                                <div>
                                    <dt className="inline">Sequence: </dt>
                                    <dd className="inline font-mono text-foreground">{signal.sequence}</dd>
                                </div>
                                <div>
                                    <dt className="inline">Answered: </dt>
                                    <dd className="inline text-foreground">{signal.answered ? 'Yes' : 'No'}</dd>
                                </div>
                                {signal.reason && (
                                    <div className="col-span-2">
                                        <dt className="inline">Reason: </dt>
                                        <dd className="inline text-foreground">{humanize(signal.reason)}</dd>
                                    </div>
                                )}
                            </dl>
                        </div>
                    </li>
                ))}
            </ol>
        )}
        {nextCursor && (
            <Button variant="outline" size="sm" className="mt-4" onClick={onLoadMore} disabled={loading}>
                Load more signals
            </Button>
        )}
    </section>
);

export default SignalTimeline;
