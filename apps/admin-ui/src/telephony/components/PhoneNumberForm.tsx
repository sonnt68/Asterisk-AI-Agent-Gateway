import { FormEvent, useEffect, useMemo, useState } from 'react';
import Button from '../../components/ui/Button';
import { FormInput, FormSelect, FormSwitch } from '../../components/ui/FormComponents';
import type { PartnerApp } from '../../lib/types';
import type { PhoneNumber, PhoneNumberInput, PhoneNumberOutboundApp, SipTrunk } from '../types';
import OutboundAppPicker from './OutboundAppPicker';

type PhoneNumberFormProps = {
    phoneNumber?: PhoneNumber;
    trunks: SipTrunk[];
    phoneNumbers: PhoneNumber[];
    apps: PartnerApp[];
    saving: boolean;
    onCancel: () => void;
    onSubmit: (input: PhoneNumberInput) => Promise<void>;
};

const existingOutboundAssignments = (phoneNumber?: PhoneNumber): PhoneNumberOutboundApp[] => {
    if (!phoneNumber) return [];
    const assignments = Array.isArray(phoneNumber.outbound_partner_apps) ? phoneNumber.outbound_partner_apps : [];
    const ids = phoneNumber.outbound_partner_app_ids ?? assignments.map((app) => app.id);
    const known = new Set(assignments.map((app) => app.id));
    return [
        ...assignments,
        ...ids
            .filter((id) => !known.has(id))
            .map((id) => ({ id, name: 'Unavailable Partner App', agent_slug: id, enabled: false })),
    ];
};

