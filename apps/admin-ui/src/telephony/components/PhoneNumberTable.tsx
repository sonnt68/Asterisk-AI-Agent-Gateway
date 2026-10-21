import { Edit3, Hash, Plus, Power } from 'lucide-react';

import { DataTable } from '../../components/ui/DataTable';
import { EmptyState } from '../../components/ui/EmptyState';
import Button from '../../components/ui/Button';
import { StatusPill } from '../../components/ui/StatusPill';
import type { LiveConnection, PartnerApp } from '../../lib/types';
import type { PhoneNumber, PhoneNumberOutboundApp } from '../types';

type PhoneNumberTableProps = {
    phoneNumbers: PhoneNumber[];
    apps: PartnerApp[];
    connections: LiveConnection[];
    canCreate: boolean;
    onCreate: () => void;
    onEdit: (phoneNumber: PhoneNumber) => void;
    onToggle: (phoneNumber: PhoneNumber) => void;
};

const formatDate = (value: string) => {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
};

const connectionFor = (appId: string, agentSlug: string, apps: PartnerApp[], connections: LiveConnection[]) => {
    const app = apps.find((candidate) => candidate.id === appId);
    const connected = connections.some((connection) => connection.partner_app_id === appId || connection.agent_slug === agentSlug || (app && connection.agent_slug === app.agent_slug));
    return { app, connected };
};

const AppConnection = ({ appId, name, agentSlug, enabled, apps, connections }: {
    appId: string;
    name: string;
    agentSlug: string;
    enabled: boolean;
    apps: PartnerApp[];
    connections: LiveConnection[];
}) => {
    const { connected } = connectionFor(appId, agentSlug, apps, connections);
    const state = !enabled ? 'Disabled' : connected ? 'Connected' : 'Not connected';
    const tone = !enabled ? 'neutral' : connected ? 'success' : 'neutral';
    return (
        <div className="min-w-0">
            <div className="truncate font-medium">{name || 'Unavailable Partner App'}</div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <code className="truncate">{agentSlug || '—'}</code>
                <StatusPill tone={tone}>{state}</StatusPill>
            </div>
        </div>
    );
};

const OutboundAssignments = ({ assignments, apps, connections }: {
    assignments: PhoneNumberOutboundApp[];
    apps: PartnerApp[];
    connections: LiveConnection[];
}) => {
    if (!assignments.length) return <span className="text-sm text-muted-foreground">None assigned</span>;
    return (
        <div className="space-y-2">
            {assignments.map((app) => (
                <AppConnection
                    key={app.id}
                    appId={app.id}
                    name={app.name}
                    agentSlug={app.agent_slug}
                    enabled={app.enabled}
                    apps={apps}
                    connections={connections}
                />
            ))}
        </div>
    );
};

const PhoneNumberTable = ({ phoneNumbers, apps, connections, canCreate, onCreate, onEdit, onToggle }: PhoneNumberTableProps) => (
    <DataTable
        rows={phoneNumbers}
        rowKey={(row) => row.id}
        empty={
            <EmptyState
                icon={Hash}
                title="No call routing numbers"
                description="Add an exact number, choose one inbound Partner App, and optionally share it for outbound caller ID."
                action={<Button onClick={onCreate} disabled={!canCreate}><Plus className="h-4 w-4" />Add phone number</Button>}
            />
        }
        columns={[
            {
                header: 'Number',
                cell: (row) => (
                    <div className="min-w-[11rem]">
                        <div className="flex items-center gap-2 font-medium">
                            <span>{row.number}</span>
                            <StatusPill tone={row.enabled ? 'success' : 'neutral'}>{row.enabled ? 'Enabled' : 'Disabled'}</StatusPill>
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{row.label || 'No label'}</p>
                    </div>
                ),
            },
            {
                header: 'Inbound Partner App',
                cell: (row) => {
                    const app = apps.find((candidate) => candidate.id === row.partner_app_id);
                    return (
                        <AppConnection
                            appId={row.partner_app_id}
                            name={row.partner_app_name || app?.name || 'Unavailable Partner App'}
                            agentSlug={row.agent_slug || app?.agent_slug || ''}
                            enabled={app?.enabled ?? true}
                            apps={apps}
                            connections={connections}
                        />
                    );
                },
            },
            {
                header: 'Outbound Partner Apps',
                cell: (row) => <OutboundAssignments assignments={row.outbound_partner_apps ?? []} apps={apps} connections={connections} />,
            },
            {
                header: 'PBX state',
                cell: (row) => (
                    <div className="text-sm">
                        <StatusPill tone={row.pbx_applied ? 'success' : 'warning'}>{row.pbx_applied ? 'Applied' : 'Awaiting apply'}</StatusPill>
                        <div className="mt-1 text-xs text-muted-foreground">Updated {formatDate(row.updated_at)}</div>
                    </div>
                ),
            },
            {
                header: 'Actions',
                className: 'whitespace-nowrap',
                cell: (row) => (
                    <div className="flex items-center gap-1">
                        <Button variant="ghost" size="sm" onClick={() => onEdit(row)} aria-label={`Edit ${row.number}`}>
                            <Edit3 className="h-3.5 w-3.5" />
                            Edit
                        </Button>
                        <Button variant="ghost" size="sm" onClick={() => onToggle(row)} aria-label={`${row.enabled ? 'Disable' : 'Enable'} ${row.number}`}>
                            <Power className="h-3.5 w-3.5" />
                            {row.enabled ? 'Disable' : 'Enable'}
                        </Button>
                    </div>
                ),
            },
        ]}
    />
);

export default PhoneNumberTable;
