import { FormEvent, useState } from 'react';
import { AppWindow, Plus } from 'lucide-react';

import PartnerAppCard from '../components/PartnerAppCard';
import RevealedKeyBanner from '../components/RevealedKeyBanner';
import Button from '../components/ui/Button';
import { ConfigCard } from '../components/ui/ConfigCard';
import { EmptyState } from '../components/ui/EmptyState';
import ErrorPanel from '../components/ui/ErrorPanel';
import { FormInput } from '../components/ui/FormComponents';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { useGatewayData } from '../hooks/useGatewayData';

const DEFAULT_SCOPES = ['calls:read', 'media:stream', 'calls:hangup'];

const PartnerAppsPage = () => {
    const { apps, keys, loading, error, createApp, deleteApp, savePolicy, issueKey, rotateKey, revokeKey } =
        useGatewayData();
    const [name, setName] = useState('');
    const [slug, setSlug] = useState('');
    const [creating, setCreating] = useState(false);

    const submit = async (event: FormEvent) => {
        event.preventDefault();
        setCreating(true);
        try {
            await createApp({ name, agent_slug: slug, scopes: DEFAULT_SCOPES });
            setName('');
            setSlug('');
        } catch {
            // Toast already surfaced by the data layer.
        } finally {
            setCreating(false);
        }
    };

    if (loading) return <PageLoader message="Loading partner apps…" />;

    return (
        <div>
            <PageHeader
                title="Partner Apps"
                description="Each partner app maps a third-party integration to an agent slug, its scopes, and its outbound destination policy."
            />

            {error && <ErrorPanel type="error" message={error} className="mb-6" />}

            <RevealedKeyBanner />

            <ConfigCard className="mb-6">
                <h3 className="text-lg font-semibold tracking-tight mb-1">Create partner app</h3>
                <p className="text-sm text-muted-foreground mb-4">
                    Issued with the default scopes: {DEFAULT_SCOPES.join(', ')}.
                </p>
                <form className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-start" onSubmit={submit}>
                    <FormInput
                        label="Name"
                        placeholder="Partner app name"
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        required
                    />
                    <FormInput
                        label="Agent slug"
                        placeholder="agent-slug"
                        pattern="[a-z0-9-]{3,80}"
                        tooltip="Lowercase letters, digits and dashes. Partner SDKs connect using this slug."
                        value={slug}
                        onChange={(event) => setSlug(event.target.value)}
                        required
                    />
                    <Button type="submit" className="md:mt-[26px]" disabled={creating}>
                        <Plus className="w-4 h-4" />
                        {creating ? 'Creating…' : 'Create app'}
                    </Button>
                </form>
            </ConfigCard>

            {apps.length === 0 ? (
                <EmptyState
                    icon={AppWindow}
                    title="No partner apps yet"
                    description="Create the first partner app to issue API keys and let an integration place calls through the gateway."
                />
            ) : (
                <div className="grid gap-4 lg:grid-cols-2">
                    {apps.map((app) => (
                        <PartnerAppCard
                            key={app.id}
                            app={app}
                            keys={keys[app.id] ?? []}
                            onIssueKey={issueKey}
                            onRevokeKey={revokeKey}
                            onRotateKey={rotateKey}
                            onSavePolicy={savePolicy}
                            onDelete={deleteApp}
                        />
                    ))}
                </div>
            )}
        </div>
    );
};

export default PartnerAppsPage;
