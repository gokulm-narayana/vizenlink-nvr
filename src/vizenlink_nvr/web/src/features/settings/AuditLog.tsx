import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { formatDateTime, useSiteTimeZone } from "@/lib/time";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InlineError } from "@/components/InlineError";
import { SettingsSection } from "./SettingsSection";

type Entry = { id: number; timestamp: string; action: string; actor_username: string | null; resource_type: string; resource_id: string | null };

/* Plain-language names for the action codes the recorder writes. Unknown codes fall back to
   a readable form of the code itself, so a new backend action never shows up blank. */
const ACTION_LABELS: Record<string, string> = {
  "auth.login_success": "Signed in",
  "auth.login_failure": "Sign-in failed",
  "auth.logout": "Signed out",
  "auth.password_change": "Changed own password",
  "auth.sign_out_others": "Signed out other sessions",
  "user.create": "Created user",
  "user.update": "Updated user",
  "user.reset_password": "Reset user password",
  "system.setup": "Completed first-time setup",
  "system.update": "Changed system settings",
  "storage.update_path": "Changed recording folder",
  "camera.add": "Added camera",
  "camera.remove": "Removed camera",
  "camera.reboot": "Rebooted camera",
  "camera.reprobe": "Re-checked camera",
  "camera.factory_reset": "Factory-reset camera",
  "camera.recording.export": "Exported camera SD recording",
  "camera.settings.update_identity": "Changed camera details",
  "camera.settings.update_imaging": "Changed camera image settings",
  "camera.settings.update_encoder": "Changed camera video settings",
  "camera.settings.update_osd": "Changed on-screen text",
  "camera.osd.create": "Added on-screen text",
  "camera.osd.delete": "Removed on-screen text",
  "camera.mask.save": "Saved privacy mask",
  "camera.mask.delete": "Removed privacy mask",
  "event.lock": "Locked alert footage",
  "event.unlock": "Unlocked alert footage",
  "event.hide": "Deleted alert",
  "event.acknowledge_all": "Acknowledged all alerts",
  "playback.segment_lock": "Locked footage",
  "playback.segment_unlock": "Unlocked footage",
  "gallery.save_snapshot": "Saved snapshot",
  "gallery.export_clip": "Exported clip",
  "gallery.delete_item": "Deleted gallery item",
  "mobile.pair_qr": "Paired phone by QR code",
  "mobile.pair_credentials": "Paired phone by password",
  "mobile.pair_failed": "Phone pairing failed",
  "mobile.device_revoked": "Removed phone access",
};
const CATEGORY_LABELS: Record<string, string> = {
  auth: "Sign-in", user: "Users", system: "System", storage: "Storage", camera: "Cameras",
  event: "Alerts", playback: "Playback", gallery: "Gallery", mobile: "Mobile",
};
// Failures and destructive actions are the rows an owner scans for.
const ATTENTION = new Set(["auth.login_failure", "mobile.pair_failed", "camera.remove", "camera.factory_reset", "gallery.delete_item", "event.hide"]);

export function actionLabel(action: string): string {
  if (ACTION_LABELS[action]) return ACTION_LABELS[action];
  const text = action.replace(/[._]/g, " ");
  return text.charAt(0).toUpperCase() + text.slice(1);
}
function resourceLabel(entry: Entry): string {
  if (entry.resource_type === "session" || entry.resource_type === "system" || !entry.resource_id) return "—";
  return `${entry.resource_type.replace(/_/g, " ")} ${entry.resource_id}`;
}

export function AuditLog() {
  const zone = useSiteTimeZone();
  const [offset, setOffset] = useState(0);
  const [actor, setActor] = useState("");
  const [filter, setFilter] = useState("");
  const limit = 50;
  const page = useQuery({ queryKey: ["audit", filter, offset], queryFn: () =>
    apiFetch<{ items: Entry[]; total: number }>(`/api/v1/audit-logs?${new URLSearchParams({ limit: String(limit), offset: String(offset), ...(filter ? { actor: filter } : {}) })}`) });
  const total = page.data?.total ?? 0;
  const first = total ? offset + 1 : 0;
  const last = Math.min(offset + limit, total);
  return <SettingsSection
    flush
    title="Audit log"
    description="Who did what on this recorder: sign-ins, camera changes, user management and exports."
    action={<form className="flex items-center gap-2" onSubmit={e => { e.preventDefault(); setFilter(actor.trim()); setOffset(0); }}>
      <label className="sr-only" htmlFor="audit-user">Username</label>
      <Input id="audit-user" className="w-40" value={actor} onChange={e => setActor(e.target.value)} placeholder="All users" />
      <Button variant="outline"><Search className="size-4" />Filter</Button>
      {filter && <Button type="button" variant="ghost" onClick={() => { setActor(""); setFilter(""); setOffset(0); }}>Clear</Button>}
    </form>}
    footer={<>
      <span className="mr-auto text-sm text-muted-foreground" role="status">{page.data ? total ? `Showing ${first}–${last} of ${total} entries` : "0 entries" : ""}</span>
      <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(offset - limit)}>Previous</Button>
      <Button variant="outline" size="sm" disabled={!page.data || offset + limit >= total} onClick={() => setOffset(offset + limit)}>Next</Button>
    </>}
  >
    {page.isError ? <div className="p-6"><InlineError message={page.error.message} actionLabel="Retry audit log" onAction={() => void page.refetch()} /></div>
      : !page.data ? <p role="status" className="p-6 text-sm text-muted-foreground">Loading audit log…</p>
      : !page.data.items.length ? <p className="p-6 text-sm text-muted-foreground">No entries match this filter.</p>
      : <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground"><tr>{["Time", "User", "Action", "Area", "Resource"].map(label => <th key={label} scope="col" className="whitespace-nowrap px-6 py-2 font-semibold">{label}</th>)}</tr></thead>
        <tbody>{page.data.items.map(entry => {
          const category = entry.action.split(".")[0];
          return <tr key={entry.id} className="border-t border-border hover:bg-muted/40">
            <td className="whitespace-nowrap px-6 py-2 tabular-nums text-muted-foreground">{formatDateTime(entry.timestamp, zone)}</td>
            <td className="px-6 py-2 font-semibold">{entry.actor_username ?? "—"}</td>
            <td className={`px-6 py-2 ${ATTENTION.has(entry.action) ? "font-semibold text-critical" : ""}`} title={entry.action}>{actionLabel(entry.action)}</td>
            <td className="px-6 py-2"><span className="rounded-full bg-muted px-2 py-1 text-xs font-semibold text-muted-foreground">{CATEGORY_LABELS[category] ?? category}</span></td>
            <td className="break-all px-6 py-2 text-muted-foreground">{resourceLabel(entry)}</td>
          </tr>;
        })}</tbody></table></div>}
  </SettingsSection>;
}
