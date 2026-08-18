import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { Loader2 } from 'lucide-react';

import { useAuth } from './AuthContext';

export const RequireAuth: React.FC<{ children: JSX.Element }> = ({ children }) => {
    const { isAuthenticated, loading } = useAuth();
    const location = useLocation();

    if (loading) {
        return (
            <div
                className="flex flex-col items-center justify-center h-screen gap-3 bg-background text-muted-foreground"
                role="status"
                aria-live="polite"
            >
                <Loader2 className="w-8 h-8 animate-spin text-primary" aria-hidden="true" />
                <span className="text-sm">Loading…</span>
            </div>
        );
    }

    if (!isAuthenticated) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    return children;
};
