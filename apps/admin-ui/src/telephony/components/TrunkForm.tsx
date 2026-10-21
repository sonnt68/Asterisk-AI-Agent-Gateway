import { FormEvent, useEffect, useState } from 'react';

import Button from '../../components/ui/Button';
import { FormInput, FormLabel, FormSelect, FormSwitch } from '../../components/ui/FormComponents';
import type { SipTrunk, SipTrunkInput, SipTrunkPatch } from '../types';
import { isSupportedTrunkAuthentication, isSupportedTrunkRegistration } from '../types';

type TrunkFormProps = {
    trunk?: SipTrunk;
    transports: string[];
    saving: boolean;
    onCancel: () => void;
    onSubmit: (input: SipTrunkInput | SipTrunkPatch) => Promise<void>;
};

type TrunkFormState = {
    name: string;
    host: string;
    port: string;
    transport: string;
    authentication: string;
    registration: string;
    username: string;
    auth_username: string;
    password: string;
    match: string;
    from_domain: string;
    from_user: string;
    contact_user: string;
    outbound_caller_id: string;
    codecs: string;
    enabled: boolean;
};

const splitList = (value: string) =>
    value
        .split(/[\n,]/)
        .map((item) => item.trim())
        .filter(Boolean);

const listValue = (value: string) => splitList(value).join(',');

const initialState = (trunk: SipTrunk | undefined, transports: string[]): TrunkFormState => ({
    name: trunk?.name ?? '',
    host: trunk?.host ?? '',
    port: trunk ? String(trunk.port) : '5060',
    transport: trunk?.transport ?? transports[0] ?? '',
    authentication: trunk?.authentication ?? 'none',
    registration: trunk?.registration ?? 'none',
    username: trunk?.username ?? '',
    auth_username: trunk?.auth_username ?? '',
    password: '',
    match: trunk?.match.replace(/\s*,\s*/g, '\n') ?? '',
    from_domain: trunk?.from_domain ?? '',
    from_user: trunk?.from_user ?? '',
    contact_user: trunk?.contact_user ?? '',
    outbound_caller_id: trunk?.outbound_caller_id ?? '',
    codecs: trunk?.codecs.join(', ') ?? '',
    enabled: trunk?.enabled ?? true,
});

const fieldClass = 'min-h-20 w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2';

