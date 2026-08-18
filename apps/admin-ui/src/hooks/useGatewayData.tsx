import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';

import { useAuth } from '../auth/AuthContext';
import { api } from '../lib/api';
import type {
    ApiKey,
    AsteriskConfig,
    AuditEvent,
    LiveCall,
    LiveConnection,
    Member,
    PartnerApp,
    Runtime,
} from '../lib/types';
import { apiErrorMessage } from '../utils/apiErrors';

const EMPTY_RUNTIME: Runtime = {
    active_connections: 0,
    active_calls: 0,
    ari_connected: false,
    audiosocket_listening: false,
};

/** Poll interval for the runtime-facing panels, matching the AVA dashboard. */
const POLL_INTERVAL_MS = 5000;

interface GatewayData {
    apps: PartnerApp[];
    keys: Record<string, ApiKey[]>;
    runtime: Runtime;
    auditEvents: AuditEvent[];
    asterisk: AsteriskConfig | null;
    connections: LiveConnection[];
    calls: LiveCall[];
    members: Member[];
    loading: boolean;
    error: string | null;
    revealedKey: { value: string; appId: string } | null;
    dismissRevealedKey: () => void;
    refresh: () => Promise<void>;
    createApp: (input: { name: string; agent_slug: string; scopes: string[] }) => Promise<void>;
    deleteApp: (appId: string) => Promise<void>;
    savePolicy: (app: PartnerApp, allowedDestinations: string[]) => Promise<void>;
    issueKey: (app: PartnerApp) => Promise<void>;
    rotateKey: (keyId: string) => Promise<void>;
    revokeKey: (keyId: string) => Promise<void>;
}

const GatewayDataContext = createContext<GatewayData | null>(null);

export const GatewayDataProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const { session, isAuthenticated } = useAuth();
    const organizationId = session?.organization_id;

    const [apps, setApps] = useState<PartnerApp[]>([]);
    const [keys, setKeys] = useState<Record<string, ApiKey[]>>({});
    const [runtime, setRuntime] = useState<Runtime>(EMPTY_RUNTIME);
    const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
    const [asterisk, setAsterisk] = useState<AsteriskConfig | null>(null);
    const [connections, setConnections] = useState<LiveConnection[]>([]);
    const [calls, setCalls] = useState<LiveCall[]>([]);
    const [members, setMembers] = useState<Member[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [revealedKey, setRevealedKey] = useState<{ value: string; appId: string } | null>(null);

    // Guards the polling timer against overlapping in-flight refreshes.
    const refreshing = useRef(false);

    const refresh = useCallback(async () => {
        if (!organizationId || refreshing.current) return;
        refreshing.current = true;
        try {
            const [partnerApps, runtimeState, events, asteriskConfig, liveConnections, liveCalls, organizationMembers] =
                await Promise.all([
                    api.get<PartnerApp[]>(`/organizations/${organizationId}/partner-apps`),
                    api.get<Runtime>('/runtime'),
                    api.get<AuditEvent[]>('/audit-events'),
                    api.get<AsteriskConfig>('/asterisk'),
                    api.get<LiveConnection[]>('/connections'),
                    api.get<LiveCall[]>('/calls'),
                    api.get<Member[]>('/organization/members'),
                ]);

            setApps(partnerApps.data);
            setRuntime(runtimeState.data);
            setAuditEvents(events.data);
            setAsterisk(asteriskConfig.data);
            setConnections(liveConnections.data);
            setCalls(liveCalls.data);
            setMembers(organizationMembers.data);

            const entries = await Promise.all(
                partnerApps.data.map(
                    async (app) => [app.id, (await api.get<ApiKey[]>(`/partner-apps/${app.id}/api-keys`)).data] as const,
                ),
            );
            setKeys(Object.fromEntries(entries));
            setError(null);
        } catch (err) {
            setError(apiErrorMessage(err));
        } finally {
            refreshing.current = false;
            setLoading(false);
        }
    }, [organizationId]);

    useEffect(() => {
        if (!isAuthenticated || !organizationId) {
            setLoading(false);
            return;
        }
        setLoading(true);
        refresh();
        const interval = setInterval(refresh, POLL_INTERVAL_MS);
        return () => clearInterval(interval);
    }, [isAuthenticated, organizationId, refresh]);

    const run = useCallback(
        async (action: () => Promise<void>, successMessage: string) => {
            try {
                await action();
                await refresh();
                toast.success(successMessage);
            } catch (err) {
                toast.error('Request failed', { description: apiErrorMessage(err) });
                throw err;
            }
        },
        [refresh],
    );

    const createApp: GatewayData['createApp'] = useCallback(
        (input) =>
            run(async () => {
                await api.post(`/organizations/${organizationId}/partner-apps`, input);
            }, 'Partner app created.'),
        [organizationId, run],
    );

    const deleteApp: GatewayData['deleteApp'] = useCallback(
        (appId) =>
            run(async () => {
                await api.delete(`/partner-apps/${appId}`);
            }, 'Partner app deleted.'),
        [run],
    );

    const savePolicy: GatewayData['savePolicy'] = useCallback(
        (app, allowedDestinations) =>
            run(async () => {
                await api.patch(`/partner-apps/${app.id}`, { allowed_destinations: allowedDestinations });
            }, 'Destination policy saved.'),
        [run],
    );

    const issueKey: GatewayData['issueKey'] = useCallback(
        (app) =>
            run(async () => {
                const response = await api.post<{ key: string }>(`/partner-apps/${app.id}/api-keys`, {
                    name: `${app.agent_slug}-key`,
                    scopes: app.scopes,
                });
                setRevealedKey({ value: response.data.key, appId: app.id });
            }, 'API key issued. Copy it now — it will not be shown again.'),
        [run],
    );

    const rotateKey: GatewayData['rotateKey'] = useCallback(
        (keyId) =>
            run(async () => {
                const response = await api.post<{ key: string }>(`/api-keys/${keyId}/rotate`);
                setRevealedKey({ value: response.data.key, appId: '' });
            }, 'Key rotated. Copy the replacement now; the old key is revoked.'),
        [run],
    );

    const revokeKey: GatewayData['revokeKey'] = useCallback(
        (keyId) =>
            run(async () => {
                await api.delete(`/api-keys/${keyId}`);
            }, 'API key revoked. New realtime sessions are blocked.'),
        [run],
    );

    const dismissRevealedKey = useCallback(() => setRevealedKey(null), []);

    return (
        <GatewayDataContext.Provider
            value={{
                apps,
                keys,
                runtime,
                auditEvents,
                asterisk,
                connections,
                calls,
                members,
                loading,
                error,
                revealedKey,
                dismissRevealedKey,
                refresh,
                createApp,
                deleteApp,
                savePolicy,
                issueKey,
                rotateKey,
                revokeKey,
            }}
        >
            {children}
        </GatewayDataContext.Provider>
    );
};

export const useGatewayData = () => {
    const context = useContext(GatewayDataContext);
    if (!context) {
        throw new Error('useGatewayData must be used within a GatewayDataProvider');
    }
    return context;
};
