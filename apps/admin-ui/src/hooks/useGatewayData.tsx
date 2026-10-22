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
    ApiKeyReveal,
} from '../lib/types';
import { apiErrorMessage, describeApiError } from '../utils/apiErrors';

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
    refresh: () => Promise<void>;
    createApp: (input: { name: string; agent_slug: string; scopes: string[] }) => Promise<void>;
    deleteApp: (appId: string) => Promise<void>;
    savePolicy: (app: PartnerApp, allowedDestinations: string[]) => Promise<void>;
    saveAppName: (app: PartnerApp, name: string) => Promise<void>;
    issueKey: (app: PartnerApp) => Promise<void>;
    rotateKey: (keyId: string) => Promise<void>;
    revealKey: (keyId: string, app: Pick<PartnerApp, 'id' | 'agent_slug'>) => Promise<ApiKeyReveal>;
    hasEphemeralSecret: (keyId: string) => boolean;
    revokeKey: (keyId: string) => Promise<void>;
    deleteRevokedKey: (keyId: string) => Promise<void>;
    revokeKeys: (keyIds: string[]) => Promise<{ failedKeyIds: string[] }>;
    deleteRevokedKeys: (keyIds: string[]) => Promise<{ failedKeyIds: string[] }>;
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
    const [ephemeralSecrets, setEphemeralSecrets] = useState<Record<string, { secret: string; appId: string }>>({});
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
            const listedKeys = new Map(
                entries.flatMap(([appId, rows]) => rows.map((key) => [key.id, { appId, key }] as const)),
            );
            setEphemeralSecrets((current) => Object.fromEntries(
                Object.entries(current).filter(([keyId, entry]) => {
                    const listed = listedKeys.get(keyId);
                    if (!listed || listed.appId !== entry.appId || listed.key.revoked_at) return false;
                    return !listed.key.expires_at || Date.parse(listed.key.expires_at) > Date.now();
                }),
            ));
            setError(null);
        } catch (err) {
            setError(apiErrorMessage(err));
        } finally {
            refreshing.current = false;
            setLoading(false);
        }
    }, [organizationId]);

    useEffect(() => {
        // Do not retain a plaintext fallback across logout or organization changes.
        setEphemeralSecrets({});
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

    const runKeyBatch = useCallback(
        async (
            keyIds: string[],
            action: (keyId: string) => Promise<unknown>,
            verb: 'revoked' | 'deleted',
        ): Promise<{ failedKeyIds: string[] }> => {
            if (keyIds.length === 0) return { failedKeyIds: [] };

            const results = await Promise.allSettled(keyIds.map(action));
            await refresh();

            const failedKeyIds: string[] = [];
            const failureReasons: unknown[] = [];
            results.forEach((result, index) => {
                if (result.status !== 'rejected') return;
                const keyId = keyIds[index];
                if (keyId !== undefined) failedKeyIds.push(keyId);
                failureReasons.push(result.reason);
            });

            if (failureReasons.length) {
                const succeededCount = keyIds.length - failureReasons.length;
                toast.error(
                    `${failureReasons.length} API key${failureReasons.length === 1 ? '' : 's'} could not be ${verb}.`,
                    {
                        description: `${succeededCount} succeeded. ${apiErrorMessage(failureReasons[0])}`,
                    },
                );
            } else {
                toast.success(`${keyIds.length} API key${keyIds.length === 1 ? '' : 's'} ${verb}.`);
            }
            return { failedKeyIds };
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
                setEphemeralSecrets((current) => Object.fromEntries(
                    Object.entries(current).filter(([, entry]) => entry.appId !== appId),
                ));
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

    const saveAppName: GatewayData['saveAppName'] = useCallback(
        (app, name) =>
            run(async () => {
                const trimmedName = name.trim();
                if (trimmedName.length < 1 || trimmedName.length > 120) {
                    throw new Error('Partner app name must be between 1 and 120 characters.');
                }
                await api.patch(`/partner-apps/${app.id}`, { name: trimmedName });
            }, 'Partner app name saved.'),
        [run],
    );

    const issueKey: GatewayData['issueKey'] = useCallback(
        (app) =>
            run(async () => {
                const response = await api.post<{ id: string; key?: string; partner_app_id?: string }>(`/partner-apps/${app.id}/api-keys`, {
                    name: `${app.agent_slug}-key`,
                    scopes: app.scopes,
                });
                if (response.data.key) {
                    setEphemeralSecrets((current) => ({
                        ...current,
                        [response.data.id]: { secret: response.data.key ?? '', appId: response.data.partner_app_id ?? app.id },
                    }));
                }
            }, 'API key issued. Use Copy config on the new key.'),
        [run],
    );

    const rotateKey: GatewayData['rotateKey'] = useCallback(
        (keyId) =>
            run(async () => {
                const response = await api.post<{ id: string; key?: string; partner_app_id?: string; replaces?: string }>(`/api-keys/${keyId}/rotate`);
                const secret = response.data.key;
                const appId = response.data.partner_app_id;
                setEphemeralSecrets((current) => {
                    const next = { ...current };
                    delete next[keyId];
                    if (response.data.replaces) delete next[response.data.replaces];
                    if (secret && appId) next[response.data.id] = { secret, appId };
                    return next;
                });
            }, 'API key rotated. Use Copy config on the replacement key.'),
        [run],
    );

    const revealKey: GatewayData['revealKey'] = useCallback(async (keyId, app) => {
        try {
            const response = await api.post<ApiKeyReveal>(`/api-keys/${keyId}/reveal`);
            return response.data;
        } catch (err) {
            const details = describeApiError(err);
            const fallback = ephemeralSecrets[keyId];
            if (
                details.status === 409
                && details.detail === 'API key secret is unavailable'
                && fallback?.appId === app.id
            ) {
                return { key: fallback.secret, partner_app_id: fallback.appId, agent_slug: app.agent_slug };
            }
            toast.error('Unable to copy configuration', { description: apiErrorMessage(err) });
            throw err;
        }
    }, [ephemeralSecrets]);

    const hasEphemeralSecret: GatewayData['hasEphemeralSecret'] = useCallback(
        (keyId) => Boolean(ephemeralSecrets[keyId]),
        [ephemeralSecrets],
    );

    const revokeKey: GatewayData['revokeKey'] = useCallback(
        (keyId) =>
            run(async () => {
                await api.delete(`/api-keys/${keyId}`);
                setEphemeralSecrets((current) => {
                    const next = { ...current };
                    delete next[keyId];
                    return next;
                });
            }, 'API key revoked. New realtime sessions are blocked.'),
        [run],
    );
    const deleteRevokedKey: GatewayData['deleteRevokedKey'] = useCallback(
        (keyId) =>
            run(async () => {
                await api.delete(`/api-keys/${keyId}/purge`);
                setEphemeralSecrets((current) => {
                    const next = { ...current };
                    delete next[keyId];
                    return next;
                });
            }, 'Revoked API key deleted permanently.'),
        [run],
    );

    const revokeKeys: GatewayData['revokeKeys'] = useCallback(
        async (keyIds) => {
            const result = await runKeyBatch(keyIds, (keyId) => api.delete(`/api-keys/${keyId}`), 'revoked');
            setEphemeralSecrets((current) => {
                const next = { ...current };
                keyIds.filter((keyId) => !result.failedKeyIds.includes(keyId)).forEach((keyId) => delete next[keyId]);
                return next;
            });
            return result;
        },
        [runKeyBatch],
    );

    const deleteRevokedKeys: GatewayData['deleteRevokedKeys'] = useCallback(
        async (keyIds) => {
            const result = await runKeyBatch(keyIds, (keyId) => api.delete(`/api-keys/${keyId}/purge`), 'deleted');
            setEphemeralSecrets((current) => {
                const next = { ...current };
                keyIds.filter((keyId) => !result.failedKeyIds.includes(keyId)).forEach((keyId) => delete next[keyId]);
                return next;
            });
            return result;
        },
        [runKeyBatch],
    );

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
                refresh,
                createApp,
                deleteApp,
                savePolicy,
                saveAppName,
                issueKey,
                rotateKey,
                revealKey,
                hasEphemeralSecret,
                revokeKey,
                deleteRevokedKey,
                revokeKeys,
                deleteRevokedKeys,
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