const TrunkForm = ({ trunk, transports, saving, onCancel, onSubmit }: TrunkFormProps) => {
    const [form, setForm] = useState(() => initialState(trunk, transports));
    const [validationError, setValidationError] = useState<string | null>(null);

    useEffect(() => {
        setForm(initialState(trunk, transports));
        setValidationError(null);
    }, [trunk, transports]);

    const update = <K extends keyof TrunkFormState>(key: K, value: TrunkFormState[K]) => {
        setForm((current) => ({ ...current, [key]: value }));
    };
    const transportOptions = Array.from(new Set([form.transport, ...transports].filter(Boolean)));
    const pageUsesHttp = typeof window !== 'undefined' && window.location.protocol === 'http:';

    const submit = async (event: FormEvent) => {
        event.preventDefault();
        setValidationError(null);
        const port = Number(form.port);
        if (!form.name.trim() || !form.host.trim() || !form.transport) {
            setValidationError('Name, host, and transport are required.');
            return;
        }
        if (!Number.isInteger(port) || port < 1 || port > 65535) {
            setValidationError('Port must be a whole number between 1 and 65535.');
            return;
        }
        if (form.authentication === 'outbound' && !form.username.trim()) {
            setValidationError('Username is required when outbound authentication is enabled.');
            return;
        }
        if (form.authentication === 'outbound' && !trunk && !form.password) {
            setValidationError('Enter a password when creating an authenticated trunk.');
            return;
        }
        if (!trunk && form.authentication === 'none' && splitList(form.match).length === 0) {
            setValidationError('Add at least one Match IP/CIDR value when using IP authentication.');
            return;
        }
        if (!isSupportedTrunkAuthentication(form.authentication) || !isSupportedTrunkRegistration(form.registration)) {
            setValidationError('This trunk uses a native mode outside the supported editor. Close this form without saving.');
            return;
        }

        const payload: SipTrunkInput = {
            name: form.name.trim(),
            host: form.host.trim(),
            port,
            transport: form.transport,
            authentication: form.authentication,
            registration: form.registration,
            username: form.username.trim(),
            auth_username: form.auth_username.trim(),
            match: listValue(form.match),
            from_domain: form.from_domain.trim(),
            from_user: form.from_user.trim(),
            contact_user: form.contact_user.trim(),
            outbound_caller_id: form.outbound_caller_id.trim(),
            codecs: splitList(form.codecs),
            enabled: form.enabled,
        };
        // An empty edit password is deliberately omitted so the stored secret
        // remains unchanged. It is never copied into the form from the API.
        if (form.password.length > 0) payload.password = form.password;
        if (!trunk) {
            await onSubmit(payload);
            return;
        }

        const original = initialState(trunk, transports);
        const patch: SipTrunkPatch = {};
        if (payload.name !== original.name) patch.name = payload.name;
        if (payload.host !== original.host) patch.host = payload.host;
        if (payload.port !== Number(original.port)) patch.port = payload.port;
        if (payload.transport !== original.transport) patch.transport = payload.transport;
        if (payload.authentication !== original.authentication) patch.authentication = payload.authentication;
        if (payload.registration !== original.registration) patch.registration = payload.registration;
        if (payload.username !== original.username) patch.username = payload.username;
        if (payload.auth_username !== original.auth_username) patch.auth_username = payload.auth_username;
        if (payload.match !== listValue(original.match)) patch.match = payload.match;
        if (payload.from_domain !== original.from_domain.trim()) patch.from_domain = payload.from_domain;
        if (payload.from_user !== original.from_user.trim()) patch.from_user = payload.from_user;
        if (payload.contact_user !== original.contact_user.trim()) patch.contact_user = payload.contact_user;
        if (payload.outbound_caller_id !== original.outbound_caller_id.trim()) patch.outbound_caller_id = payload.outbound_caller_id;
        if (JSON.stringify(payload.codecs) !== JSON.stringify(splitList(original.codecs))) patch.codecs = payload.codecs;
        if (payload.enabled !== original.enabled) patch.enabled = payload.enabled;
        if (payload.password !== undefined) patch.password = payload.password;
        await onSubmit(patch);
    };

    const unsupportedAuthentication = Boolean(trunk && !isSupportedTrunkAuthentication(trunk.authentication));
    const unsupportedRegistration = Boolean(trunk && !isSupportedTrunkRegistration(trunk.registration));

    if (unsupportedAuthentication || unsupportedRegistration) {
        return (
            <div className="space-y-4">
                <div className="rounded-md border border-yellow-500/40 bg-yellow-500/10 p-4 text-sm" role="alert">
                    <h3 className="font-semibold text-yellow-800 dark:text-yellow-200">Editing is unavailable for this trunk</h3>
                    <p className="mt-1 text-yellow-700 dark:text-yellow-300">
                        This trunk uses a native FreePBX mode outside the supported common configuration editor. The current mode is preserved; editing is blocked so saving cannot silently reset it.
                    </p>
                    <p className="mt-2 font-mono text-xs text-yellow-800 dark:text-yellow-200">
                        authentication={trunk?.authentication} · registration={trunk?.registration}
                    </p>
                </div>
                <div className="flex justify-end">
                    <Button variant="outline" onClick={onCancel}>Close</Button>
                </div>
            </div>
        );
    }

    return (
        <form onSubmit={submit} noValidate>
            {validationError && <p className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{validationError}</p>}
            {pageUsesHttp && (
                <p className="mb-4 rounded-md border border-yellow-500/30 bg-yellow-500/10 p-3 text-xs text-yellow-700 dark:text-yellow-300">
                    Enter SIP passwords only over HTTPS or a trusted local SSH tunnel. This page is currently served over HTTP; the Gateway does not claim TLS is configured.
                </p>
            )}

            <div className="grid gap-x-4 md:grid-cols-2">
                <FormInput label="Name" value={form.name} onChange={(event) => update('name', event.target.value)} required autoComplete="off" />
                <FormInput label="Host" value={form.host} onChange={(event) => update('host', event.target.value)} required autoComplete="off" />
                <FormInput label="Port" type="number" min={1} max={65535} step={1} value={form.port} onChange={(event) => update('port', event.target.value)} required />
                <FormSelect
                    label="SIP transport"
                    value={form.transport}
                    onChange={(event) => update('transport', event.target.value)}
                    options={transportOptions.length ? transportOptions.map((value) => ({ value, label: value })) : [{ value: '', label: 'No transport available' }]}
                    required
                    disabled={!transportOptions.length}
                />
                <FormSelect
                    label="Outbound authentication"
                    value={form.authentication}
                    onChange={(event) => update('authentication', event.target.value as SipTrunk['authentication'])}
                    options={[{ value: 'none', label: 'None' }, { value: 'outbound', label: 'Username and password' }]}
                />
                <FormSelect
                    label="Registration"
                    value={form.registration}
                    onChange={(event) => update('registration', event.target.value as SipTrunk['registration'])}
                    options={[{ value: 'none', label: 'None' }, { value: 'send', label: 'Send registration' }]}
                />
                <FormInput label="Username" value={form.username} onChange={(event) => update('username', event.target.value)} autoComplete="off" />
                <FormInput label="Auth username" value={form.auth_username} onChange={(event) => update('auth_username', event.target.value)} autoComplete="off" />
                <FormInput
                    label={trunk?.password_set ? 'Password (leave blank to keep current)' : 'Password'}
                    type="password"
                    value={form.password}
                    onChange={(event) => update('password', event.target.value)}
                    autoComplete="new-password"
                    required={Boolean(!trunk && form.authentication === 'outbound')}
                />
            </div>

            <details className="mb-4 rounded-md border border-border/70 p-4">
                <summary className="cursor-pointer text-sm font-semibold">Advanced SIP options</summary>
                <div className="mt-4 grid gap-x-4 md:grid-cols-2">
                    <div className="mb-4 md:col-span-2">
                        <FormLabel htmlFor="trunk-match" tooltip={form.authentication === 'none' ? 'At least one source IP or CIDR is required when using IP authentication.' : 'Optional source IP or CIDR values used to match inbound traffic.'}>
                            {form.authentication === 'none' && !trunk ? 'Match IP/CIDR values (required for IP authentication)' : 'Match IP/CIDR values'}
                        </FormLabel>
                        <textarea id="trunk-match" className={fieldClass} value={form.match} onChange={(event) => update('match', event.target.value)} placeholder="One IP or CIDR per line" rows={3} required={!trunk && form.authentication === 'none'} />
                    </div>
                    <FormInput label="From domain" value={form.from_domain} onChange={(event) => update('from_domain', event.target.value)} autoComplete="off" />
                    <FormInput label="From user" value={form.from_user} onChange={(event) => update('from_user', event.target.value)} autoComplete="off" />
                    <FormInput label="Contact user" value={form.contact_user} onChange={(event) => update('contact_user', event.target.value)} autoComplete="off" />
                    <FormInput label="Outbound caller ID" value={form.outbound_caller_id} onChange={(event) => update('outbound_caller_id', event.target.value)} autoComplete="off" />
                    <div className="mb-4 md:col-span-2">
                        <FormLabel htmlFor="trunk-codecs" tooltip="Optional codec preference list sent to the PBX.">Codecs</FormLabel>
                        <textarea id="trunk-codecs" className={fieldClass} value={form.codecs} onChange={(event) => update('codecs', event.target.value)} placeholder="alaw, ulaw" rows={2} />
                    </div>
                </div>
            </details>

            <FormSwitch label="Enabled" description="Disabled trunks remain saved and can be enabled later." checked={form.enabled} onChange={(event) => update('enabled', event.target.checked)} />
            <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={onCancel} disabled={saving}>Cancel</Button>
                <Button type="submit" disabled={saving || !transportOptions.length}>{saving ? 'Saving…' : trunk ? 'Save trunk' : 'Create trunk'}</Button>
            </div>
        </form>
    );
};

export default TrunkForm;
