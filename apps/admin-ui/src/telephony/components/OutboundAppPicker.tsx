import type { PartnerApp } from '../../lib/types';
import type { PhoneNumberOutboundApp } from '../types';

type OutboundAppPickerProps = {
    apps: PartnerApp[];
    selectedIds: string[];
    existingAssignments: PhoneNumberOutboundApp[];
    disabled?: boolean;
    onChange: (ids: string[]) => void;
};

type DisplayApp = {
    id: string;
    name: string;
    agent_slug: string;
    enabled: boolean;
    existing: boolean;
};

const OutboundAppPicker = ({
    apps,
    selectedIds,
    existingAssignments,
    disabled = false,
    onChange,
}: OutboundAppPickerProps) => {
    const assigned = new Map(existingAssignments.map((app) => [app.id, app]));
    const displayApps: DisplayApp[] = [
        ...apps
            .filter((app) => app.enabled || assigned.has(app.id))
            .map((app) => ({ ...app, existing: assigned.has(app.id) })),
        ...existingAssignments
            .filter((app) => !apps.some((candidate) => candidate.id === app.id))
            .map((app) => ({ ...app, existing: true })),
    ];

    const toggle = (app: DisplayApp, checked: boolean) => {
        if (checked && !app.enabled) return;
        const next = checked
            ? [...selectedIds, app.id]
            : selectedIds.filter((id) => id !== app.id);
        onChange(Array.from(new Set(next)));
    };

    return (
        <fieldset className="mb-4" disabled={disabled}>
            <legend className="mb-1.5 block text-sm font-medium">Outbound Partner Apps</legend>
            <p className="mb-2 text-xs text-muted-foreground">
                Optional. Assignments affect new outbound calls immediately. Disabled assigned apps can be removed, but new assignments must use an enabled app.
            </p>
            {!displayApps.length ? (
                <p className="rounded-md border border-border bg-muted/30 p-3 text-sm text-muted-foreground">
                    No Partner Apps are available for outbound assignment.
                </p>
            ) : (
                <div className="space-y-2 rounded-md border border-border p-3">
                    {displayApps.map((app) => {
                        const checked = selectedIds.includes(app.id);
                        const unavailable = !app.enabled;
                        const inputId = `outbound-app-${app.id}`;
                        return (
                            <label key={app.id} htmlFor={inputId} className="flex items-start gap-3 rounded-md p-1.5 hover:bg-accent/50">
                                <input
                                    id={inputId}
                                    type="checkbox"
                                    checked={checked}
                                    disabled={unavailable && !checked}
                                    onChange={(event) => toggle(app, event.target.checked)}
                                    className="mt-0.5 h-4 w-4 rounded border-input text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                                />
                                <span className="min-w-0 text-sm">
                                    <span className="block font-medium">{app.name}</span>
                                    <span className="block text-xs text-muted-foreground">
                                        <code>{app.agent_slug}</code>
                                        {unavailable && (checked ? ' — currently unavailable; remove to clear' : ' — disabled')}
                                    </span>
                                </span>
                            </label>
                        );
                    })}
                </div>
            )}
        </fieldset>
    );
};

export default OutboundAppPicker;
