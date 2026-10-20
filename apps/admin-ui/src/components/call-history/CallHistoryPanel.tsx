import { RefreshCw } from 'lucide-react';

import Button from '../ui/Button';
import ErrorPanel from '../ui/ErrorPanel';
import PageHeader from '../ui/PageHeader';
import { useCallHistory } from '../../hooks/useCallHistory';
import CallHistoryDetail from './CallHistoryDetail';
import CallHistoryFilters from './CallHistoryFilters';
import CallHistoryPagination from './CallHistoryPagination';
import CallHistoryTable from './CallHistoryTable';

const CallHistoryPanel = () => {
    const history = useCallHistory();

    return (
        <div>
            <PageHeader
                title="Call History"
                description="Durable Gateway call records and the status signals captured for each call."
                actions={
                    <Button variant="outline" size="sm" onClick={history.refresh} disabled={history.loading}>
                        <RefreshCw className={`h-3.5 w-3.5 ${history.loading ? 'animate-spin' : ''}`} />
                        Refresh
                    </Button>
                }
            />
            <div className="space-y-4">
                <CallHistoryFilters
                    values={history.draftFilters}
                    agents={history.agents}
                    agentsLoading={history.agentsLoading}
                    agentsError={history.agentsError}
                    onChange={history.updateDraftFilter}
                    onApply={history.applyFilters}
                    onReset={history.resetFilters}
                    disabled={history.loading}
                />
                {history.error && (
                    <div>
                        <ErrorPanel type="error" message={history.error} className="mb-3" />
                        <Button variant="outline" size="sm" onClick={history.refresh}>Retry</Button>
                    </div>
                )}
                {!history.error && (
                    <>
                        <div className={history.loading ? 'opacity-60 transition-opacity' : ''}>
                            <CallHistoryTable
                                rows={history.items}
                                selectedCallId={history.selectedCallId}
                                loading={history.loading}
                                onSelect={history.selectCall}
                            />
                        </div>
                        <CallHistoryPagination
                            currentPage={history.currentPage}
                            pageSize={history.pageSize}
                            total={history.total}
                            totalPages={history.totalPages}
                            loading={history.loading}
                            onPageChange={history.goToPage}
                        />
                        {history.selectedCallId && (
                            <CallHistoryDetail
                                call={history.selectedCall}
                                signals={history.signals}
                                loading={history.detailLoading}
                                error={history.detailError}
                                signalsLoading={history.signalsLoading}
                                signalsNextCursor={history.signalsNextCursor}
                                onRetry={history.retryDetail}
                                onClose={history.clearSelection}
                                onLoadMoreSignals={history.loadMoreSignals}
                            />
                        )}
                    </>
                )}
            </div>
        </div>
    );
};

export default CallHistoryPanel;
