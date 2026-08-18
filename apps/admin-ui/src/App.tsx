import { Navigate, Route, BrowserRouter as Router, Routes } from 'react-router-dom';
import { Toaster } from 'sonner';

import { AuthProvider } from './auth/AuthContext';
import { RequireAuth } from './auth/RequireAuth';
import AppShell from './components/layout/AppShell';
import { ConfirmDialogProvider } from './hooks/useConfirmDialog';
import { GatewayDataProvider } from './hooks/useGatewayData';
import ApiKeysPage from './pages/ApiKeysPage';
import AsteriskPage from './pages/AsteriskPage';
import AuditPage from './pages/AuditPage';
import CallsPage from './pages/CallsPage';
import ConnectionsPage from './pages/ConnectionsPage';
import Dashboard from './pages/Dashboard';
import LoginPage from './pages/LoginPage';
import MembersPage from './pages/MembersPage';
import PartnerAppsPage from './pages/PartnerAppsPage';

function App() {
    return (
        <AuthProvider>
            <ConfirmDialogProvider>
                <Toaster position="top-right" richColors closeButton />
                <Router>
                    <Routes>
                        <Route path="/login" element={<LoginPage />} />

                        <Route
                            path="*"
                            element={
                                <RequireAuth>
                                    <GatewayDataProvider>
                                        <Routes>
                                            <Route element={<AppShell />}>
                                                <Route path="/" element={<Dashboard />} />
                                                <Route path="/partner-apps" element={<PartnerAppsPage />} />
                                                <Route path="/api-keys" element={<ApiKeysPage />} />
                                                <Route path="/members" element={<MembersPage />} />
                                                <Route path="/connections" element={<ConnectionsPage />} />
                                                <Route path="/calls" element={<CallsPage />} />
                                                <Route path="/asterisk" element={<AsteriskPage />} />
                                                <Route path="/audit" element={<AuditPage />} />
                                                <Route path="*" element={<Navigate to="/" replace />} />
                                            </Route>
                                        </Routes>
                                    </GatewayDataProvider>
                                </RequireAuth>
                            }
                        />
                    </Routes>
                </Router>
            </ConfirmDialogProvider>
        </AuthProvider>
    );
}

export default App;
