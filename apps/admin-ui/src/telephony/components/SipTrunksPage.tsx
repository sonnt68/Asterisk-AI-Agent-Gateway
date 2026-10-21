import { useState } from 'react';
import { Cable, Edit3, Plus, Power, RefreshCw } from 'lucide-react';

import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import { useTelephonyManagement } from '../hooks/useTelephonyManagement';
import Button from '../../components/ui/Button';
import { DataTable } from '../../components/ui/DataTable';
import { EmptyState } from '../../components/ui/EmptyState';
import ErrorPanel from '../../components/ui/ErrorPanel';
import { Modal } from '../../components/ui/Modal';
import { PageLoader } from '../../components/ui/LoadingSpinner';
import PageHeader from '../../components/ui/PageHeader';
import { StatusPill } from '../../components/ui/StatusPill';
import { apiErrorMessage } from '../../utils/apiErrors';
import type { SipTrunk, SipTrunkInput, SipTrunkPatch } from '../types';
import { isSupportedTrunkAuthentication, isSupportedTrunkRegistration } from '../types';
import TelephonyReadiness from './TelephonyReadiness';
import TrunkForm from './TrunkForm';

const SipTrunksPage = () => {
    const { confirm } = useConfirmDialog();
    const {
        provisioning,
        trunks,
        loading,
        error,
        pendingApply,
        refresh,
        saveTrunk,
        applyConfiguration,
    } = useTelephonyManagement('trunks');
    const [editingTrunk, setEditingTrunk] = useState<SipTrunk | undefined>();
    const [modalOpen, setModalOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [actionError, setActionError] = useState<string | null>(null);
    const managementReady = Boolean(provisioning?.can_manage && provisioning.configured && provisioning.connected);

    const openCreate = () => {
        setEditingTrunk(undefined);
        setActionError(null);
        setModalOpen(true);
    };

    const openEdit = (trunk: SipTrunk) => {
        setEditingTrunk(trunk);
        setActionError(null);
        setModalOpen(true);
    };

    const closeModal = () => {
        if (saving) return;
        setModalOpen(false);
        setEditingTrunk(undefined);
    };

    const submit = async (input: SipTrunkInput | SipTrunkPatch) => {
        setSaving(true);
        setActionError(null);
        try {
            await saveTrunk(input, editingTrunk?.id);
            setModalOpen(false);
            setEditingTrunk(undefined);
        } catch (err) {
            setActionError(apiErrorMessage(err));
        } finally {
            setSaving(false);
        }
    };

    const toggle = async (trunk: SipTrunk) => {
        if (!isSupportedTrunkAuthentication(trunk.authentication) || !isSupportedTrunkRegistration(trunk.registration)) {
            openEdit(trunk);
            return;
        }
        const nextEnabled = !trunk.enabled;
        const confirmed = await confirm({
            title: `${nextEnabled ? 'Enable' : 'Disable'} ${trunk.name}?`,
            description: nextEnabled
                ? 'This enables the saved SIP trunk for future calls after the pending configuration is applied.'
                : 'This disables the SIP trunk for new calls after the pending configuration is applied. Existing calls continue.',
            confirmText: nextEnabled ? 'Enable trunk' : 'Disable trunk',
            variant: nextEnabled ? 'default' : 'destructive',
        });
        if (!confirmed) return;
        try {
            await saveTrunk({ enabled: nextEnabled }, trunk.id);
        } catch {
            // The data hook has already surfaced the request error.
        }
    };

    if (loading && !provisioning) return <PageLoader message="Loading SIP trunk management…" />;

    return (
        <div>
            <PageHeader
                title="SIP Trunks"
                description="Manage the safe SIP account configuration used by the deployment-bound FreePBX instance."
                actions={
                    provisioning?.can_manage ? (
                        <div className="flex flex-wrap gap-2">
                            <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading}>
                                <RefreshCw className="h-3.5 w-3.5" />
                                Refresh
                            </Button>
                            <Button size="sm" onClick={openCreate} disabled={!managementReady} title={!managementReady ? 'The management bridge is unavailable' : undefined}>
                                <Plus className="h-3.5 w-3.5" />
                                Add SIP trunk
                            </Button>
                        </div>
                    ) : undefined
                }
            />

            <TelephonyReadiness
                provisioning={provisioning}
                pendingApply={pendingApply}
                loading={loading}
                error={error}
                onApply={applyConfiguration}
                onRefresh={refresh}
            />

            {provisioning?.can_manage && !error && (
                <DataTable
                    rows={trunks}
                    rowKey={(row) => row.id}
                    empty={
                        <EmptyState
                            icon={Cable}
                            title="No SIP trunks"
                            description="Add a trunk to save the provider host, authentication, and optional routing details."
                            action={<Button onClick={openCreate} disabled={!managementReady}><Plus className="h-4 w-4" />Add SIP trunk</Button>}
                        />
                    }
                    columns={[
                        {
                            header: 'Trunk',
                            cell: (row) => (
                                <div className="min-w-[10rem]">
                                    <div className="flex items-center gap-2 font-medium">
                                        {row.name}
                                        <StatusPill tone={row.enabled ? 'success' : 'neutral'}>{row.enabled ? 'Enabled' : 'Disabled'}</StatusPill>
                                    </div>
                                    <p className="mt-1 text-xs text-muted-foreground">{row.host}:{row.port}</p>
                                </div>
                            ),
                        },
                        { header: 'Transport', cell: (row) => <span className="text-sm">{row.transport || '—'}</span> },
                        {
                            header: 'Authentication',
                            cell: (row) => (
                                <div className="text-sm">
                                    <div>
                                        {row.authentication === 'outbound'
                                            ? 'Username and password'
                                            : row.authentication === 'none'
                                                ? 'None'
                                                : `Native: ${row.authentication}`}
                                    </div>
                                    <div className="text-xs text-muted-foreground">
                                        {row.registration === 'send'
                                            ? 'Sends registration'
                                            : row.registration === 'none'
                                                ? 'No registration'
                                                : `Native: ${row.registration}`}
                                    </div>
                                    {(!isSupportedTrunkAuthentication(row.authentication) || !isSupportedTrunkRegistration(row.registration)) && (
                                        <div className="mt-1 text-xs text-yellow-700 dark:text-yellow-300">Inventory only: native mode; edit and enable/disable are blocked</div>
                                    )}
                                </div>
                            ),
                        },
                        {
                            header: 'Match rules',
                            cell: (row) => {
                                const matchCount = row.match.split(',').map((item) => item.trim()).filter(Boolean).length;
                                return <span className="text-sm text-muted-foreground">{matchCount ? `${matchCount} IP/CIDR value${matchCount === 1 ? '' : 's'}` : 'None'}</span>;
                            },
                        },
                        {
                            header: 'Actions',
                            className: 'whitespace-nowrap',
                            cell: (row) => (
                                <div className="flex items-center gap-1">
                                    <Button variant="ghost" size="sm" onClick={() => openEdit(row)} aria-label={`Edit ${row.name}`}>
                                        <Edit3 className="h-3.5 w-3.5" />
                                        Edit
                                    </Button>
                                    <Button
                                        variant="ghost"
                                        size="sm"
                                        onClick={() => void toggle(row)}
                                        disabled={!isSupportedTrunkAuthentication(row.authentication) || !isSupportedTrunkRegistration(row.registration)}
                                        title={!isSupportedTrunkAuthentication(row.authentication) || !isSupportedTrunkRegistration(row.registration) ? 'Native mode is inventory-only; enable/disable is blocked' : undefined}
                                        aria-label={`${row.enabled ? 'Disable' : 'Enable'} ${row.name}`}
                                    >
                                        <Power className="h-3.5 w-3.5" />
                                        {row.enabled ? 'Disable' : 'Enable'}
                                    </Button>
                                </div>
                            ),
                        },
                    ]}
                />
            )}

            <Modal isOpen={modalOpen} onClose={closeModal} title={editingTrunk ? 'Edit SIP trunk' : 'Add SIP trunk'} size="xl">
                {actionError && <ErrorPanel type="error" message={actionError} className="mb-4" />}
                <TrunkForm
                    trunk={editingTrunk}
                    transports={provisioning?.transports ?? []}
                    saving={saving}
                    onCancel={closeModal}
                    onSubmit={submit}
                />
            </Modal>
        </div>
    );
};

export default SipTrunksPage;
