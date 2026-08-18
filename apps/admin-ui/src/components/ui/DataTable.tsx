import React from 'react';

interface Column<T> {
    header: string;
    cell: (row: T) => React.ReactNode;
    className?: string;
}

interface DataTableProps<T> {
    columns: Column<T>[];
    rows: T[];
    rowKey: (row: T) => string;
    empty?: React.ReactNode;
}

export function DataTable<T>({ columns, rows, rowKey, empty }: DataTableProps<T>) {
    if (rows.length === 0 && empty) return <>{empty}</>;

    return (
        <div className="overflow-x-auto rounded-lg border border-border bg-card shadow-sm">
            <table className="w-full text-sm">
                <thead>
                    <tr className="border-b border-border bg-muted/40 text-left">
                        {columns.map((column) => (
                            <th
                                key={column.header}
                                className={`px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground ${column.className ?? ''}`}
                            >
                                {column.header}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {rows.map((row) => (
                        <tr key={rowKey(row)} className="border-b border-border/60 last:border-0 hover:bg-accent/40 transition-colors">
                            {columns.map((column) => (
                                <td key={column.header} className={`px-4 py-3 align-middle ${column.className ?? ''}`}>
                                    {column.cell(row)}
                                </td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

export default DataTable;
