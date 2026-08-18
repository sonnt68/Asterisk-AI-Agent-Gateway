import { Link } from 'react-router-dom';
import { AppWindow, KeyRound, PhoneCall, Radio, RefreshCw, ScrollText, Server, Users } from 'lucide-react';

import RevealedKeyBanner from '../components/RevealedKeyBanner';
import { ConfigCard } from '../components/ui/ConfigCard';
import { EmptyState } from '../components/ui/EmptyState';
import ErrorPanel from '../components/ui/ErrorPanel';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { StatCard } from '../components/ui/StatCard';
import { StatusPill } from '../components/ui/StatusPill';
import Button from '../components/ui/Button';
import { useAuth } from '../auth/AuthContext';
import { useGatewayData } from '../hooks/useGatewayData';

const Dashboard = () => {
    const { session } = useAuth();
    const { runtime, apps, keys, members, calls, connections, auditEvents, asterisk, loading, error, refresh } =
        useGatewayData();

    if (loading) return <PageLoader message="Loading control plane…" />;

    const activeKeys = Object.values(keys)
        .flat()
        .filter((key) => !key.revoked_at).length;

    return (
        <div>
            <PageHeader
                title="Dashboard"
                description={`Organization ${session?.organization_id ?? ''} · signed in as ${session?.role ?? ''}`}
                actions={
                    <Button variant="outline" size="sm" onClick={refresh}>
                        <RefreshCw className="w-3.5 h-3.5" />
                        Refresh
                    </Button>
                }
            />

            {error && <ErrorPanel type="error" message={error} className="mb-6" />}

            <RevealedKeyBanner />

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
                <StatCard
                    title="ARI"
                    value={runtime.ari_connected ? 'Connected' : 'Down'}
                    icon={Server}
                    color={runtime.ari_connected ? 'text-green-500' : 'text-destructive'}
                />
                <StatCard
                    title="AudioSocket"
                    value={runtime.audiosocket_listening ? 'Listening' : 'Down'}
                    icon={Radio}
                    color={runtime.audiosocket_listening ? 'text-green-500' : 'text-destructive'}
                />
                <StatCard title="Realtime connections" value={runtime.active_connections} icon={Radio} />
                <StatCard title="Active calls" value={runtime.active_calls} icon={PhoneCall} />
            </div>

            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4 mb-6">
                <StatCard title="Partner apps" value={apps.length} icon={AppWindow} />
                <StatCard title="Active API keys" value={activeKeys} icon={KeyRound} />
                <StatCard title="Members" value={members.length} icon={Users} />
                <StatCard title="Audit events" value={auditEvents.length} icon={ScrollText} />
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
                <ConfigCard>
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="text-lg font-semibold tracking-tight">Asterisk connection</h3>
                        <StatusPill tone={asterisk?.configured ? 'success' : 'warning'}>
                            {asterisk?.configured ? 'Configured' : 'Not configured'}
                        </StatusPill>
                    </div>
                    {asterisk ? (
                        <dl className="space-y-2 text-sm">
                            <Row label="ARI endpoint" value={`${asterisk.host ?? '—'}:${asterisk.ari_port ?? '—'}`} />
                            <Row label="Stasis app" value={asterisk.stasis_app ?? '—'} />
                            <Row label="Media transport" value={asterisk.media_transport} />
                            <Row
                                label="AudioSocket"
                                value={`${asterisk.audiosocket_advertise_host}:${asterisk.audiosocket_port}`}
                            />
                            <Row label="Credentials" value={asterisk.credentials ?? '—'} />
                        </dl>
                    ) : (
                        <p className="text-sm text-muted-foreground">Asterisk configuration unavailable.</p>
                    )}
                    <p className="mt-3 text-xs text-muted-foreground">
                        Credentials are secret-managed and never returned to the dashboard.
                    </p>
                </ConfigCard>

                <ConfigCard>
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="text-lg font-semibold tracking-tight">Recent audit events</h3>
                        <Link to="/audit" className="text-xs text-primary hover:underline">
                            View all
                        </Link>
                    </div>
                    {auditEvents.length === 0 ? (
                        <EmptyState icon={ScrollText} title="No audit events yet" />
                    ) : (
                        <div className="space-y-2 text-sm">
                            {auditEvents.slice(0, 8).map((event) => (
                                <div
                                    key={event.id}
                                    className="flex items-center justify-between gap-4 border-b border-border/60 pb-2 last:border-0"
                                >
                                    <span className="truncate">
                                        <span className="font-medium">{event.action}</span>
                                        <span className="text-muted-foreground"> · {event.target_id ?? 'system'}</span>
                                    </span>
                                    <time className="text-xs text-muted-foreground whitespace-nowrap">
                                        {new Date(event.created_at).toLocaleString()}
                                    </time>
                                </div>
                            ))}
                        </div>
                    )}
                </ConfigCard>

                <ConfigCard>
                    <h3 className="text-lg font-semibold tracking-tight mb-3">Live connections</h3>
                    {connections.length === 0 ? (
                        <EmptyState icon={Radio} title="No realtime connections" />
                    ) : (
                        <ul className="space-y-2 text-sm">
                            {connections.slice(0, 6).map((item) => (
                                <li key={item.id} className="flex items-center justify-between gap-3">
                                    <span className="font-medium truncate">{item.agent_slug}</span>
                                    <code className="text-xs text-muted-foreground truncate">{item.id}</code>
                                </li>
                            ))}
                        </ul>
                    )}
                </ConfigCard>

                <ConfigCard>
                    <h3 className="text-lg font-semibold tracking-tight mb-3">Active calls</h3>
                    {calls.length === 0 ? (
                        <EmptyState icon={PhoneCall} title="No active calls" />
                    ) : (
                        <ul className="space-y-2 text-sm">
                            {calls.slice(0, 6).map((call) => (
                                <li key={call.id} className="flex items-center justify-between gap-3">
                                    <span className="font-medium truncate">{call.agent_slug}</span>
                                    <StatusPill tone="info">{call.media_transport}</StatusPill>
                                </li>
                            ))}
                        </ul>
                    )}
                </ConfigCard>
            </div>
        </div>
    );
};

const Row = ({ label, value }: { label: string; value: string }) => (
    <div className="flex items-center justify-between gap-4">
        <dt className="text-muted-foreground">{label}</dt>
        <dd className="font-medium truncate">{value}</dd>
    </div>
);

export default Dashboard;
