import { KeyRound } from 'lucide-react';

import RevealedKeyBanner from '../components/RevealedKeyBanner';
import Button from '../components/ui/Button';
import { DataTable } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import ErrorPanel from '../components/ui/ErrorPanel';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { StatusPill } from '../components/ui/StatusPill';
import { useConfirmDialog } from '../hooks/useConfirmDialog';
import { useGatewayData } from '../hooks/useGatewayData';
import type { ApiKey } from '../lib/types';

type Row = ApiKey & { appName: string; agentSlug: string };

const ApiKeysPage = () => {
    const { apps, keys, loading, error, rotateKey, revokeKey } = useGatewayData();
    const { confirm } = useConfirmDialog();

    if (loading) return <PageLoader message="Loading API keys…" />;

    const rows: Row[] = apps.flatMap((app) =>
        (keys[app.id] ?? []).map((key) => ({ ...key, appName: app.name, agentSlug: app.agent_slug })),
    );

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

    return (
        <div>
            <PageHeader
                title="API Keys"
                description="Every key belongs to a partner app. Keys are hashed at rest — rotate or revoke instead of recovering them."
            />

            {error && <ErrorPanel type="error" message={error} className="mb-6" />}

            <RevealedKeyBanner />

            <DataTable
                rows={rows}
                rowKey={(row) => row.id}
                empty={
                    <EmptyState
                        icon={KeyRound}
                        title="No API keys issued"
                        description="Issue a key from the Partner Apps page to let an integration authenticate."
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
                                <span className="text-xs text-muted-foreground">—</span>
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
