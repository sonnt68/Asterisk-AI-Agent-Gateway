import { useState } from 'react';
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

type Row = ApiKey & { appName: string; agentSlug: string };

const ApiKeysPage = () => {
    const { apps, keys, loading, error, issueKey, rotateKey, revokeKey, deleteRevokedKey } = useGatewayData();
    const [selectedAppId, setSelectedAppId] = useState('');
    const [creatingKey, setCreatingKey] = useState(false);
    const { confirm } = useConfirmDialog();

    if (loading) return <PageLoader message="Loading API keys…" />;

    const selectedApp = apps.find((app) => app.id === selectedAppId) ?? apps[0];

    const rows: Row[] = apps.flatMap((app) =>
        (keys[app.id] ?? []).map((key) => ({ ...key, appName: app.name, agentSlug: app.agent_slug })),
    );
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
        const confirmed = await confirm({
            title: 'Rotate API key?',
            description: `A replacement key is issued and ${row.prefix} is revoked. Copy the new key immediately — it is shown once.`,
            confirmText: 'Rotate key',
        });
        if (confirmed) await rotateKey(row.id);
    };

    const revoke = async (row: Row) => {
        const confirmed = await confirm({
            title: 'Revoke API key?',
            description: `Key ${row.prefix} stops working immediately and every new realtime session using it is blocked.`,
            confirmText: 'Revoke key',
            variant: 'destructive',
        });
        if (confirmed) await revokeKey(row.id);
    };

    const deleteRevoked = async (row: Row) => {
        const confirmed = await confirm({
            title: 'Delete revoked API key?',
            description: `Revoked key ${row.prefix} will be permanently deleted. This cannot be undone.`,
            confirmText: 'Delete key',
            variant: 'destructive',
        });
        if (confirmed) await deleteRevokedKey(row.id);
    };

    return (
        <div>
            <PageHeader
                title="API Keys"
                description="Create a key for a partner app or manage existing credentials. Plaintext keys are shown once."
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

            <RevealedKeyBanner />

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
                                        onClick={() => deleteRevoked(row)}
                                    >
                                        <Trash2 className="w-3 h-3" />
                                        Delete
                                    </Button>
                                </span>
                            ) : (
                                <span className="flex justify-end gap-2">
                                    <Button size="sm" variant="outline" onClick={() => rotate(row)}>
                                        Rotate
                                    </Button>
                                    <Button size="sm" variant="ghost" className="text-destructive" onClick={() => revoke(row)}>
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
