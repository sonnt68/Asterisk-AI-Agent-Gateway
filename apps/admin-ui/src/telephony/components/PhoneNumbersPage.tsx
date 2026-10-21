import { useEffect, useMemo, useRef, useState } from 'react';
import { Plus, RefreshCw } from 'lucide-react';

import { useConfirmDialog } from '../../hooks/useConfirmDialog';
import { useGatewayData } from '../../hooks/useGatewayData';
import { useTelephonyManagement } from '../hooks/useTelephonyManagement';
import Button from '../../components/ui/Button';
import ErrorPanel from '../../components/ui/ErrorPanel';
import { Modal } from '../../components/ui/Modal';
import { PageLoader } from '../../components/ui/LoadingSpinner';
import PageHeader from '../../components/ui/PageHeader';
import type { PhoneNumber, PhoneNumberInput } from '../types';
import PhoneNumberForm from './PhoneNumberForm';
import PhoneNumberTable from './PhoneNumberTable';
import TelephonyReadiness from './TelephonyReadiness';

const PhoneNumbersPage = () => {
    const { confirm } = useConfirmDialog();
    const { apps, connections, loading: gatewayLoading } = useGatewayData();
    const {
        provisioning,
        trunks,
        phoneNumbers,
        loading,
        error,
        pendingApply,
        refresh,
        savePhoneNumber,
        applyConfiguration,
    } = useTelephonyManagement('all');
    const enabledApps = apps.filter((app) => app.enabled);
    const appSignature = useMemo(
        () => apps
            .map((app) => `${app.id}:${app.name}:${app.agent_slug}:${app.enabled}`)
            .sort()
            .join('|'),
        [apps],
    );
    const previousAppSignature = useRef<string | null>(null);
    const [editingNumber, setEditingNumber] = useState<PhoneNumber | undefined>();
    const [modalOpen, setModalOpen] = useState(false);
    const [saving, setSaving] = useState(false);
    const [actionError, setActionError] = useState<string | null>(null);
    const managementReady = Boolean(provisioning?.can_manage && provisioning.configured && provisioning.connected);

    useEffect(() => {
        if (gatewayLoading) return;
        if (previousAppSignature.current === null) {
            previousAppSignature.current = appSignature;
            return;
        }
        if (previousAppSignature.current === appSignature) return;
        previousAppSignature.current = appSignature;
        void refresh();
    }, [appSignature, gatewayLoading, refresh]);

    const openCreate = () => {
        setEditingNumber(undefined);
        setActionError(null);
        setModalOpen(true);
    };

    const openEdit = (phoneNumber: PhoneNumber) => {
        setEditingNumber(phoneNumber);
        setActionError(null);
        setModalOpen(true);
    };

    const closeModal = () => {
        if (saving) return;
        setModalOpen(false);
        setEditingNumber(undefined);
    };

    const submit = async (input: PhoneNumberInput) => {
        setSaving(true);
        setActionError(null);
        try {
            if (editingNumber) {
                await savePhoneNumber(
                    {
                        label: input.label,
                        partner_app_id: input.partner_app_id,
                        outbound_partner_app_ids: input.outbound_partner_app_ids ?? [],
                        enabled: input.enabled,
                    },
                    editingNumber.id,
                );
            } else {
                await savePhoneNumber(input);
            }
            setModalOpen(false);
            setEditingNumber(undefined);
        } catch (err) {
            setActionError(err instanceof Error ? err.message : 'Unable to save phone number.');
        } finally {
            setSaving(false);
        }
    };

    const toggle = async (phoneNumber: PhoneNumber) => {
        const nextEnabled = !phoneNumber.enabled;
        const confirmed = await confirm({
            title: `${nextEnabled ? 'Enable' : 'Disable'} ${phoneNumber.number}?`,
            description: nextEnabled
                ? 'This enables the number for new inbound and outbound calls immediately. Existing calls continue.'
                : 'This blocks new inbound and outbound calls immediately. Existing calls continue.',
            confirmText: nextEnabled ? 'Enable number' : 'Disable number',
            variant: nextEnabled ? 'default' : 'destructive',
        });
        if (!confirmed) return;
        try {
            await savePhoneNumber({ label: phoneNumber.label ?? '', partner_app_id: phoneNumber.partner_app_id, enabled: nextEnabled }, phoneNumber.id);
        } catch {
            // The data hook has already surfaced the request error.
        }
    };

    if (loading && !provisioning) return <PageLoader message="Loading phone number management…" />;

    return (
        <div>
            <PageHeader
                title="Call Routing"
                description="Route each exact number to one inbound Partner App and optionally share it with multiple outbound Partner Apps."
                actions={
                    provisioning?.can_manage ? (
                        <div className="flex flex-wrap gap-2">
                            <Button variant="outline" size="sm" onClick={() => void refresh()} disabled={loading}>
                                <RefreshCw className="h-3.5 w-3.5" />
                                Refresh
                            </Button>
                            <Button
                                size="sm"
                                onClick={openCreate}
                                disabled={!enabledApps.length || !managementReady}
                                title={!enabledApps.length ? 'Create an enabled Partner App first' : !managementReady ? 'The management bridge is unavailable' : undefined}
                            >
                                <Plus className="h-3.5 w-3.5" />
                                Add phone number
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
                <>
                    {!gatewayLoading && !enabledApps.length && (
                        <div className="mb-4 rounded-md border border-yellow-500/30 bg-yellow-500/10 p-3 text-sm text-yellow-700 dark:text-yellow-300" role="status">
                            Create and enable a Partner App before assigning an inbound route. Existing routes remain visible so disabled mappings can be recovered.
                        </div>
                    )}
                    <div className="mb-4 rounded-md border border-border bg-muted/20 p-3 text-sm text-muted-foreground" role="note">
                        Each number has one inbound Partner App. Outbound assignments may be shared across apps; one assigned enabled number can be selected automatically, while multiple enabled numbers require an exact <code>caller_number</code>. Apply configuration publishes new inbound routes to FreePBX and does not prove PSTN or carrier service.
                    </div>
                    <PhoneNumberTable
                        phoneNumbers={phoneNumbers}
                        apps={apps}
                        connections={connections}
                        canCreate={Boolean(enabledApps.length && managementReady)}
                        onCreate={openCreate}
                        onEdit={openEdit}
                        onToggle={(phoneNumber) => void toggle(phoneNumber)}
                    />
                </>
            )}

            <Modal isOpen={modalOpen} onClose={closeModal} title={editingNumber ? 'Edit call routing' : 'Add call routing'} size="md">
                {actionError && <ErrorPanel type="error" message={actionError} className="mb-4" />}
                <PhoneNumberForm
                    phoneNumber={editingNumber}
                    trunks={trunks}
                    phoneNumbers={phoneNumbers}
                    apps={apps}
                    saving={saving}
                    onCancel={closeModal}
                    onSubmit={submit}
                />
            </Modal>
        </div>
    );
};

export default PhoneNumbersPage;
