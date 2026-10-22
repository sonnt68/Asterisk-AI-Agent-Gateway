import { FormEvent, useEffect, useState } from 'react';
import { KeyRound, Pencil, Trash2 } from 'lucide-react';

import { useConfirmDialog } from '../hooks/useConfirmDialog';
import type { ApiKey, ApiKeyReveal, PartnerApp } from '../lib/types';
import { apiErrorMessage } from '../utils/apiErrors';
import Button from './ui/Button';
import { ConfigCard } from './ui/ConfigCard';
import { FormInput } from './ui/FormComponents';
import { StatusPill } from './ui/StatusPill';
import RevealedKeyBanner from './RevealedKeyBanner';

interface Props {
    app: PartnerApp;
    keys: ApiKey[];
    onIssueKey: (app: PartnerApp) => Promise<void>;
    onRevokeKey: (keyId: string) => Promise<void>;
    onRotateKey: (keyId: string) => Promise<void>;
    onRevealKey: (keyId: string, app: Pick<PartnerApp, 'id' | 'agent_slug'>) => Promise<ApiKeyReveal>;
    hasEphemeralSecret: (keyId: string) => boolean;
    onDeleteRevokedKey: (keyId: string) => Promise<void>;
    onSavePolicy: (app: PartnerApp, destinations: string[]) => Promise<void>;
    onSaveName: (app: PartnerApp, name: string) => Promise<void>;
    onDelete: (appId: string) => Promise<void>;
}

