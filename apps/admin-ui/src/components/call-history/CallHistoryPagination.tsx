import Button from '../ui/Button';

type PageToken = number | `ellipsis-${number}`;

type CallHistoryPaginationProps = {
    currentPage: number;
    pageSize: number;
    total: number;
    totalPages: number;
    loading: boolean;
    onPageChange: (page: number) => void;
};

const pageTokens = (currentPage: number, totalPages: number): PageToken[] => {
    const visible = new Set<number>([1, totalPages]);
    for (
        let page = Math.max(1, currentPage - 2);
        page <= Math.min(totalPages, currentPage + 2);
        page += 1
    ) {
        visible.add(page);
    }

    const pages = [...visible].sort((left, right) => left - right);
    return pages.flatMap((page, index) => {
        const previous = pages[index - 1];
        return previous !== undefined && page - previous > 1
            ? [`ellipsis-${page}` as const, page]
            : [page];
    });
};

export const CallHistoryPagination = ({
    currentPage,
    pageSize,
    total,
    totalPages,
    loading,
    onPageChange,
}: CallHistoryPaginationProps) => {
    const firstItem = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
    const lastItem = total === 0 ? 0 : Math.min(total, currentPage * pageSize);

    return (
        <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
                {total === 0 ? '0 calls' : `Showing ${firstItem}–${lastItem} of ${total} calls`}
            </span>
            <nav className="flex flex-wrap items-center justify-end gap-1" aria-label="Call history pages">
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onPageChange(currentPage - 1)}
                    disabled={loading || currentPage <= 1}
                >
                    Previous
                </Button>
                {pageTokens(currentPage, totalPages).map((token) =>
                    typeof token === 'number' ? (
                        <Button
                            key={token}
                            variant={token === currentPage ? 'secondary' : 'outline'}
                            size="sm"
                            onClick={() => onPageChange(token)}
                            disabled={loading}
                            aria-current={token === currentPage ? 'page' : undefined}
                            aria-label={`Go to page ${token}`}
                        >
                            {token}
                        </Button>
                    ) : (
                        <span key={token} className="px-1 text-sm text-muted-foreground" aria-hidden="true">
                            …
                        </span>
                    ),
                )}
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onPageChange(currentPage + 1)}
                    disabled={loading || currentPage >= totalPages}
                >
                    Next
                </Button>
            </nav>
        </div>
    );
};

export default CallHistoryPagination;
