import { Server } from 'lucide-react';

import { ConfigCard } from '../components/ui/ConfigCard';
import { ConfigSection } from '../components/ui/ConfigSection';
import ErrorPanel from '../components/ui/ErrorPanel';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { StatCard } from '../components/ui/StatCard';
import { StatusPill } from '../components/ui/StatusPill';
import { useGatewayData } from '../hooks/useGatewayData';

const Field = ({ label, value }: { label: string; value: string }) => (
    <div className="flex items-center justify-between gap-4 border-b border-border/60 py-2 last:border-0 text-sm">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium truncate">{value}</span>
    </div>
);

const AsteriskPage = () => {
    const { asterisk, runtime, loading, error } = useGatewayData();

    if (loading) return <PageLoader message="Loading Asterisk configuration…" />;

    return (
        <div>
            <PageHeader
                title="Asterisk"
                description="How this gateway reaches Asterisk. Credentials stay in the secret store and are never returned to the browser."
            />

            {error && <ErrorPanel type="error" message={error} className="mb-6" />}

            <div className="grid gap-4 sm:grid-cols-2 mb-6">
                <StatCard
                    title="ARI"
                    value={runtime.ari_connected ? 'Connected' : 'Down'}
                    icon={Server}
                    color={runtime.ari_connected ? 'text-green-500' : 'text-destructive'}
                />
                <StatCard
                    title="AudioSocket listener"
                    value={runtime.audiosocket_listening ? 'Listening' : 'Down'}
                    icon={Server}
                    color={runtime.audiosocket_listening ? 'text-green-500' : 'text-destructive'}
                />
            </div>

            <ConfigCard>
                <div className="flex items-center justify-between mb-4">
                    <h3 className="text-lg font-semibold tracking-tight">Connection</h3>
                    <StatusPill tone={asterisk?.configured ? 'success' : 'warning'}>
                        {asterisk?.configured ? 'Configured' : 'Not configured'}
                    </StatusPill>
                </div>

                {asterisk ? (
                    <>
                        <ConfigSection title="ARI" description="REST interface and Stasis application used for call control.">
                            <div>
                                <Field label="Host" value={asterisk.host ?? '—'} />
                                <Field label="Port" value={asterisk.ari_port ? String(asterisk.ari_port) : '—'} />
                                <Field label="Stasis app" value={asterisk.stasis_app ?? '—'} />
                                <Field label="Credentials" value={asterisk.credentials ?? '—'} />
                            </div>
                        </ConfigSection>

                        <ConfigSection title="Media" description="Transport the gateway advertises to Asterisk for audio.">
                            <div>
                                <Field label="Media transport" value={asterisk.media_transport} />
                                <Field label="AudioSocket host" value={asterisk.audiosocket_advertise_host} />
                                <Field label="AudioSocket port" value={String(asterisk.audiosocket_port)} />
                            </div>
                        </ConfigSection>
                    </>
                ) : (
                    <p className="text-sm text-muted-foreground">Asterisk configuration unavailable.</p>
                )}
            </ConfigCard>
        </div>
    );
};

export default AsteriskPage;
