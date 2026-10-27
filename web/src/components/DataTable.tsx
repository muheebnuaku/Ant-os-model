"use client";

import type { ReactNode } from "react";

import { EmptyState, SkeletonRows } from "./ui";

/* The standard table (§6): sticky header, 48 px rows, whole-row click,
   right-aligned numbers, designed loading and empty states, and stacked
   rows on small screens (each cell labelled by its column). */

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  numeric?: boolean;
  width?: number | string;
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  loading,
  refreshing = false,
  empty,
  footer,
  caption,
}: {
  refreshing?: boolean;
  columns: Column<T>[];
  rows: T[] | null;
  rowKey: (row: T) => string;
  onRowClick?: (row: T) => void;
  loading?: boolean;
  empty: { title: string; description?: string };
  footer?: ReactNode;
  caption: string;
}) {
  if (!rows && loading) return <SkeletonRows rows={5} />;
  if (!rows?.length) return <EmptyState title={empty.title}>{empty.description}</EmptyState>;
  return (
    <div className="refreshable" data-refreshing={refreshing} aria-busy={refreshing}>
      <div className="table-wrap">
        <table className="table">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} scope="col" className={c.numeric ? "num" : undefined} style={c.width ? { width: c.width } : undefined}>
                  {c.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                data-clickable={onRowClick ? "true" : undefined}
                onClick={onRowClick ? (e) => {
                  if ((e.target as HTMLElement).closest("a, button, input, select, textarea")) return;
                  onRowClick(row);
                } : undefined}
              >
                {columns.map((c) => (
                  <td key={c.key} data-label={c.header} className={c.numeric ? "num" : undefined}>
                    {c.render(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-foot">
        <span className="t-num">Showing {rows.length.toLocaleString()} {rows.length === 1 ? "item" : "items"}</span>
        <span className="spacer" />
        {footer}
      </div>
    </div>
  );
}
