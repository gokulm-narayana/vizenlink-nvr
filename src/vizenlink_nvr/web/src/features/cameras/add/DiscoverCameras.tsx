import { useMutation } from "@tanstack/react-query";
import { Search, Cctv } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { useCameras } from "@/lib/queries";
import { Button } from "@/components/ui/button";
import type { UseFormReturn } from "react-hook-form";
import type { AddCameraFormValues } from "./schema";

type FoundCamera = { host: string; port: number; name: string; location: string; model: string };
export function DiscoverCameras({ form }: { form: UseFormReturn<AddCameraFormValues> }) {
  const { data: existing = [] } = useCameras();
  const scan = useMutation({ mutationFn: () => apiFetch<{ cameras: FoundCamera[] }>("/api/v1/cameras/discover", { method: "POST" }) });
  const useCamera = (camera: FoundCamera) => {
    form.setValue("host", camera.host, { shouldDirty: true, shouldValidate: true });
    form.setValue("https_port", camera.port, { shouldDirty: true });
    form.setValue("name", camera.name, { shouldDirty: true });
    form.setValue("location", camera.location || "", { shouldDirty: true });
    document.getElementById("camera-serial")?.focus();
  };
  return <section className="mb-6 w-full max-w-xl rounded-xl border border-border bg-card p-6">
    <div className="flex flex-wrap items-center justify-between gap-4"><div><h2 className="font-semibold">Find cameras nearby</h2><p className="mt-1 text-sm text-muted-foreground">Search for supported cameras on the recorder's network.</p></div><Button type="button" variant="outline" disabled={scan.isPending} onClick={() => scan.mutate()}><Search className="size-4" />{scan.isPending ? "Searching…" : "Find cameras"}</Button></div>
    {scan.isPending && <p className="mt-4 text-sm text-muted-foreground" role="status">Searching can take up to 30 seconds. You can also enter the details below.</p>}
    {scan.isError && <p role="alert" className="mt-4 text-sm text-critical">{scan.error.message}</p>}
    {scan.data && !scan.isPending && <div className="mt-4 max-h-64 overflow-auto" aria-live="polite">{scan.data.cameras.length === 0 ? <p className="text-sm text-muted-foreground">No supported cameras found. Check that the camera and recorder are on the same network, or enter its address below.</p> : scan.data.cameras.map(c => {
      const added = existing.some(e => e.host === c.host && (e.https_port || 443) === c.port);
      return <div key={`${c.host}:${c.port}`} className="flex items-center gap-4 border-t border-border py-4"><Cctv className="size-5 shrink-0 text-primary" /><div className="min-w-0 flex-1"><p className="truncate font-semibold">{c.name}</p><p className="text-xs text-muted-foreground">{c.host} · {c.model}</p></div><Button type="button" variant="outline" size="sm" disabled={added} onClick={() => useCamera(c)}>{added ? "Already added" : "Use camera"}</Button></div>;
    })}</div>}
  </section>;
}
