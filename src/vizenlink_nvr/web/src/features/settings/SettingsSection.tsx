import type { ReactNode } from "react";

/* One look for every settings block: titled card, one-line purpose, optional action on the
   right, optional footer for the save row. Keeps System, Storage, Recording and the audit
   log visually identical instead of each page styling its own box. */
export function SettingsSection({
  title,
  description,
  action,
  footer,
  children,
  flush = false,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  footer?: ReactNode;
  children?: ReactNode;
  /** Body without padding, for tables that run edge to edge. */
  flush?: boolean;
}) {
  return (
    <section className="min-w-0 overflow-hidden rounded-xl border border-border bg-card">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 border-b border-border px-6 py-4">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold">{title}</h2>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        {action && <div className="flex shrink-0 flex-wrap items-center gap-2">{action}</div>}
      </header>
      {children !== undefined && <div className={flush ? "min-w-0" : "flex min-w-0 flex-col gap-4 p-6"}>{children}</div>}
      {footer && <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-border bg-muted/40 px-6 py-4">{footer}</footer>}
    </section>
  );
}
