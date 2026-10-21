import { useState } from 'react';
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, ShieldAlert, UploadCloud } from 'lucide-react';

import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import Button from '../../components/ui/Button';
import { ConfigCard } from '../../components/ui/ConfigCard';
import ErrorPanel from '../../components/ui/ErrorPanel';
import { StatusPill } from '../../components/ui/StatusPill';
import type { ProvisioningStatus } from '../types';
import { apiErrorMessage } from '../../utils/apiErrors';

type TelephonyReadinessProps = {
    provisioning: ProvisioningStatus | null;
    pendingApply: boolean;
    loading: boolean;
    error: string | null;
    onApply: () => Promise<void>;
    onRefresh: () => Promise<void>;
};

const TelephonyReadiness = ({
    provisioning,
    pendingApply,
    loading,
    error,
    onApply,
    onRefresh,
}: TelephonyReadinessProps) => {
    const { confirm } = useConfirmDialog();
    const [applying, setApplying] = useState(false);
    const [refreshing, setRefreshing] = useState(false);
    const [applyError, setApplyError] = useState<string | null>(null);

    const handleApply = async () => {
        const confirmed = await confirm({
            title: 'Apply all pending FreePBX configuration?',
            description:
                'This applies every pending SIP trunk and phone number change, then reloads the managed FreePBX configuration and verifies the result. Active PBX calls may cause the operation to be rejected.',
            confirmText: 'Apply configuration',
        });
        if (!confirmed) return;

        setApplying(true);
        setApplyError(null);
        try {
            await onApply();
        } catch (err) {
            setApplyError(apiErrorMessage(err, '/asterisk/apply'));
        } finally {
            setApplying(false);
        }
    };

    const handleRefresh = async () => {
        setRefreshing(true);
        try {
            await onRefresh();
        } finally {
            setRefreshing(false);
        }
    };

    if (!provisioning) {
        return (
            <div className="mb-6">
                {error ? <ErrorPanel type="error" message={error} /> : <p className="text-sm text-muted-foreground">Loading telephony management status…</p>}
            </div>
        );
    }

    const canManage = provisioning.can_manage;
    const bridgeReachable = provisioning.connected;
    const statusTone = !canManage ? 'warning' : bridgeReachable ? 'success' : 'warning';

    return (
        <ConfigCard className="mb-6">
            <div className="flex flex-wrap items-start justify-between gap-4">
                <div>
                    <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-base font-semibold tracking-tight">Telephony management status</h2>
                        <StatusPill tone={statusTone}>
                            {!canManage ? 'Management unavailable' : bridgeReachable ? 'Management bridge reachable' : 'Management bridge unavailable'}
                        </StatusPill>
                    </div>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {canManage
                            ? 'Saved SIP and DID configuration is managed for the deployment-bound operator organization.'
                            : 'Only an Owner or Admin of the deployment-bound operator organization can manage these settings.'}
                    </p>
                </div>
                <div className="flex flex-wrap gap-2">
                    <Button variant="outline" size="sm" onClick={handleRefresh} disabled={loading || refreshing}>
                        {refreshing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
                        Refresh status
                    </Button>
                    {canManage && pendingApply && (
                        <Button
                            size="sm"
                            onClick={handleApply}
                            disabled={applying || loading || refreshing || !provisioning.configured || !bridgeReachable}
                            title={!provisioning.configured || !bridgeReachable ? 'The management bridge is unavailable' : undefined}
                        >
                            {applying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <UploadCloud className="h-3.5 w-3.5" />}
                            {applying ? 'Applying…' : 'Apply configuration'}
                        </Button>
                    )}
                </div>
            </div>

            {error && <ErrorPanel type="error" message={error} className="mt-4" />}
            {applyError && <ErrorPanel type="error" message={applyError} className="mt-4" />}

            <div className="mt-4 grid gap-3 sm:grid-cols-3">
                <div className="rounded-md border border-border/70 bg-muted/20 p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        {provisioning.configured ? <CheckCircle2 className="h-3.5 w-3.5 text-green-600" /> : <AlertTriangle className="h-3.5 w-3.5 text-yellow-600" />}
                        Management configuration
                    </div>
                    <p className="mt-1 text-sm font-medium">{provisioning.configured ? 'Configured' : 'Not configured'}</p>
                </div>
                <div className="rounded-md border border-border/70 bg-muted/20 p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        {pendingApply ? <UploadCloud className="h-3.5 w-3.5 text-yellow-600" /> : <CheckCircle2 className="h-3.5 w-3.5 text-green-600" />}
                        Saved configuration
                    </div>
                    <p className="mt-1 text-sm font-medium">{pendingApply ? 'Changes waiting to apply' : 'Saved and applied'}</p>
                </div>
                <div className="rounded-md border border-border/70 bg-muted/20 p-3">
                    <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                        <ShieldAlert className="h-3.5 w-3.5 text-muted-foreground" />
                        SIP transports
                    </div>
                    <p className="mt-1 text-sm font-medium">{provisioning.transports.length ? provisioning.transports.join(', ') : 'Unavailable'}</p>
                </div>
            </div>
        </ConfigCard>
    );
};

export default TelephonyReadiness;
