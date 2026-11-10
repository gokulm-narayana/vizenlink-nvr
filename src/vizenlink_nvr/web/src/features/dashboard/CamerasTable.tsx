import React from "react";
import { Link } from "react-router";
import { Plus, Cctv } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Empty, EmptyMedia, EmptyTitle, EmptyDescription, EmptyContent } from "@/components/ui/empty";
import { StatusBadge } from "@/components/StatusBadge";
import { formatDateTime, formatRelative, useSiteTimeZone } from "@/lib/time";
import { useCurrentUser } from "@/lib/queries";
import { DASHBOARD_COPY } from "./copy";

export interface CameraTableItem {
  serial: string;
  name: string;
}

export interface CamerasTableProps {
  cameras: CameraTableItem[];
  recordingSerials: Set<string>;
  openOutageMap: Map<string, string>; // camera_serial -> started_at
  onViewOutage: (serial: string, name: string) => void;
  zone?: string;
}

export const CamerasTable: React.FC<CamerasTableProps> = ({
  cameras,
  recordingSerials,
  openOutageMap,
  onViewOutage,
  zone: zoneProp,
}) => {
  const defaultZone = useSiteTimeZone();
  const zone = zoneProp || defaultZone;
  const user = useCurrentUser();

  const isOperatorOrOwner = user?.role === "owner" || user?.role === "operator";

  if (cameras.length === 0) {
    return (
      <section className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-border bg-card p-5">
        <div className="flex items-center gap-4">
          <div className="rounded-lg bg-selected p-3 text-primary"><Cctv className="size-6" /></div>
          <div>
            <h2 className="font-semibold">{isOperatorOrOwner ? DASHBOARD_COPY.CAMERAS_EMPTY_OPERATOR_TITLE : DASHBOARD_COPY.CAMERAS_EMPTY_VIEWER_TITLE}</h2>
            <p className="mt-1 text-sm text-muted-foreground">{isOperatorOrOwner ? DASHBOARD_COPY.CAMERAS_EMPTY_OPERATOR_DESC : DASHBOARD_COPY.CAMERAS_EMPTY_VIEWER_DESC}</p>
          </div>
        </div>
        {isOperatorOrOwner && <Button asChild><Link to="/cameras/add"><Plus className="size-4" />{DASHBOARD_COPY.CAMERAS_ADD_BUTTON}</Link></Button>}
      </section>
    );
  }

  return (
    <Card className="border-border bg-card overflow-hidden gap-0 py-0">
      <CardHeader className="border-b border-border p-4">
        <CardTitle className="text-sm font-semibold text-foreground">
          {DASHBOARD_COPY.CAMERAS_TITLE}
        </CardTitle>
      </CardHeader>

      <CardContent className="p-0">
        {/* Desktop Table View */}
        <div className="hidden md:block overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow className="border-b border-border hover:bg-transparent">
                <TableHead className="text-xs font-semibold">Camera</TableHead>
                <TableHead className="text-xs font-semibold">Connectivity</TableHead>
                <TableHead className="text-xs font-semibold">Recording</TableHead>
                <TableHead className="text-xs font-semibold">Last Seen</TableHead>
                <TableHead className="text-right text-xs font-semibold">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {cameras.map((cam) => {
                const openOutageStartedAt = openOutageMap.get(cam.serial);
                const isOnline = !openOutageStartedAt;
                const isRecording = recordingSerials.has(cam.serial);

                const lastSeenRelative = isOnline
                  ? "Online"
                  : formatRelative(openOutageStartedAt);
                const lastSeenAbsolute = isOnline
                  ? "Currently online"
                  : formatDateTime(openOutageStartedAt, zone);

                return (
                  <TableRow key={cam.serial} className="border-b border-border hover:bg-muted/40">
                    <TableCell className="text-xs">
                      <div className="flex flex-col gap-0.5">
                        <span className="font-semibold text-foreground">{cam.name}</span>
                        <span className="text-muted-foreground font-mono text-xs">{cam.serial}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <StatusBadge kind={isOnline ? "online" : "offline"} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge kind={isRecording ? "online" : "not-recording"} label={isRecording ? "Enabled" : "Off"} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground" title={lastSeenAbsolute}>
                      {lastSeenRelative}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => onViewOutage(cam.serial, cam.name)}
                        className="h-8 text-xs font-semibold"
                      >
                        {DASHBOARD_COPY.VIEW_OUTAGE_HISTORY}
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>

        {/* Mobile Stacked Card View */}
        <div className="flex flex-col divide-y divide-border md:hidden">
          {cameras.map((cam) => {
            const openOutageStartedAt = openOutageMap.get(cam.serial);
            const isOnline = !openOutageStartedAt;
            const isRecording = recordingSerials.has(cam.serial);
            const lastSeenRelative = isOnline ? "Online" : formatRelative(openOutageStartedAt);

            return (
              <div key={cam.serial} className="flex flex-col gap-2 p-4 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-foreground text-sm">{cam.name}</span>
                  <span className="font-mono text-muted-foreground">{cam.serial}</span>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <StatusBadge kind={isOnline ? "online" : "offline"} />
                  <StatusBadge kind={isRecording ? "online" : "not-recording"} label={isRecording ? "Enabled" : "Off"} />
                </div>

                <div className="flex items-center justify-between pt-1">
                  <span className="text-muted-foreground">Last seen: {lastSeenRelative}</span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => onViewOutage(cam.serial, cam.name)}
                    className="h-7 text-xs font-semibold"
                  >
                    {DASHBOARD_COPY.VIEW_OUTAGE_HISTORY}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </CardContent>
    </Card>
  );
};
