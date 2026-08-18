export type PartnerApp = {
    id: string;
    name: string;
    agent_slug: string;
    enabled: boolean;
    scopes: string[];
    allowed_destinations: string[];
};

export type ApiKey = {
    id: string;
    name: string;
    prefix: string;
    scopes?: string[];
    created_at?: string;
    revoked_at?: string | null;
};

export type Runtime = {
    active_connections: number;
    active_calls: number;
    ari_connected: boolean;
    audiosocket_listening: boolean;
};

export type AuditEvent = {
    id: string;
    action: string;
    target_id?: string | null;
    created_at: string;
};

export type AsteriskConfig = {
    configured: boolean;
    host?: string | null;
    ari_port?: number | null;
    stasis_app?: string;
    media_transport: string;
    audiosocket_port: number;
    audiosocket_advertise_host: string;
    credentials?: string;
    organization_id?: string;
};

export type LiveConnection = {
    id: string;
    partner_app_id?: string;
    agent_slug: string;
    scopes: string[];
};

export type LiveCall = {
    id: string;
    agent_slug: string;
    media_transport: string;
    transfer_consulting: boolean;
};

export type Member = { user_id: string; email: string; role: string };
