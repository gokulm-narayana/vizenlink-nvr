import React, { useMemo } from "react";
import { XIcon, History } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Empty, EmptyMedia, EmptyTitle, EmptyDescription } from "@/components/ui/empty";
import { formatDateTime, useSiteTimeZone } from "@/lib/time";
import { useOutages, type OutageRecord } from "./api";
import { DASHBOARD_COPY } from "./copy";

export interface OutageHistoryDialogProps {
  isOpen: boolean;
  onClose: () => void;
  filterCameraSerial?: string | null;
  cameraName?: string | null;
  zone?: string;
}

export function formatOutageDuration(sec?: number | null): string {
  if (sec === null || sec === undefined) return "Ongoing";
  const mins = Math.floor(sec / 60);
  const secs = Math.round(sec % 60);
  if (mins > 0) return `${mins}m ${secs}s`;
  return `${secs}s`;
}

export const OutageHistoryDialog: React.FC<OutageHistoryDialogProps> = ({
  isOpen,
  onClose,
  filterCameraSerial,
  cameraName,
  zone: zoneProp,
}) => {
  const defaultZone = useSiteTimeZone();
  const zone = zoneProp || defaultZone;
  const { data: allOutages = [], isLoading } = useOutages();

  const outages = useMemo(() => {
    if (!filterCameraSerial) return allOutages;
    return allOutages.filter((o) => o.camera_serial === filterCameraSerial);
  }, [allOutages, filterCameraSerial]);

  const dialogTitle = cameraName
    ? DASHBOARD_COPY.OUTAGES_CAMERA_TITLE(cameraName)
    : DASHBOARD_COPY.OUTAGES_TITLE;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        showCloseButton={false}
        className="flex max-w-3xl sm:max-w-3xl flex-col bg-card p-0"
      >
        {/* Header */}
        <DialogHeader className="flex shrink-0 flex-row items-center justify-between border-b border-border p-4 pr-12">
          <div className="flex min-w-0 items-center gap-2">
            <History className="h-4 w-4 shrink-0 text-muted-foreground" />
            <DialogTitle className="text-sm font-semibold truncate">
              {dialogTitle}
            </DialogTitle>
          </div>

          <Button
            aria-label={DASHBOARD_COPY.OUTAGES_CLOSE_ARIA}
            variant="ghost"
            size="icon"
            onClick={onClose}
            className="absolute top-2 right-2 h-8 w-8 z-20"
          >
            <XIcon className="h-4 w-4" />
            <span className="sr-only">{DASHBOARD_COPY.OUTAGES_CLOSE_ARIA}</span>
          </Button>
        </DialogHeader>

        {/* Content Body */}
        <div className="max-h-[400px] overflow-y-auto p-4 flex flex-col">
          {isLoading ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              Loading outage history...
            </div>
          ) : outages.length === 0 ? (
            <Empty className="py-8 border border-dashed border-border bg-card/40">
              <EmptyMedia>
                <History className="h-6 w-6 text-muted-foreground" />
              </EmptyMedia>
              <EmptyTitle>
                {filterCameraSerial
                  ? DASHBOARD_COPY.OUTAGES_EMPTY_FILTERED_TITLE
                  : DASHBOARD_COPY.OUTAGES_EMPTY_GLOBAL_TITLE}
              </EmptyTitle>
              <EmptyDescription>
                {filterCameraSerial && cameraName
                  ? DASHBOARD_COPY.OUTAGES_EMPTY_FILTERED_DESC(cameraName)
                  : DASHBOARD_COPY.OUTAGES_EMPTY_GLOBAL_DESC}
              </EmptyDescription>
            </Empty>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="border-b border-border hover:bg-transparent">
                  {!filterCameraSerial && (
                    <TableHead className="text-xs font-semibold">Camera</TableHead>
                  )}
                  <TableHead className="text-xs font-semibold">Started</TableHead>
                  <TableHead className="text-xs font-semibold">Ended</TableHead>
                  <TableHead className="text-xs font-semibold">Duration</TableHead>
                  <TableHead className="text-xs font-semibold">Reason</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {outages.map((outage) => (
                  <TableRow
                    key={outage.id}
                    className="border-b border-border hover:bg-muted/40 text-xs"
                  >
                    {!filterCameraSerial && (
                      <TableCell className="font-mono font-semibold">
                        {outage.camera_serial}
                      </TableCell>
                    )}
                    <TableCell>{formatDateTime(outage.started_at, zone)}</TableCell>
                    <TableCell>
                      {outage.ended_at
                        ? formatDateTime(outage.ended_at, zone)
                        : "Ongoing"}
                    </TableCell>
                    <TableCell className="tabular-nums font-semibold">
                      {formatOutageDuration(outage.duration_seconds)}
                    </TableCell>
                    <TableCell className="text-muted-foreground whitespace-normal break-words">
                      {outage.reason || "Disconnected"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>

        {/* Footer */}
        <div className="flex justify-end border-t border-border p-4 bg-card">
          <Button
            variant="outline"
            size="sm"
            onClick={onClose}
            className="text-xs font-semibold"
          >
            {DASHBOARD_COPY.OUTAGES_CLOSE}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
