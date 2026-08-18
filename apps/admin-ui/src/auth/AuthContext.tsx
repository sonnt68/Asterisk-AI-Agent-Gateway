import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { toast } from 'sonner';

import { api } from '../lib/api';
import { apiErrorMessage } from '../utils/apiErrors';

export interface Session {
    user_id?: string;
    organization_id: string;
    role: string;
}

interface AuthContextType {
    session: Session | null;
    login: (email: string, password: string) => Promise<void>;
    logout: () => Promise<void>;
    refreshSession: () => Promise<void>;
    isAuthenticated: boolean;
    loading: boolean;
}

const AuthContext = createContext<AuthContextType | null>(null);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [session, setSession] = useState<Session | null>(null);
    const [loading, setLoading] = useState(true);

    // The control plane keeps the browser session in an httpOnly cookie, so the
    // only way to learn whether we are signed in is to ask for it.
    const refreshSession = useCallback(async () => {
        try {
            const response = await api.get<Session>('/auth/session');
            setSession(response.data);
        } catch {
            setSession(null);
        }
    }, []);

    useEffect(() => {
        refreshSession().finally(() => setLoading(false));
    }, [refreshSession]);

    const login = useCallback(async (email: string, password: string) => {
        const response = await api.post<Session>('/auth/login', { email, password });
        setSession(response.data);
    }, []);

    const logout = useCallback(async () => {
        try {
            await api.post('/auth/logout');
        } catch (err) {
            toast.error('Sign out failed', { description: apiErrorMessage(err, '/auth/logout') });
        } finally {
            setSession(null);
        }
    }, []);

    // A 401 anywhere means the session cookie expired or was revoked: drop back
    // to the login screen instead of leaving pages half-rendered.
    useEffect(() => {
        const interceptor = api.interceptors.response.use(
            (response) => response,
            (error) => {
                if (error?.response?.status === 401) {
                    setSession(null);
                }
                return Promise.reject(error);
            },
        );
        return () => {
            api.interceptors.response.eject(interceptor);
        };
    }, []);

    return (
        <AuthContext.Provider
            value={{ session, login, logout, refreshSession, isAuthenticated: !!session, loading }}
        >
            {children}
        </AuthContext.Provider>
    );
};

export const useAuth = () => {
    const context = useContext(AuthContext);
    if (!context) {
        throw new Error('useAuth must be used within an AuthProvider');
    }
    return context;
};
