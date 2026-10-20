import { Filter, RotateCcw, Search } from 'lucide-react';

import Button from '../ui/Button';
import { FormInput, FormSelect } from '../ui/FormComponents';
import {
    CALL_HISTORY_DIRECTIONS,
    CALL_HISTORY_STATUSES,
    type CallHistoryFilters as CallHistoryFilterValues,
} from '../../call-history/types';
import { humanize } from '../../call-history/formatters';

type CallHistoryFiltersProps = {
    values: CallHistoryFilterValues;
    agents: string[];
    agentsLoading?: boolean;
    agentsError?: string | null;
    onChange: (name: keyof CallHistoryFilterValues, value: string) => void;
    onApply: () => void;
    onReset: () => void;
    disabled?: boolean;
};

export const CallHistoryFilters = ({
    values,
    agents,
    agentsLoading = false,
    agentsError,
    onChange,
    onApply,
    onReset,
    disabled = false,
}: CallHistoryFiltersProps) => (
    <form
        className="rounded-lg border border-border bg-card p-4 shadow-sm"
        onSubmit={(event) => {
            event.preventDefault();
            onApply();
        }}
    >
        <div className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <Filter className="h-4 w-4 text-muted-foreground" />
            Filter call history
        </div>
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
            <FormSelect
                label="Agent slug"
                value={values.agentSlug}
                onChange={(event) => onChange('agentSlug', event.target.value)}
                options={[
                    { value: '', label: agentsLoading ? 'Loading agents…' : 'All agents' },
                    ...agents.map((agent) => ({ value: agent, label: agent })),
                ]}
                disabled={disabled || agentsLoading}
            />
            <FormSelect
                label="Status"
                value={values.status}
                onChange={(event) => onChange('status', event.target.value)}
                options={[
                    { value: '', label: 'All statuses' },
                    ...CALL_HISTORY_STATUSES.map((status) => ({ value: status, label: humanize(status) })),
                ]}
                disabled={disabled}
            />
            <FormSelect
                label="Direction"
                value={values.direction}
                onChange={(event) => onChange('direction', event.target.value)}
                options={[
                    { value: '', label: 'All directions' },
                    ...CALL_HISTORY_DIRECTIONS.map((direction) => ({ value: direction, label: humanize(direction) })),
                ]}
                disabled={disabled}
            />
            <FormInput
                label="Started after"
                type="datetime-local"
                value={values.startedAfter}
                onChange={(event) => onChange('startedAfter', event.target.value)}
                disabled={disabled}
            />
            <FormInput
                label="Started before"
                type="datetime-local"
                value={values.startedBefore}
                onChange={(event) => onChange('startedBefore', event.target.value)}
                disabled={disabled}
            />
        </div>
        {agentsError && <p className="mb-3 text-xs text-muted-foreground">Agent filter unavailable: {agentsError}</p>}
        <div className="flex flex-wrap justify-end gap-2">
            <Button type="button" variant="ghost" size="sm" onClick={onReset} disabled={disabled}>
                <RotateCcw className="h-3.5 w-3.5" />
                Reset
            </Button>
            <Button type="submit" size="sm" disabled={disabled}>
                <Search className="h-3.5 w-3.5" />
                Apply filters
            </Button>
        </div>
    </form>
);

export default CallHistoryFilters;
