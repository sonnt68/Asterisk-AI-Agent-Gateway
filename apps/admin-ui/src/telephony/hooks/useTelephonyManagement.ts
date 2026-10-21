import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';

import { useAuth } from '../../auth/AuthContext';
import { api } from '../../lib/api';
import { apiErrorMessage, describeApiError } from '../../utils/apiErrors';
import type {
    PhoneNumber,
    PhoneNumberInput,
    PhoneNumberPatch,
    ApplyResponse,
    ProvisioningStatus,
    SipTrunk,
    SipTrunkInput,
    SipTrunkPatch,
} from '../types';

type TelephonyManagement = {
    provisioning: ProvisioningStatus | null;
    trunks: SipTrunk[];
    phoneNumbers: PhoneNumber[];
    loading: boolean;
    error: string | null;
    pendingApply: boolean;
    refresh: () => Promise<void>;
    saveTrunk: (input: SipTrunkInput | SipTrunkPatch, trunkId?: string) => Promise<void>;
    savePhoneNumber: (input: PhoneNumberInput | PhoneNumberPatch, phoneNumberId?: string) => Promise<void>;
    applyConfiguration: () => Promise<void>;
};

export type TelephonyResource = false | 'all' | 'trunks' | 'phoneNumbers';

const deniedStatus = (): ProvisioningStatus => ({
    configured: false,
    can_manage: false,
    connected: false,
    needs_apply: false,
    transports: [],
});

export const useTelephonyManagement = (resource: TelephonyResource = 'all'): TelephonyManagement => {
    const { isAuthenticated } = useAuth();
    const [provisioning, setProvisioning] = useState<ProvisioningStatus | null>(null);
    const [trunks, setTrunks] = useState<SipTrunk[]>([]);
    const [phoneNumbers, setPhoneNumbers] = useState<PhoneNumber[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const refreshing = useRef(false);

    const refresh = useCallback(async () => {
        if (!isAuthenticated || refreshing.current) return;
        refreshing.current = true;
        setLoading(true);
        try {
            const statusResponse = await api.get<ProvisioningStatus>('/asterisk/provisioning');
            const status = statusResponse.data;
            setProvisioning(status);
            setError(status.error ?? null);

            // Capability is authoritative. Do not probe tenant data endpoints for
            // an operator who cannot manage the deployment-bound PBX.
            if (resource === false || !status.can_manage) {
                setTrunks([]);
                setPhoneNumbers([]);
                return;
            }

            if (resource === 'trunks' || resource === 'all') {
                const trunksResponse = await api.get<SipTrunk[]>('/asterisk/trunks');
                setTrunks(trunksResponse.data);
            } else {
                setTrunks([]);
            }
            if (resource === 'phoneNumbers' || resource === 'all') {
                const phoneNumbersResponse = await api.get<PhoneNumber[]>('/phone-numbers');
                setPhoneNumbers(phoneNumbersResponse.data);
            } else {
                setPhoneNumbers([]);
            }
            setError(null);
        } catch (err) {
            const details = describeApiError(err);
            if (details.status === 403) {
                setProvisioning(deniedStatus());
                setTrunks([]);
                setPhoneNumbers([]);
                setError('Telephony management is unavailable for this organization or operator.');
            } else {
                setError(apiErrorMessage(err));
            }
        } finally {
            refreshing.current = false;
            setLoading(false);
        }
    }, [isAuthenticated, resource]);

    useEffect(() => {
        void refresh();
    }, [refresh]);

    const runMutation = useCallback(
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

    const saveTrunk = useCallback(
        (input: SipTrunkInput | SipTrunkPatch, trunkId?: string) =>
            runMutation(
                async () => {
                    if (trunkId) {
                        await api.patch(`/asterisk/trunks/${trunkId}`, input);
                    } else {
                        await api.post('/asterisk/trunks', input);
                    }
                },
                trunkId ? 'SIP trunk saved.' : 'SIP trunk created.',
            ),
        [runMutation],
    );

    const savePhoneNumber = useCallback(
        (input: PhoneNumberInput | PhoneNumberPatch, phoneNumberId?: string) =>
            runMutation(
                async () => {
                    if (phoneNumberId) {
                        await api.patch(`/phone-numbers/${phoneNumberId}`, input);
                    } else {
                        await api.post('/phone-numbers', input);
                    }
                },
                phoneNumberId ? 'Call routing saved.' : 'Inbound route saved. Apply configuration to publish the new number to FreePBX.',
            ),
        [runMutation],
    );

    const applyConfiguration = useCallback(
        () =>
            runMutation(
                async () => {
                    // The bridge response contains verified route readback. The
                    // refreshed provisioning/DID responses remain the UI source
                    // of truth for whether anything is still pending.
                    await api.post<ApplyResponse>('/asterisk/apply');
                },
                'Pending FreePBX configuration applied and verified.',
            ),
        [runMutation],
    );

    const pendingApply = useMemo(
        () => Boolean(provisioning?.needs_apply || phoneNumbers.some((number) => !number.pbx_applied)),
        [phoneNumbers, provisioning?.needs_apply],
    );

    return {
        provisioning,
        trunks,
        phoneNumbers,
        loading,
        error,
        pendingApply,
        refresh,
        saveTrunk,
        savePhoneNumber,
        applyConfiguration,
    };
};

export default useTelephonyManagement;
