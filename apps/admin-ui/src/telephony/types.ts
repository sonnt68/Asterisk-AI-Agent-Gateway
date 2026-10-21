export type TrunkAuthentication = 'none' | 'outbound';
export type TrunkRegistration = 'none' | 'send';

export const isSupportedTrunkAuthentication = (value: string): value is TrunkAuthentication =>
    value === 'none' || value === 'outbound';

export const isSupportedTrunkRegistration = (value: string): value is TrunkRegistration =>
    value === 'none' || value === 'send';

export type ProvisioningStatus = {
    configured: boolean;
    can_manage: boolean;
    connected: boolean;
    needs_apply: boolean;
    transports: string[];
    error?: string;
};

export type SipTrunk = {
    id: string;
    name: string;
    host: string;
    port: number;
    transport: string;
    authentication: string;
    registration: string;
    username: string;
    auth_username: string;
    password_set: boolean;
    match: string;
    from_domain?: string | null;
    from_user?: string | null;
    contact_user?: string | null;
    outbound_caller_id?: string | null;
    codecs: string[];
    enabled: boolean;
};

export type SipTrunkInput = {
    name: string;
    host: string;
    port: number;
    transport: string;
    authentication: TrunkAuthentication;
    registration: TrunkRegistration;
    username: string;
    auth_username: string;
    password?: string;
    match: string;
    from_domain?: string;
    from_user?: string;
    contact_user?: string;
    outbound_caller_id?: string;
    codecs: string[];
    enabled: boolean;
};

export type SipTrunkPatch = Partial<SipTrunkInput>;

export type PhoneNumber = {
    id: string;
    number: string;
    label?: string | null;
    partner_app_id: string;
    partner_app_name: string;
    agent_slug: string;
    outbound_partner_app_ids: string[];
    outbound_partner_apps: PhoneNumberOutboundApp[];
    enabled: boolean;
    pbx_applied: boolean;
    created_at: string;
    updated_at: string;
};

export type PhoneNumberOutboundApp = {
    id: string;
    name: string;
    agent_slug: string;
    enabled: boolean;
};

export type PhoneNumberInput = {
    number: string;
    label: string;
    partner_app_id: string;
    outbound_partner_app_ids?: string[];
    enabled: boolean;
};

export type PhoneNumberPatch = Omit<PhoneNumberInput, 'number'>;

export type ApplyResponse = {
    applied_routes: Array<{ route_id: string; number: string }>;
};

export type TelephonyState = {
    provisioning: ProvisioningStatus | null;
    trunks: SipTrunk[];
    phoneNumbers: PhoneNumber[];
    loading: boolean;
    error: string | null;
    pendingApply: boolean;
};
