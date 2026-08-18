import { useState } from 'react';
import { ScrollText } from 'lucide-react';

import { DataTable } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import ErrorPanel from '../components/ui/ErrorPanel';
import { FormInput } from '../components/ui/FormComponents';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { useGatewayData } from '../hooks/useGatewayData';

const AuditPage = () => {
    const { auditEvents, loading, error } = useGatewayData();
    const [query, setQuery] = useState('');

    if (loading) return <PageLoader message="Loading audit events…" />;

    const needle = query.trim().toLowerCase();
    const rows = needle
        ? auditEvents.filter(
              (event) =>
                  event.action.toLowerCase().includes(needle) || (event.target_id ?? '').toLowerCase().includes(needle),
          )
        : auditEvents;

    return (
        <div>
            <PageHeader
                title="Audit Events"
                description="Every control-plane mutation is recorded: logins, key issuance, rotation, revocation, and policy changes."
            />

            {error && <ErrorPanel type="error" message={error} className="mb-6" />}

            <div className="max-w-sm">
                <FormInput
                    label="Filter"
                    placeholder="Filter by action or target"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                />
            </div>

            <DataTable
                rows={rows}
                rowKey={(row) => row.id}
                empty={<EmptyState icon={ScrollText} title="No audit events match" />}
                columns={[
                    { header: 'Action', cell: (row) => <span className="font-medium">{row.action}</span> },
                    {
                        header: 'Target',
                        cell: (row) => <code className="text-xs text-muted-foreground break-all">{row.target_id ?? 'system'}</code>,
                    },
                    {
                        header: 'When',
                        className: 'text-right',
                        cell: (row) => (
                            <time className="text-xs text-muted-foreground whitespace-nowrap">
                                {new Date(row.created_at).toLocaleString()}
                            </time>
                        ),
                    },
                ]}
            />
        </div>
    );
};

export default AuditPage;