export const PartnerAppCard = ({ app, keys, onIssueKey, onRevokeKey, onRotateKey, onRevealKey, hasEphemeralSecret, onDeleteRevokedKey, onSavePolicy, onSaveName, onDelete }: Props) => {
    const [destinations, setDestinations] = useState(app.allowed_destinations.join(', '));
    const [editingName, setEditingName] = useState(false);
    const [nameDraft, setNameDraft] = useState(app.name);
    const [nameError, setNameError] = useState<string | null>(null);
    const [savingName, setSavingName] = useState(false);
    const [saving, setSaving] = useState(false);
    const [busyAction, setBusyAction] = useState<string | null>(null);
    const { confirm } = useConfirmDialog();
    const hasActiveKeys = keys.some((key) => !key.revoked_at);

    // Polling refreshes the app list; adopt server state unless the operator is
    // mid-edit (the field is only reset when the saved value actually changed).
    useEffect(() => {
        setDestinations(app.allowed_destinations.join(', '));
    }, [app.allowed_destinations]);

    useEffect(() => {
        if (!editingName) setNameDraft(app.name);
    }, [app.name, editingName]);

    const startNameEdit = () => {
        if (busyAction) return;
        setNameDraft(app.name);
        setNameError(null);
        setEditingName(true);
    };

    const cancelNameEdit = () => {
        if (savingName) return;
        setNameDraft(app.name);
        setNameError(null);
        setEditingName(false);
    };

    const saveName = async (event: FormEvent) => {
        event.preventDefault();
        if (savingName || busyAction) return;
        const trimmedName = nameDraft.trim();
        if (trimmedName.length < 1) {
            setNameError('Enter a partner app name.');
            return;
        }
        if (trimmedName.length > 120) {
            setNameError('Partner app names must be 120 characters or fewer.');
            return;
        }

        setSavingName(true);
        setNameError(null);
        try {
            await onSaveName(app, trimmedName);
            setNameDraft(trimmedName);
            setEditingName(false);
        } catch (err) {
            setNameError(apiErrorMessage(err));
        } finally {
            setSavingName(false);
        }
    };

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
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setSaving(false);
        }
    };

    const revoke = async (key: ApiKey) => {
        if (busyAction || editingName) return;
        setBusyAction(`revoke:${key.id}`);
        try {
            const confirmed = await confirm({
                title: 'Revoke API key?',
                description: `Key ${key.prefix} stops working immediately and every new realtime session using it is blocked.`,
                confirmText: 'Revoke key',
                variant: 'destructive',
            });
            if (confirmed) await onRevokeKey(key.id);
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setBusyAction(null);
        }
    };

    const rotate = async (key: ApiKey) => {
        if (busyAction || editingName) return;
        setBusyAction(`rotate:${key.id}`);
        try {
            const confirmed = await confirm({
                title: 'Rotate API key?',
                description: `A replacement key is issued and ${key.prefix} is revoked. Use Copy config on the replacement key.`,
                confirmText: 'Rotate key',
            });
            if (confirmed) await onRotateKey(key.id);
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setBusyAction(null);
        }
    };

    const deleteRevoked = async (key: ApiKey) => {
        if (busyAction || editingName) return;
        setBusyAction(`delete:${key.id}`);
        try {
            const confirmed = await confirm({
                title: 'Delete revoked API key?',
                description: `Revoked key ${key.prefix} will be permanently deleted. Call history is retained.`,
                confirmText: 'Delete key',
                variant: 'destructive',
            });
            if (confirmed) await onDeleteRevokedKey(key.id);
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setBusyAction(null);
        }
    };

    const remove = async () => {
        if (busyAction || editingName || hasActiveKeys) return;
        setBusyAction('delete-app');
        try {
            const confirmed = await confirm({
                title: 'Delete partner app?',
                description: `All API keys are already revoked. ${app.name} will be removed from management. Current calls finish, call history is retained, and integrations using agent slug "${app.agent_slug}" stop working.`,
                confirmText: 'Delete app',
                variant: 'destructive',
            });
            if (confirmed) await onDelete(app.id);
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setBusyAction(null);
        }
    };

    const issue = async () => {
        if (busyAction || editingName) return;
        setBusyAction('issue');
        try {
            await onIssueKey(app);
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setBusyAction(null);
        }
    };

    return (
        <ConfigCard>
            <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                    {editingName ? (
                        <form className="flex flex-wrap items-end gap-2" onSubmit={saveName}>
                            <FormInput
                                id={`partner-app-name-${app.id}`}
                                label="Partner app name"
                                value={nameDraft}
                                onChange={(event) => {
                                    setNameDraft(event.target.value);
                                    if (nameError) setNameError(null);
                                }}
                                error={nameError ?? undefined}
                                required
                                autoFocus
                                autoComplete="organization"
                            />
                            <div className="mb-4 flex gap-2">
                                <Button type="submit" size="sm" disabled={savingName}>
                                    {savingName ? 'Saving…' : 'Save'}
                                </Button>
                                <Button type="button" size="sm" variant="outline" onClick={cancelNameEdit} disabled={savingName}>
                                    Cancel
                                </Button>
                            </div>
                        </form>
                    ) : (
                        <div className="flex min-w-0 items-center gap-2">
                            <h3 className="text-lg font-semibold tracking-tight truncate">{app.name}</h3>
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="shrink-0 px-2"
                                onClick={startNameEdit}
                                disabled={busyAction !== null}
                                aria-label={`Edit name for ${app.name}`}
                                title="Edit partner app name"
                            >
                                <Pencil className="h-3.5 w-3.5" />
                            </Button>
                        </div>
                    )}
                    <code className="text-sm text-primary">{app.agent_slug}</code>
                </div>
                <div className="flex items-center gap-2">
                    <StatusPill tone={app.enabled ? 'success' : 'neutral'}>
                        {app.enabled ? 'Enabled' : 'Disabled'}
                    </StatusPill>
                    <button
                        type="button"
                        onClick={remove}
                        disabled={busyAction !== null || editingName || hasActiveKeys}
                        aria-label={`Delete ${app.name}`}
                        aria-describedby={hasActiveKeys ? `delete-help-${app.id}` : undefined}
                        title={hasActiveKeys ? 'Revoke active API keys before deleting this app.' : 'Delete partner app'}
                        className="p-1.5 rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
                    >
                        <Trash2 className="w-4 h-4" />
                    </button>
                </div>
            </div>
            {hasActiveKeys && (
                <p id={`delete-help-${app.id}`} className="mt-2 text-xs text-muted-foreground">
                    Revoke active API keys before deleting this app.
                </p>
            )}

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
                <Button size="sm" onClick={() => void issue()} disabled={busyAction !== null || editingName}>
                    <KeyRound className="w-3 h-3" />
                    {busyAction === 'issue' ? 'Issuing…' : 'Issue key'}
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
                            <span className="flex items-center gap-2">
                                <StatusPill tone="neutral">Revoked</StatusPill>
                                <Button
                                    size="sm"
                                    variant="ghost"
                                    className="text-destructive"
                                    disabled={busyAction !== null || editingName}
                                    onClick={() => void deleteRevoked(key)}
                                >
                                    Delete
                                </Button>
                            </span>
                        ) : (
                            <span className="flex gap-2">
                                <RevealedKeyBanner
                                    app={app}
                                    apiKey={key}
                                    onReveal={onRevealKey}
                                    hasEphemeralSecret={hasEphemeralSecret(key.id)}
                                />
                                <Button size="sm" variant="ghost" onClick={() => void rotate(key)} disabled={busyAction !== null || editingName}>
                                    Rotate
                                </Button>
                                <Button size="sm" variant="ghost" className="text-destructive" onClick={() => void revoke(key)} disabled={busyAction !== null || editingName}>
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
