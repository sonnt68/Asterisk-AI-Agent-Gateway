import { Users } from 'lucide-react';

import { DataTable } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import ErrorPanel from '../components/ui/ErrorPanel';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { StatusPill } from '../components/ui/StatusPill';
import { useGatewayData } from '../hooks/useGatewayData';

const MembersPage = () => {
    const { members, loading, error } = useGatewayData();

    if (loading) return <PageLoader message="Loading members…" />;

    return (
        <div>
            <PageHeader title="Members" description="Everyone with access to this organization's control plane." />
            {error && <ErrorPanel type="error" message={error} className="mb-6" />}
            <DataTable
                rows={members}
                rowKey={(row) => row.user_id}
                empty={<EmptyState icon={Users} title="No members" />}
                columns={[
                    { header: 'Email', cell: (row) => <span className="font-medium">{row.email}</span> },
                    {
                        header: 'Role',
                        cell: (row) => <StatusPill tone={row.role === 'owner' ? 'info' : 'neutral'}>{row.role}</StatusPill>,
                    },
                    {
                        header: 'User ID',
                        cell: (row) => <code className="text-xs text-muted-foreground">{row.user_id}</code>,
                    },
                ]}
            />
        </div>
    );
};

export default MembersPage;
