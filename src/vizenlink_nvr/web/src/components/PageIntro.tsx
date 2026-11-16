import type { ReactNode } from "react";

/* The app header already shows the page title, so this row carries only a one-line
   purpose statement and the page actions. Slogan headings were removed: they pushed
   content down ~100px on every page. */
export function PageIntro({ description, actions }: { description: string; actions?: ReactNode }) {
  return <div className="page-intro flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
    <p className="min-w-0 max-w-2xl text-sm text-muted-foreground">{description}</p>
    {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
  </div>;
}