const PhoneNumberForm = ({ phoneNumber, trunks, phoneNumbers, apps, saving, onCancel, onSubmit }: PhoneNumberFormProps) => {
    const assignedNumbers = useMemo(() => new Set(phoneNumbers.map((item) => item.number)), [phoneNumbers]);
    const trunkNumbers = useMemo(() => {
        const numbers = new Map<string, string[]>();
        for (const trunk of trunks) {
            const value = trunk.outbound_caller_id ?? '';
            // Caller ID is only a source for the exact number, not a trunk routing binding.
            if (!/^\+?\d{1,32}$/.test(value) || assignedNumbers.has(value)) continue;
            numbers.set(value, [...(numbers.get(value) ?? []), trunk.name]);
        }
        return numbers;
    }, [assignedNumbers, trunks]);
    const existingAssignments = useMemo(() => existingOutboundAssignments(phoneNumber), [phoneNumber]);
    const existingOutboundIds = useMemo(() => new Set(existingAssignments.map((app) => app.id)), [existingAssignments]);
    const enabledApps = useMemo(() => apps.filter((app) => app.enabled), [apps]);
    const [numberSource, setNumberSource] = useState(trunkNumbers.size ? '' : 'manual');
    const [number, setNumber] = useState(phoneNumber?.number ?? '');
    const [label, setLabel] = useState(phoneNumber?.label ?? '');
    const [inboundAppId, setInboundAppId] = useState(phoneNumber?.partner_app_id ?? '');
    const [outboundAppIds, setOutboundAppIds] = useState<string[]>(Array.from(existingOutboundIds));
    const [enabled, setEnabled] = useState(phoneNumber?.enabled ?? true);
    const [validationError, setValidationError] = useState<string | null>(null);

    useEffect(() => {
        setNumberSource(phoneNumber ? '' : trunkNumbers.size ? '' : 'manual');
        setNumber(phoneNumber?.number ?? '');
        setLabel(phoneNumber?.label ?? '');
        setInboundAppId(phoneNumber?.partner_app_id ?? '');
        setOutboundAppIds(Array.from(existingOutboundAssignments(phoneNumber).map((app) => app.id)));
        setEnabled(phoneNumber?.enabled ?? true);
        setValidationError(null);
    }, [phoneNumber, trunkNumbers.size]);

    const selectNumber = (value: string) => {
        setNumberSource(value);
        setNumber(value === 'manual' ? '' : value);
        const names = trunkNumbers.get(value);
        if (names && !label.trim()) setLabel(names[0].slice(0, 120));
        setValidationError(null);
    };

    const submit = async (event: FormEvent) => {
        event.preventDefault();
        setValidationError(null);
        if (!phoneNumber && !/^\+?\d{1,32}$/.test(number)) {
            setValidationError('Enter an exact phone number with an optional + and 1 to 32 digits.');
            return;
        }
        if (!label.trim()) {
            setValidationError('Label is required.');
            return;
        }
        if (!inboundAppId) {
            setValidationError('Choose an enabled Inbound Partner App.');
            return;
        }
        const inboundAppIsEnabled = enabledApps.some((app) => app.id === inboundAppId);
        const keepsUnavailableInboundMappingDisabled = Boolean(
            phoneNumber &&
            inboundAppId === phoneNumber.partner_app_id &&
            !inboundAppIsEnabled &&
            !enabled,
        );
        if (!inboundAppIsEnabled && !keepsUnavailableInboundMappingDisabled) {
            setValidationError('Choose an enabled Inbound Partner App when saving an enabled number or changing its assignment.');
            return;
        }
        const invalidOutboundApp = outboundAppIds.some(
            (id) => !enabledApps.some((app) => app.id === id) && !existingOutboundIds.has(id),
        );
        if (invalidOutboundApp) {
            setValidationError('New outbound assignments must use enabled Partner Apps. Remove unavailable apps before adding replacements.');
            return;
        }
        await onSubmit({
            number,
            label: label.trim(),
            partner_app_id: inboundAppId,
            outbound_partner_app_ids: outboundAppIds,
            enabled,
        });
    };

    const currentApp = apps.find((app) => app.id === phoneNumber?.partner_app_id);
    const inboundApps = apps.filter((app) => app.enabled || app.id === phoneNumber?.partner_app_id);
    const inboundAppOptions = [
        { value: '', label: enabledApps.length ? 'Choose an enabled Partner App' : 'No enabled Partner Apps available' },
        ...inboundApps.map((app) => ({
            value: app.id,
            label: `${app.name} (${app.agent_slug})${app.enabled ? '' : app.id === phoneNumber?.partner_app_id ? ' — currently unavailable; keep only while disabled' : ' — disabled'}`,
        })),
        ...(phoneNumber && !currentApp
            ? [{ value: phoneNumber.partner_app_id, label: `${phoneNumber.partner_app_name || 'Current Partner App'} (currently unavailable; keep only while disabled)` }]
            : []),
    ];
    const canSaveUnavailableMapping = Boolean(phoneNumber && !enabled && inboundAppId === phoneNumber.partner_app_id);
    const formDisabled = saving || (!enabledApps.length && !canSaveUnavailableMapping);

    return (
        <form onSubmit={submit} noValidate>
            {validationError && <p className="mb-4 rounded-md border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive" role="alert">{validationError}</p>}
            {!phoneNumber && (
                <>
                    <FormSelect
                        label="Phone number"
                        value={numberSource}
                        onChange={(event) => selectNumber(event.target.value)}
                        options={[
                            { value: '', label: 'Choose a number from SIP trunks' },
                            ...Array.from(trunkNumbers, ([value, names]) => ({ value, label: `${value} — ${names.join(', ')}` })),
                            { value: 'manual', label: 'Enter another number manually' },
                        ]}
                        required
                    />
                    <p className="-mt-2 mb-4 text-xs text-muted-foreground">
                        {trunkNumbers.size
                            ? 'Numbers come from SIP trunk Outbound Caller ID. Choose the exact DID your provider sends for incoming calls.'
                            : 'No unassigned numeric Caller IDs found on SIP trunks. Enter the DID supplied by your provider.'}
                    </p>
                </>
            )}
            {(phoneNumber || numberSource === 'manual') && <FormInput
                label="Phone number"
                value={number}
                onChange={(event) => setNumber(event.target.value)}
                placeholder="+84901234567"
                pattern="\\+?[0-9]{1,32}"
                disabled={Boolean(phoneNumber)}
                required={!phoneNumber}
                autoComplete="off"
                tooltip={phoneNumber ? 'The exact number is immutable after creation.' : 'Use an optional + followed by 1 to 32 digits. No normalization is applied.'}
            />}
            <FormInput label="Label" value={label} onChange={(event) => setLabel(event.target.value)} placeholder="Sales line" autoComplete="off" required />
            <FormSelect
                label="Inbound Partner App"
                value={inboundAppId}
                onChange={(event) => setInboundAppId(event.target.value)}
                options={inboundAppOptions}
                disabled={!enabledApps.length && !canSaveUnavailableMapping}
                required
                tooltip="Exactly one Partner App receives inbound calls for this number."
            />
            <OutboundAppPicker
                apps={apps}
                selectedIds={outboundAppIds}
                existingAssignments={existingAssignments}
                disabled={saving}
                onChange={setOutboundAppIds}
            />
            <p className="-mt-2 mb-4 text-xs text-muted-foreground">
                An app with one assigned enabled number can use it automatically for outbound calls. If it has multiple enabled numbers, callers must provide an exact caller_number; assignments never choose arbitrarily.
            </p>
            <FormSwitch
                label="Enabled"
                description="Disabled numbers block new inbound and outbound calls; existing calls continue."
                checked={enabled}
                onChange={(event) => setEnabled(event.target.checked)}
            />
            <p className="mb-4 text-xs text-muted-foreground">
                Adding a new number waits for Apply configuration. Reassigning an existing inbound Partner App, changing outbound assignments, and enabling or disabling take effect for new calls immediately; existing calls continue. Apply publishes new inbound routes to FreePBX; it does not prove PSTN or carrier service.
            </p>
            <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={onCancel} disabled={saving}>Cancel</Button>
                <Button type="submit" disabled={formDisabled}>{saving ? 'Saving…' : phoneNumber ? 'Save routing' : 'Add number'}</Button>
            </div>
        </form>
    );
};

export default PhoneNumberForm;
