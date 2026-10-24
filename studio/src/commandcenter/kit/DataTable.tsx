import React, { useCallback, useRef, useState } from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

// ═══════════════════════════════════════════════════════════════════════════
// AETHEL Command Center — Virtualized Data Table
// বাংলা মন্তব্য: ভার্চুয়ালাইজড টেবিল — বড় ডেটাসেটের জন্য লাইটওয়েট
// ═══════════════════════════════════════════════════════════════════════════

export interface Column<T> {
    key: string;
    label: string;
    /** বাংলা মন্তব্য: render ঐচ্ছিক — না দিলে row[key] সরাসরি দেখানো হয় */
    render?: (row: T) => React.ReactNode;
    sortable?: boolean;
    width?: string;
    align?: 'left' | 'center' | 'right';
}

interface DataTableProps<T> {
    columns: Column<T>[];
    data: T[];
    /** বাংলা মন্তব্য: keyField বা rowKey — যেকোনো একটি দিলেই চলে */
    keyField?: string;
    rowKey?: (row: T) => string;
    maxHeight?: number;
    loading?: boolean;
    emptyMessage?: string;
    onRowClick?: (row: T) => void;
}

function getVal<T>(row: T, key: string): unknown {
    return (row as Record<string, unknown>)[key];
}

export function DataTable<T extends object>({
    columns,
    data,
    keyField,
    rowKey,
    maxHeight = 400,
    loading,
    emptyMessage = 'NO DATA',
    onRowClick,
}: DataTableProps<T>) {

    const keyOf = (row: T, i: number): string =>
        rowKey ? String(rowKey(row)) : String(getVal(row, keyField ?? 'id') ?? i);
    const [sortKey, setSortKey] = useState<string | null>(null);
    const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

    const handleSort = useCallback((key: string) => {
        if (sortKey === key) {
            setSortDir(d => (d === 'asc' ? 'desc' : 'asc'));
        } else {
            setSortKey(key);
            setSortDir('asc');
        }
    }, [sortKey]);

    const sorted = React.useMemo(() => {
        if (!sortKey) return data;
        return [...data].sort((a, b) => {
            const aVal = getVal(a, sortKey);
            const bVal = getVal(b, sortKey);
            if (aVal == null) return 1;
            if (bVal == null) return -1;
            const cmp = String(aVal).localeCompare(String(bVal), undefined, { numeric: true });
            return sortDir === 'asc' ? cmp : -cmp;
        });
    }, [data, sortKey, sortDir]);

    const containerRef = useRef<HTMLDivElement>(null);
    // বাংলা মন্তব্য: TanStack Virtual-এর useVirtualizer রিএক্ট কম্পাইলারের সাথে সামঞ্জস্যপূর্ণ নয় — এটি ইচ্ছাকৃতভাবে স্কিপ করা হয়েছে।
    /* eslint-disable-next-line react-hooks/incompatible-library */
    const virtualizer = useVirtualizer({
        count: sorted.length,
        getScrollElement: () => containerRef.current,
        estimateSize: () => 32,
        overscan: 5,
    });

    if (loading) {
        return (
            <div className="flex items-center justify-center p-6 text-[10px] text-[var(--sa-text-2)] font-mono">
                <span className="animate-pulse">LOADING...</span>
            </div>
        );
    }

    if (sorted.length === 0) {
        return (
            <div className="flex items-center justify-center p-6 text-[10px] text-[var(--sa-text-2)] font-mono">
                {emptyMessage}
            </div>
        );
    }

    const useVirtual = sorted.length > 50;

    return (
        <div ref={containerRef} className="overflow-x-auto rounded-xl border border-[var(--sa-line)]" style={{ maxHeight }}>
            <table className="w-full text-[10px] font-mono">
                <thead>
                    <tr className="bg-[var(--sa-bg-2)] border-b border-[var(--sa-line)]">
                        {columns.map(col => (
                            <th
                                key={col.key}
                                className={`px-3 py-2 text-[9px] uppercase tracking-widest text-[var(--sa-text-2)] font-bold ${col.sortable ? 'cursor-pointer hover:text-[var(--sa-cyan)] select-none' : ''
                                    } ${col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'}`}
                                style={{ width: col.width }}
                                onClick={() => col.sortable && handleSort(col.key)}
                            >
                                {col.label}
                                {sortKey === col.key && (
                                    <span className="ml-1 text-[var(--sa-cyan)]">{sortDir === 'asc' ? '▲' : '▼'}</span>
                                )}
                            </th>
                        ))}
                    </tr>
                </thead>
                <tbody>
                    {useVirtual ? (
                        virtualizer.getVirtualItems().map(vRow => {
                            const row = sorted[vRow.index];
                            const i = vRow.index;
                            return (
                                <tr
                                    key={keyOf(row, i)}
                                    onClick={() => onRowClick?.(row)}
                                    className={`border-b border-[var(--sa-line)] transition-colors ${onRowClick ? 'cursor-pointer hover:bg-[var(--sa-bg-hover)]' : ''
                                        } ${i % 2 === 0 ? 'bg-[var(--sa-bg-1)]' : 'bg-[var(--sa-bg-2)]'}`}
                                    style={{
                                        position: 'absolute',
                                        transform: `translateY(${vRow.start}px)`,
                                        width: '100%',
                                        height: '32px',
                                        display: 'flex',
                                    }}
                                >
                                    {columns.map(col => (
                                        <td
                                            key={col.key}
                                            className={`px-3 py-2 text-[var(--sa-text-0)] ${col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                                                }`}
                                            style={{ flex: col.width ? undefined : 1, width: col.width, minWidth: col.width ? 0 : undefined }}
                                        >
                                            {col.render ? col.render(row) : String(getVal(row, col.key) ?? '')}
                                        </td>
                                    ))}
                                </tr>
                            );
                        })
                    ) : (
                        sorted.map((row, i) => (
                            <tr
                                key={keyOf(row, i)}
                                onClick={() => onRowClick?.(row)}
                                className={`border-b border-[var(--sa-line)] transition-colors ${onRowClick ? 'cursor-pointer hover:bg-[var(--sa-bg-hover)]' : ''
                                    } ${i % 2 === 0 ? 'bg-[var(--sa-bg-1)]' : 'bg-[var(--sa-bg-2)]'}`}
                            >
                                {columns.map(col => (
                                    <td
                                        key={col.key}
                                        className={`px-3 py-2 text-[var(--sa-text-0)] ${col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                                            }`}
                                    >
                                        {col.render ? col.render(row) : String(getVal(row, col.key) ?? '')}
                                    </td>
                                ))}
                            </tr>
                        ))
                    )}
                </tbody>
            </table>
            {useVirtual && (
                <div style={{ height: virtualizer.getTotalSize() }} className="relative w-full">
                    <div
                        className="absolute left-0 top-0 right-0"
                        style={{ height: virtualizer.getTotalSize() }}
                    />
                </div>
            )}
        </div>
    );
}
