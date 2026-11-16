import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { Search } from "lucide-react";

export function WorkspaceSearch() {
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (window.innerWidth >= 1100) input.current?.focus();
        else void navigate("/search");
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [navigate]);
  return <form role="search" className="workspace-search hidden min-w-0 items-center gap-2 rounded-lg border border-border bg-background px-4 py-2 md:flex" onSubmit={e => { e.preventDefault(); void navigate(`/search${value.trim() ? `?q=${encodeURIComponent(value.trim())}&range=all` : ""}`); setValue(""); }}>
    <Search className="size-4 shrink-0 text-muted-foreground" /><input ref={input} aria-label="Search workspace" placeholder="Search footage…" maxLength={100} value={value} onChange={e => setValue(e.target.value)} className="min-w-0 flex-1 border-0 bg-transparent text-sm outline-none" /><kbd className="shrink-0 rounded border border-border bg-card px-1 text-xs text-muted-foreground">⌘ K</kbd>
  </form>;
}
