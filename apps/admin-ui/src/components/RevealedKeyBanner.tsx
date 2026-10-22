import { useState } from 'react';
import { Check, Copy } from 'lucide-react';
import { toast } from 'sonner';

import type { ApiKey, ApiKeyReveal, PartnerApp } from '../lib/types';
import Button from './ui/Button';

type Props = {
    app?: PartnerApp;
    apiKey?: ApiKey;
    onReveal?: (keyId: string, app: Pick<PartnerApp, 'id' | 'agent_slug'>) => Promise<ApiKeyReveal>;
    hasEphemeralSecret?: boolean;
    className?: string;
};

const gatewayOrigin = () => {
    const currentOrigin = typeof window === 'undefined' ? '' : window.location.origin;
    const configuredApiUrl = import.meta.env.VITE_GATEWAY_API_URL;
    if (!configuredApiUrl) return currentOrigin;
    try {
        const parsed = new URL(configuredApiUrl, currentOrigin);
        const gatewayPath = parsed.pathname.replace(/\/api\/v1\/?$/, '');
        return `${parsed.origin}${gatewayPath === '/' ? '' : gatewayPath}`;
    } catch {
        return currentOrigin;
    }
};

const copyText = async (value: string): Promise<boolean> => {
    if (typeof navigator !== 'undefined') {
        try {
            if (navigator.clipboard?.writeText) {
                await navigator.clipboard.writeText(value);
                return true;
            }
        } catch {
            // Fall through to the DOM copy path for HTTP deployments or denied permissions.
        }
    }

    if (typeof document === 'undefined' || typeof document.execCommand !== 'function' || !document.body) return false;
    const textarea = document.createElement('textarea');
    textarea.value = value;
    textarea.setAttribute('readonly', '');
    textarea.setAttribute('aria-hidden', 'true');
    textarea.style.position = 'fixed';
    textarea.style.top = '-1000px';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    try {
        textarea.focus();
        textarea.select();
        return document.execCommand('copy');
    } catch {
        return false;
    } finally {
        textarea.remove();
    }
};

const RevealedKeyBanner = ({ app, apiKey, onReveal, hasEphemeralSecret = false, className = '' }: Props) => {
    const [copying, setCopying] = useState(false);
    const [copied, setCopied] = useState(false);

    if (!app || !apiKey || !onReveal || apiKey.revoked_at) return null;

    if (!app.enabled) {
        return (
            <span className={`text-xs text-muted-foreground ${className}`}>
                Copy unavailable while this Partner App is disabled.
            </span>
        );
    }

    const expired = Boolean(apiKey.expires_at && Date.parse(apiKey.expires_at) <= Date.now());
    if (expired || (!apiKey.copy_available && !hasEphemeralSecret)) {
        return (
            <span className={`text-xs text-muted-foreground ${className}`}>
                {expired ? 'Expired key. Issue a new key to create a copyable configuration.' : 'Copy unavailable. Create or rotate a key to enable copying.'}
            </span>
        );
    }

    const copyConfiguration = async () => {
        if (copying) return;
        setCopying(true);
        setCopied(false);
        try {
            const revealed = await onReveal(apiKey.id, app);
            if (revealed.partner_app_id !== app.id) {
                toast.error('Unable to copy configuration', { description: 'The key is assigned to a different Partner App.' });
                return;
            }
            const configuration = [
                `GATEWAY_URL=${gatewayOrigin()}`,
                `GATEWAY_API_KEY=${revealed.key}`,
                `AGENT_SLUG=${revealed.agent_slug}`,
            ].join('\n');
            if (!await copyText(configuration)) {
                toast.error('Unable to copy configuration', { description: 'Copy the configuration manually from a trusted environment.' });
                return;
            }
            setCopied(true);
            toast.success('Configuration copied.');
        } catch {
            // The data layer already surfaced the request failure.
        } finally {
            setCopying(false);
        }
    };

    return (
        <span className={`inline-flex ${className}`}>
            <Button
                size="sm"
                variant="outline"
                className="whitespace-nowrap"
                onClick={() => void copyConfiguration()}
                disabled={copying}
                aria-busy={copying}
                title="Copy GATEWAY_URL, GATEWAY_API_KEY, and AGENT_SLUG"
            >
                {copied ? <Check className="h-3 w-3" /> : <Copy className="h-3 w-3" />}
                {copying ? 'Copying…' : copied ? 'Copied' : 'Copy config'}
            </Button>
        </span>
    );
};

export default RevealedKeyBanner;
