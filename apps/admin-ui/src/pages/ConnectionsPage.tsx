import { Radio, RefreshCw } from 'lucide-react';

import Button from '../components/ui/Button';
import { DataTable } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import ErrorPanel from '../components/ui/ErrorPanel';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { useGatewayData } from '../hooks/useGatewayData';

const ConnectionsPage = () => {
    const { connections, loading, error, refresh } = useGatewayData();

    if (loading) return <PageLoader message="Loading connections…" />;

    return (
        <div>
            <PageHeader
                title="Connections"
                description="Realtime WebSocket sessions currently attached to this organization. Refreshes every 5 seconds."
                actions={
                    <Button variant="outline" size="sm" onClick={refresh}>
                        <RefreshCw className="w-3.5 h-3.5" />
                        Refresh
                    </Button>
                }
            />
            {error && <ErrorPanel type="error" message={error} className="mb-6" />}
            <DataTable
                rows={connections}
                rowKey={(row) => row.id}
                empty={
                    <EmptyState
                        icon={Radio}
                        title="No realtime connections"
                        description="A partner integration appears here as soon as it opens a realtime session."
                    />
                }
                columns={[
                    { header: 'Agent slug', cell: (row) => <code className="text-primary">{row.agent_slug}</code> },
                    {
                        header: 'Connection ID',
                        cell: (row) => <code className="text-xs text-muted-foreground break-all">{row.id}</code>,
                    },
                    {
                        header: 'Scopes',
                        cell: (row) => (
                            <div className="flex flex-wrap gap-1">
                                {row.scopes.map((scope) => (
                                    <span
                                        key={scope}
                                        className="rounded bg-muted px-2 py-0.5 text-[11px] font-medium text-muted-foreground"
                                    >
                                        {scope}
                                    </span>
                                ))}
                            </div>
                        ),
                    },
                ]}
            />
        </div>
    );
};

export default ConnectionsPage;
