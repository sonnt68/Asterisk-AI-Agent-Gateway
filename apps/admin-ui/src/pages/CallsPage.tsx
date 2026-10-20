import { useId, useRef, useState, type KeyboardEvent } from 'react';
import { History, PhoneCall, RefreshCw } from 'lucide-react';

import CallHistoryPanel from '../components/call-history/CallHistoryPanel';
import Button from '../components/ui/Button';
import { DataTable } from '../components/ui/DataTable';
import { EmptyState } from '../components/ui/EmptyState';
import ErrorPanel from '../components/ui/ErrorPanel';
import { PageLoader } from '../components/ui/LoadingSpinner';
import PageHeader from '../components/ui/PageHeader';
import { StatusPill } from '../components/ui/StatusPill';
import { useGatewayData } from '../hooks/useGatewayData';

const ActiveCallsView = ({ onOpenHistory }: { onOpenHistory: () => void }) => {
    const { calls, loading, error, refresh } = useGatewayData();

    if (loading) return <PageLoader message="Loading active calls…" />;

    return (
        <div>
            <PageHeader
                title="Active Calls"
                description="Calls currently bridged to an agent through this organization's connections."
                actions={
                    <>
                        <Button variant="outline" size="sm" onClick={onOpenHistory}>
                            <History className="w-3.5 h-3.5" />
                            Call history
                        </Button>
                        <Button variant="outline" size="sm" onClick={refresh}>
                            <RefreshCw className="w-3.5 h-3.5" />
                            Refresh
                        </Button>
                    </>
                }
            />
            {error && <ErrorPanel type="error" message={error} className="mb-6" />}
            <DataTable
                rows={calls}
                rowKey={(row) => row.id}
                empty={<EmptyState icon={PhoneCall} title="No active calls" />}
                columns={[
                    { header: 'Agent slug', cell: (row) => <code className="text-primary">{row.agent_slug}</code> },
                    { header: 'Call ID', cell: (row) => <code className="text-xs text-muted-foreground break-all">{row.id}</code> },
                    { header: 'Media transport', cell: (row) => <StatusPill tone="info">{row.media_transport}</StatusPill> },
                    {
                        header: 'Transfer',
                        cell: (row) =>
                            row.transfer_consulting ? (
                                <StatusPill tone="warning">Consulting</StatusPill>
                            ) : (
                                <span className="text-xs text-muted-foreground">—</span>
                            ),
                    },
                ]}
            />
        </div>
    );
};

const CallsPage = () => {
    const [view, setView] = useState<'active' | 'history'>('active');
    const tabsId = useId();
    const activeTab = useRef<HTMLButtonElement>(null);
    const historyTab = useRef<HTMLButtonElement>(null);
    const selectTab = (next: 'active' | 'history') => {
        setView(next);
        (next === 'active' ? activeTab : historyTab).current?.focus();
    };
    const onTabKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
        if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;
        event.preventDefault();
        selectTab(event.key === 'Home' ? 'active' : event.key === 'End' ? 'history'
            : view === 'active' ? 'history' : 'active');
    };

    return (
        <div>
            <div className="mb-5 flex gap-1 border-b border-border" role="tablist" aria-label="Call views" onKeyDown={onTabKeyDown}>
                <button
                    type="button"
                    role="tab"
                    ref={activeTab}
                    id={`${tabsId}-active-tab`}
                    aria-controls={`${tabsId}-active-panel`}
                    tabIndex={view === 'active' ? 0 : -1}
                    aria-selected={view === 'active'}
                    className={`border-b-2 px-3 py-2 text-sm font-medium transition-colors ${view === 'active'
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground'
                        }`}
                    onClick={() => setView('active')}
                >
                    Active calls
                </button>
                <button
                    type="button"
                    role="tab"
                    ref={historyTab}
                    id={`${tabsId}-history-tab`}
                    aria-controls={`${tabsId}-history-panel`}
                    tabIndex={view === 'history' ? 0 : -1}
                    aria-selected={view === 'history'}
                    className={`border-b-2 px-3 py-2 text-sm font-medium transition-colors ${view === 'history'
                        ? 'border-primary text-foreground'
                        : 'border-transparent text-muted-foreground hover:border-border hover:text-foreground'
                        }`}
                    onClick={() => setView('history')}
                >
                    Call history
                </button>
            </div>
            <div role="tabpanel" id={`${tabsId}-active-panel`} aria-labelledby={`${tabsId}-active-tab`} hidden={view !== 'active'} tabIndex={0}>
                {view === 'active' && <ActiveCallsView onOpenHistory={() => selectTab('history')} />}
            </div>
            <div role="tabpanel" id={`${tabsId}-history-panel`} aria-labelledby={`${tabsId}-history-tab`} hidden={view !== 'history'} tabIndex={0}>
                {view === 'history' && <CallHistoryPanel />}
            </div>
        </div>
    );
};

export default CallsPage;
