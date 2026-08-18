import { FormEvent, useEffect, useState } from 'react';
import { KeyRound, Trash2 } from 'lucide-react';

import { useConfirmDialog } from '../hooks/useConfirmDialog';
import type { ApiKey, PartnerApp } from '../lib/types';
import Button from './ui/Button';
import { ConfigCard } from './ui/ConfigCard';
import { StatusPill } from './ui/StatusPill';

interface Props {
    app: PartnerApp;
    keys: ApiKey[];
    onIssueKey: (app: PartnerApp) => Promise<void>;
    onRevokeKey: (keyId: string) => Promise<void>;
    onRotateKey: (keyId: string) => Promise<void>;
    onSavePolicy: (app: PartnerApp, destinations: string[]) => Promise<void>;
    onDelete: (appId: string) => Promise<void>;
}

export const PartnerAppCard = ({ app, keys, onIssueKey, onRevokeKey, onRotateKey, onSavePolicy, onDelete }: Props) => {
    const [destinations, setDestinations] = useState(app.allowed_destinations.join(', '));
    const [saving, setSaving] = useState(false);
    const { confirm } = useConfirmDialog();

    // Polling refreshes the app list; adopt server state unless the operator is
    // mid-edit (the field is only reset when the saved value actually changed).
    useEffect(() => {
        setDestinations(app.allowed_destinations.join(', '));
    }, [app.allowed_destinations]);

    const save = async (event: FormEvent) => {
        event.preventDefault();
        setSaving(true);
        try {
            await onSavePolicy(
                app,
                destinations
                    .split(',')
                    .map((item) => item.trim())
                    .filter(Boolean),
            );
        } finally {
            setSaving(false);
        }
    };

    const revoke = async (key: ApiKey) => {
        const confirmed = await confirm({
            title: 'Revoke API key?',
            description: `Key ${key.prefix} stops working immediately and every new realtime session using it is blocked.`,
            confirmText: 'Revoke key',
            variant: 'destructive',
        });
        if (confirmed) await onRevokeKey(key.id);
    };

    const rotate = async (key: ApiKey) => {
        const confirmed = await confirm({
            title: 'Rotate API key?',
            description: `A replacement key is issued and ${key.prefix} is revoked. Copy the new key immediately — it is shown once.`,
            confirmText: 'Rotate key',
        });
        if (confirmed) await onRotateKey(key.id);
    };

    const remove = async () => {
        const confirmed = await confirm({
            title: 'Delete partner app?',
            description: `${app.name} and all of its API keys are removed. Integrations using agent slug "${app.agent_slug}" will stop working.`,
            confirmText: 'Delete app',
            variant: 'destructive',
        });
        if (confirmed) await onDelete(app.id);
    };

    return (
        <ConfigCard>
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                    <h3 className="text-lg font-semibold tracking-tight truncate">{app.name}</h3>
                    <code className="text-sm text-primary">{app.agent_slug}</code>
                </div>
                <div className="flex items-center gap-2">
                    <StatusPill tone={app.enabled ? 'success' : 'neutral'}>
                        {app.enabled ? 'Enabled' : 'Disabled'}
                    </StatusPill>
                    <button
                        onClick={remove}
                        aria-label={`Delete ${app.name}`}
                        title="Delete partner app"
                        className="p-1.5 rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            </div>

            <div className="mt-3 flex flex-wrap gap-1.5">
                {app.scopes.map((scope) => (
                    <span key={scope} className="rounded bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground">
                        {scope}
                    </span>
                ))}
            </div>

            <form className="mt-4" onSubmit={save}>
                <label htmlFor={`destinations-${app.id}`} className="block text-sm font-medium mb-1.5">
                    Allowed <code className="text-xs">context:extension</code> destinations
                </label>
                <div className="flex gap-2">
                    <input
                        id={`destinations-${app.id}`}
                        className="flex h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-ring"
                        value={destinations}
                        onChange={(event) => setDestinations(event.target.value)}
                        placeholder="from-internal:1001, from-internal:1002"
                    />
                    <Button type="submit" variant="outline" disabled={saving}>
                        {saving ? 'Saving…' : 'Save'}
                    </Button>
                </div>
                <p className="mt-1.5 text-xs text-muted-foreground">
                    Empty means every outbound destination is rejected.
                </p>
            </form>

            <div className="mt-5 flex items-center justify-between">
                <h4 className="text-sm font-semibold">API keys</h4>
                <Button size="sm" onClick={() => onIssueKey(app)}>
                    <KeyRound className="w-3 h-3" />
                    Issue key
                </Button>
            </div>

            <div className="mt-3 space-y-2">
                {keys.length === 0 && <p className="text-xs text-muted-foreground">No keys issued yet.</p>}
                {keys.map((key) => (
                    <div
                        key={key.id}
                        className="flex items-center justify-between gap-3 rounded-md border border-border bg-card/50 p-3 text-sm"
                    >
                        <span className="min-w-0 truncate">
                            <span className="font-medium">{key.name}</span>
                            <code className="ml-2 text-xs text-muted-foreground">{key.prefix}</code>
                        </span>
                        {key.revoked_at ? (
                            <StatusPill tone="neutral">Revoked</StatusPill>
                        ) : (
                            <span className="flex gap-2">
                                <Button size="sm" variant="ghost" onClick={() => rotate(key)}>
                                    Rotate
                                </Button>
                                <Button size="sm" variant="ghost" className="text-destructive" onClick={() => revoke(key)}>
                                    Revoke
                                </Button>
                            </span>
                        )}
                    </div>
                ))}
            </div>
        </ConfigCard>
    );
};

export default PartnerAppCard;
