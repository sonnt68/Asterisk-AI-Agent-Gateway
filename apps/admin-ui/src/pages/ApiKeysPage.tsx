import { useEffect, useRef, useState } from 'react';
import { KeyRound, Plus, Trash2 } from 'lucide-react';

import RevealedKeyBanner from '../components/RevealedKeyBanner';
import Button from '../components/ui/Button';
import { DataTable } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import ErrorPanel from '../components/ui/ErrorPanel';
import { FormSelect } from '../components/ui/FormComponents';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { StatusPill } from '../components/ui/StatusPill';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { useGatewayData } from '../hooks/useGatewayData';
import type { ApiKey } from '../lib/types';

type Row = ApiKey & { appId: string; appName: string; agentSlug: string };

const ApiKeysPage = () => {
    const { apps, keys, loading, error, issueKey, rotateKey, revealKey, hasEphemeralSecret, revokeKey, deleteRevokedKey, revokeKeys, deleteRevokedKeys } =
        useGatewayData();
    const [selectedAppId, setSelectedAppId] = useState('');
    const [creatingKey, setCreatingKey] = useState(false);
    const [rowAction, setRowAction] = useState<string | null>(null);
    const [selectedKeyIds, setSelectedKeyIds] = useState<Set<string>>(() => new Set());
    const [bulkAction, setBulkAction] = useState<'revoke' | 'delete' | null>(null);
    const selectAllRef = useRef<HTMLInputElement>(null);
    const { confirm } = useConfirmDialog();

    const rows: Row[] = apps.flatMap((app) =>
        (keys[app.id] ?? []).map((key) => ({ ...key, appId: app.id, appName: app.name, agentSlug: app.agent_slug })),
    );
    const selectedRows = rows.filter((row) => selectedKeyIds.has(row.id));
    const selectedActiveRows = selectedRows.filter((row) => !row.revoked_at);
    const selectedRevokedRows = selectedRows.filter((row) => Boolean(row.revoked_at));
    const allRowsSelected = rows.length > 0 && selectedRows.length === rows.length;
    const someRowsSelected = selectedRows.length > 0 && !allRowsSelected;

    useEffect(() => {
        if (selectAllRef.current) selectAllRef.current.indeterminate = someRowsSelected;
    }, [someRowsSelected]);

    if (loading) return <PageLoader message="Loading API keys…" />;

    const selectedApp = apps.find((app) => app.id === selectedAppId) ?? apps[0];

    const setRowSelected = (keyId: string, selected: boolean) => {
        setSelectedKeyIds((current) => {
            const next = new Set(current);
            if (selected) next.add(keyId);
            else next.delete(keyId);
            return next;
        });
    };

    const createKey = async () => {
        if (!selectedApp || creatingKey) return;
        setCreatingKey(true);
        try {
            await issueKey(selectedApp);
        } catch {
            // Request errors are already surfaced by the data layer.
        } finally {
            setCreatingKey(false);
        }
    };

    const rotate = async (row: Row) => {
        if (rowAction || bulkAction) return;
        setRowAction(`rotate:${row.id}`);
        try {
            const confirmed = await confirm({
                title: 'Rotate API key?',
                description: `A replacement key is issued and ${row.prefix} is revoked. Use Copy config on the replacement key.`,
                confirmText: 'Rotate key',
            });
            if (confirmed) await rotateKey(row.id);
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setRowAction(null);
        }
    };

    const revoke = async (row: Row) => {
        if (rowAction || bulkAction) return;
        setRowAction(`revoke:${row.id}`);
        try {
            const confirmed = await confirm({
                title: 'Revoke API key?',
                description: `Key ${row.prefix} stops working immediately and every new realtime session using it is blocked.`,
                confirmText: 'Revoke key',
                variant: 'destructive',
            });
            if (confirmed) await revokeKey(row.id);
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setRowAction(null);
        }
    };

    const deleteRevoked = async (row: Row) => {
        if (rowAction || bulkAction) return;
        setRowAction(`delete:${row.id}`);
        try {
            const confirmed = await confirm({
                title: 'Delete revoked API key?',
                description: `Revoked key ${row.prefix} will be permanently deleted. Call history is retained.`,
                confirmText: 'Delete key',
                variant: 'destructive',
            });
            if (confirmed) await deleteRevokedKey(row.id);
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setRowAction(null);
        }
    };

    const revokeSelected = async () => {
        const keyIds = selectedActiveRows.map((row) => row.id);
        if (keyIds.length === 0 || bulkAction || rowAction) return;
        const confirmed = await confirm({
            title: `Revoke ${keyIds.length} selected API key${keyIds.length === 1 ? '' : 's'}?`,
            description: `Only these ${keyIds.length} selected active key${keyIds.length === 1 ? '' : 's'} will be revoked. Already-revoked selections are unchanged.`,
            confirmText: `Revoke ${keyIds.length} key${keyIds.length === 1 ? '' : 's'}`,
            variant: 'destructive',
        });
        if (!confirmed) return;

        setBulkAction('revoke');
        try {
            const { failedKeyIds } = await revokeKeys(keyIds);
            setSelectedKeyIds(new Set(failedKeyIds));
        } finally {
            setBulkAction(null);
        }
    };

    const deleteSelectedRevoked = async () => {
        const keyIds = selectedRevokedRows.map((row) => row.id);
        if (keyIds.length === 0 || bulkAction || rowAction) return;
        const confirmed = await confirm({
            title: `Delete ${keyIds.length} selected revoked API key${keyIds.length === 1 ? '' : 's'}?`,
            description: `Only these ${keyIds.length} revoked key${keyIds.length === 1 ? '' : 's'} will be permanently deleted. Active selections are unchanged.`,
            confirmText: `Delete ${keyIds.length} key${keyIds.length === 1 ? '' : 's'}`,
            variant: 'destructive',
        });
        if (!confirmed) return;

        setBulkAction('delete');
        try {
            const { failedKeyIds } = await deleteRevokedKeys(keyIds);
            setSelectedKeyIds(new Set(failedKeyIds));
        } finally {
            setBulkAction(null);
        }
    };

    return (
        <div>
            <PageHeader
                title="API Keys"
                description="Create a key for a partner app or manage existing credentials. Keys stay hidden; copy configuration retrieves setup values for recoverable keys."
            />
            <div className="mb-6 flex flex-wrap items-end gap-2">
                <FormSelect
                    label="Partner app"
                    options={
                        apps.length
                            ? apps.map((app) => ({
                                  value: app.id,
                                  label: `${app.name} (${app.agent_slug})`,
                              }))
                            : [{ value: '', label: 'No partner apps' }]
                    }
                    value={selectedApp?.id ?? ''}
                    onChange={(event) => setSelectedAppId(event.target.value)}
                    disabled={!apps.length || creatingKey}
                    className="w-64 max-w-full"
                />
                <Button className="mb-4" onClick={createKey} disabled={!selectedApp || creatingKey}>
                    <Plus className="w-4 h-4" />
                    {creatingKey ? 'Creating…' : 'Create API key'}
                </Button>
            </div>

            {error && <ErrorPanel type="error" message={error} className="mb-6" />}

            {rows.length > 0 && (
                <div className="mb-3 flex flex-wrap items-center gap-3">
                    <label className="inline-flex items-center gap-2 text-sm">
                        <input
                            ref={selectAllRef}
                            type="checkbox"
                            aria-label="Select all API keys"
                            checked={allRowsSelected}
                            onChange={() =>
                                setSelectedKeyIds(allRowsSelected ? new Set() : new Set(rows.map((row) => row.id)))
                            }
                            disabled={bulkAction !== null || rowAction !== null}
                            className="h-4 w-4 accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                        />
                        Select all keys
                    </label>
                    <span className="text-xs text-muted-foreground" aria-live="polite">
                        {selectedRows.length} selected
                    </span>
                    {selectedActiveRows.length > 0 && (
                        <Button
                            size="sm"
                            variant="destructive"
                            onClick={revokeSelected}
                            disabled={bulkAction !== null || rowAction !== null}
                        >
                            {bulkAction === 'revoke' ? 'Revoking…' : `Revoke active (${selectedActiveRows.length})`}
                        </Button>
                    )}
                    {selectedRevokedRows.length > 0 && (
                        <Button
                            size="sm"
                            variant="destructive"
                            onClick={deleteSelectedRevoked}
                            disabled={bulkAction !== null || rowAction !== null}
                        >
                            {bulkAction === 'delete' ? 'Deleting…' : `Delete revoked (${selectedRevokedRows.length})`}
                        </Button>
                    )}
                    <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setSelectedKeyIds(new Set())}
                        disabled={selectedRows.length === 0 || bulkAction !== null || rowAction !== null}
                    >
                        Clear selection
                    </Button>
                </div>
            )}

            <DataTable
                rows={rows}
                rowKey={(row) => row.id}
                empty={
                    <EmptyState
                        icon={KeyRound}
                        title="No API keys issued"
                        description={
                            apps.length
                                ? 'Choose a partner app above to issue the first key.'
                                : 'Create a partner app before issuing an API key.'
                        }
                    />
                }
                columns={[
                    {
                        header: 'Select',
                        className: 'w-12',
                        cell: (row) => (
                            <input
                                type="checkbox"
                                aria-label={`Select API key ${row.prefix}`}
                                checked={selectedKeyIds.has(row.id)}
                                onChange={(event) => setRowSelected(row.id, event.target.checked)}
                                disabled={bulkAction !== null || rowAction !== null}
                                className="h-4 w-4 accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                            />
                        ),
                    },
                    {
                        header: 'Key',
                        cell: (row) => (
                            <div className="min-w-0">
                                <div className="font-medium truncate">{row.name}</div>
                                <code className="text-xs text-muted-foreground">{row.prefix}</code>
                            </div>
                        ),
                    },
                    {
                        header: 'Partner app',
                        cell: (row) => (
                            <div className="min-w-0">
                                <div className="truncate">{row.appName}</div>
                                <code className="text-xs text-primary">{row.agentSlug}</code>
                            </div>
                        ),
                    },
                    {
                        header: 'Status',
                        cell: (row) =>
                            row.revoked_at ? (
                                <StatusPill tone="neutral">Revoked</StatusPill>
                            ) : (
                                <StatusPill tone="success">Active</StatusPill>
                            ),
                    },
                    {
                        header: 'Created',
                        cell: (row) => (
                            <span className="text-xs text-muted-foreground">
                                {row.created_at ? new Date(row.created_at).toLocaleString() : '—'}
                            </span>
                        ),
                    },
                    {
                        header: 'Actions',
                        className: 'text-right',
                        cell: (row) =>
                            row.revoked_at ? (
                                <span className="flex justify-end">
                                    <Button
                                        size="sm"
                                        variant="ghost"
                                        className="text-destructive"
                                        aria-label={`Delete revoked API key ${row.prefix}`}
                                        disabled={bulkAction !== null || rowAction !== null}
                                        onClick={() => void deleteRevoked(row)}
                                    >
                                        <Trash2 className="w-3 h-3" />
                                        Delete
                                    </Button>
                                </span>
                            ) : (
                                <span className="flex justify-end gap-2">
                                    <RevealedKeyBanner
                                        app={apps.find((app) => app.id === row.appId)}
                                        apiKey={row}
                                        onReveal={revealKey}
                                        hasEphemeralSecret={hasEphemeralSecret(row.id)}
                                    />
                                    <Button size="sm" variant="outline" onClick={() => void rotate(row)} disabled={bulkAction !== null || rowAction !== null}>
                                        Rotate
                                    </Button>
                                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => void revoke(row)} disabled={bulkAction !== null || rowAction !== null}>
                                        Revoke
                                    </Button>
                                </span>
                            ),
                    },
                ]}
            />
        </div>
    );
};

export default ApiKeysPage;
