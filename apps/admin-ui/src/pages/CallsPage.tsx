import { PhoneCall, RefreshCw } from 'lucide-react';

import Button from '../components/ui/Button';
import { DataTable } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import ErrorPanel from '../components/ui/ErrorPanel';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { StatusPill } from '../components/ui/StatusPill';
import { useGatewayData } from '../hooks/useGatewayData';

const CallsPage = () => {
    const { calls, loading, error, refresh } = useGatewayData();

    if (loading) return <PageLoader message="Loading active calls…" />;

    return (
        <div>
            <PageHeader
                title="Active Calls"
                description="Calls currently bridged to an agent through this organization's connections."
                actions={
                    <Button variant="outline" size="sm" onClick={refresh}>
                        <RefreshCw className="w-3.5 h-3.5" />
                        Refresh
                    </Button>
                }
            />
            {error && <ErrorPanel type="error" message={error} className="mb-6" />}
            <DataTable
                rows={calls}
                rowKey={(row) => row.id}
                empty={<EmptyState icon={PhoneCall} title="No active calls" />}
                columns={[
                    { header: 'Agent slug', cell: (row) => <code className="text-primary">{row.agent_slug}</code> },
                    { header: 'Call ID', cell: (row) => <code className="text-xs text-muted-foreground break-all">{row.id}</code> },
                    { header: 'Media transport', cell: (row) => <StatusPill tone="info">{row.media_transport}</StatusPill> },
                    {
                        header: 'Transfer',
                        cell: (row) =>
                            row.transfer_consulting ? (
                                <StatusPill tone="warning">Consulting</StatusPill>
                            ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                            ),
                    },
                ]}
            />
        </div>
    );
};

export default CallsPage;
