import axios from "axios";

export type ApiErrorKind = "network" | "http" | "unknown";

export type ApiErrorInfo = {
    kind: ApiErrorKind;
    endpoint?: string;
    status?: number;
    statusText?: string;
    message: string;
    detail?: string;
};

const coerceDetail = (data: unknown): string | undefined => {
    if (!data) return undefined;
    if (typeof data === 'string') return data;
    if (typeof data !== 'object') return String(data);

    const anyData = data as any;
    const val = anyData?.detail ?? anyData?.error ?? anyData?.message;
    if (val == null) return undefined;
    return typeof val === 'string' ? val : JSON.stringify(val);
};

export const describeApiError = (err: unknown, endpoint?: string): ApiErrorInfo => {
    if (axios.isAxiosError(err)) {
        if (!err.response) {
            return {
                kind: 'network',
                endpoint,
                message: err.message || 'Network error',
            };
        }

        return {
            kind: 'http',
            endpoint,
            status: err.response.status,
            statusText: err.response.statusText,
            message: err.message || `Request failed with status ${err.response.status}`,
            detail: coerceDetail(err.response.data),
        };
    }

    const message = err instanceof Error ? err.message : String(err);
    return { kind: 'unknown', endpoint, message };
};

/** Human-readable message for a failed control-plane call. */
export const apiErrorMessage = (err: unknown, endpoint?: string): string => {
    const info = describeApiError(err, endpoint);
    return info.detail || info.message;
};
