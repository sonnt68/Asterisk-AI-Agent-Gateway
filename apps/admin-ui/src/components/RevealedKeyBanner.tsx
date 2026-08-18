import { useState } from 'react';
import { Check, Copy, KeyRound, X } from 'lucide-react';

import { useGatewayData } from '../hooks/useGatewayData';

/**
 * One-time secret display. The control plane hashes API keys, so this is the
 * only moment the plaintext exists in the browser.
 */
export const RevealedKeyBanner = () => {
    const { revealedKey, dismissRevealedKey } = useGatewayData();
    const [copied, setCopied] = useState(false);

    if (!revealedKey) return null;

    const copy = async () => {
        await navigator.clipboard.writeText(revealedKey.value);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="mb-6 rounded-lg border border-yellow-500/50 bg-yellow-500/10 p-4">
            <div className="flex items-start gap-3">
                <KeyRound className="w-5 h-5 text-yellow-600 dark:text-yellow-400 flex-shrink-0 mt-0.5" />
                <div className="flex-1 min-w-0">
                    <h4 className="font-semibold text-yellow-600 dark:text-yellow-400 mb-1">One-time API key</h4>
                    <p className="text-sm text-yellow-600 dark:text-yellow-400">
                        Copy this key now. It is hashed at rest and will never be shown again.
                    </p>
                    <code className="mt-2 block break-all rounded bg-background/60 p-2 text-xs font-mono">
                        {revealedKey.value}
                    </code>
                    <button
                        onClick={copy}
                        className="mt-3 inline-flex items-center gap-2 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90"
                    >
                        {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                        {copied ? 'Copied' : 'Copy key'}
                    </button>
                </div>
                <button
                    onClick={dismissRevealedKey}
                    aria-label="Dismiss"
                    className="text-yellow-600 dark:text-yellow-400 opacity-75 hover:opacity-100"
                >
                    <X className="w-4 h-4" />
                </button>
            </div>
        </div>
    );
};

export default RevealedKeyBanner;
