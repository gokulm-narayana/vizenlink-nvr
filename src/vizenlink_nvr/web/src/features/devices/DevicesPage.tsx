import React, { useState, useMemo } from "react";
import { Smartphone, Plus, Trash2, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Empty,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
  EmptyDescription,
  EmptyContent,
} from "@/components/ui/empty";
import { InlineError } from "@/components/InlineError";
import { useSiteTimeZone, formatDateTime, formatRelative } from "@/lib/time";
import { PairingDialog } from "./PairingDialog";
import { useDevices, useRevokeDevice, type PairedDevice } from "./api";
import { DEVICES_COPY } from "./copy";

export const DevicesPage: React.FC = () => {
  const siteZone = useSiteTimeZone();
  const [isPairingOpen, setIsPairingOpen] = useState<boolean>(false);
  const [deviceToRevoke, setDeviceToRevoke] = useState<PairedDevice | null>(null);
  const [revokeError, setRevokeError] = useState<string | null>(null);

  const {
    data: allDevices = [],
    isLoading,
    error,
    refetch,
  } = useDevices();

  const revokeMutation = useRevokeDevice();

  // Active unrevoked devices
  const activeDevices = useMemo(() => {
    return allDevices.filter((d) => !d.is_revoked);
  }, [allDevices]);

  const handleConfirmRevoke = async () => {
    if (!deviceToRevoke) return;
    setRevokeError(null);
    try {
      await revokeMutation.mutateAsync(deviceToRevoke.device_id || deviceToRevoke.id);
      setDeviceToRevoke(null);
    } catch {
      setRevokeError(DEVICES_COPY.REVOKE_FAILED(deviceToRevoke.device_name));
    }
  };

  return (
    <div className="flex min-h-full flex-col gap-6">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground tracking-tight">
            Mobile Devices
          </h2>
          <span className="text-xs font-normal text-muted-foreground">
            Paired mobile clients
          </span>
        </div>

        <Button
          type="button"
          variant="default"
          size="sm"
          onClick={() => setIsPairingOpen(true)}
          className="gap-2 text-xs"
        >
          <Plus className="h-4 w-4" />
          <span>{DEVICES_COPY.PAIR_DEVICE}</span>
        </Button>
      </div>

      {/* Revoke Error Alert */}
      {revokeError && deviceToRevoke && (
        <InlineError
          message={revokeError}
          actionLabel={DEVICES_COPY.RETRY_REVOKE}
          onAction={() => void handleConfirmRevoke()}
        />
      )}

      {/* Load Error */}
      {error && (
        <InlineError
          message={DEVICES_COPY.LOAD_ERROR}
          actionLabel={DEVICES_COPY.RELOAD_DEVICES}
          onAction={() => void refetch()}
        />
      )}

      {/* Loading Skeleton */}
      {isLoading ? (
        <div className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      ) : activeDevices.length === 0 ? (
        /* Empty State */
        <div className="flex items-center justify-center py-12">
          <Empty className="py-12 border border-border max-w-lg">
            <EmptyMedia variant="icon">
              <Smartphone className="h-6 w-6 text-muted-foreground" />
            </EmptyMedia>
            <EmptyHeader>
              <EmptyTitle>{DEVICES_COPY.EMPTY_HEADING}</EmptyTitle>
              <EmptyDescription>{DEVICES_COPY.EMPTY_BODY}</EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              <Button
                type="button"
                variant="default"
                size="sm"
                onClick={() => setIsPairingOpen(true)}
              >
                {DEVICES_COPY.PAIR_DEVICE}
              </Button>
            </EmptyContent>
          </Empty>
        </div>
      ) : (
        <>
          {/* Desktop Table (>= 768px, hidden md:block) */}
          <div className="hidden md:block rounded-lg border border-border bg-card overflow-hidden">
            <Table>
              <TableHeader className="bg-muted/40">
                <TableRow className="border-b border-border text-xs">
                  <TableHead className="font-semibold text-foreground">Device Name</TableHead>
                  <TableHead className="font-semibold text-foreground">Platform</TableHead>
                  <TableHead className="font-semibold text-foreground">Paired</TableHead>
                  <TableHead className="font-semibold text-foreground">Last Seen</TableHead>
                  <TableHead className="text-right font-semibold text-foreground">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {activeDevices.map((device) => {
                  const pairedFormatted = device.paired_at
                    ? formatDateTime(device.paired_at, siteZone)
                    : "—";
                  const lastSeenRelative = device.last_seen_at
                    ? formatRelative(device.last_seen_at)
                    : "Never";
                  const lastSeenAbsolute = device.last_seen_at
                    ? formatDateTime(device.last_seen_at, siteZone)
                    : "";

                  return (
                    <TableRow
                      key={device.id || device.device_id}
                      className="border-b border-border/60 last:border-0 text-xs"
                    >
                      <TableCell className="font-semibold text-foreground">
                        {device.device_name}
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1.5 text-muted-foreground">
                          <Smartphone className="h-4 w-4 shrink-0 text-foreground" />
                          <span className="capitalize">{device.platform}</span>
                        </div>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {pairedFormatted}
                      </TableCell>
                      <TableCell>
                        <span title={lastSeenAbsolute} className="text-muted-foreground">
                          {lastSeenRelative}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeviceToRevoke(device)}
                          className="h-8 text-xs text-critical hover:text-critical hover:bg-critical-subtle"
                        >
                          <Trash2 className="h-4 w-4 mr-1" />
                          <span>{DEVICES_COPY.REVOKE_ACTION}</span>
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>

          {/* Mobile Stacked Cards (< 768px, block md:hidden) */}
          <div className="flex flex-col gap-4 md:hidden">
            {activeDevices.map((device) => {
              const pairedFormatted = device.paired_at
                ? formatDateTime(device.paired_at, siteZone)
                : "—";
              const lastSeenRelative = device.last_seen_at
                ? formatRelative(device.last_seen_at)
                : "Never";
              const lastSeenAbsolute = device.last_seen_at
                ? formatDateTime(device.last_seen_at, siteZone)
                : "";

              return (
                <div
                  key={device.id || device.device_id}
                  className="flex flex-col gap-2 rounded-lg border border-border bg-card p-4 text-xs"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="min-w-0 text-sm font-semibold wrap-anywhere text-foreground">
                      {device.device_name}
                    </span>
                    <div className="flex shrink-0 items-center gap-1 text-muted-foreground">
                      <Smartphone className="h-4 w-4 text-foreground" />
                      <span className="capitalize">{device.platform}</span>
                    </div>
                  </div>

                  <div className="flex flex-col gap-1 text-muted-foreground pt-1 border-t border-border/40">
                    <div>
                      <span>Paired: </span>
                      <span className="text-foreground">{pairedFormatted}</span>
                    </div>
                    <div>
                      <span>Last seen: </span>
                      <span title={lastSeenAbsolute} className="text-foreground">
                        {lastSeenRelative}
                      </span>
                    </div>
                  </div>

                  <div className="pt-2 flex justify-end">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      onClick={() => setDeviceToRevoke(device)}
                      className="h-8 text-xs text-critical hover:text-critical hover:bg-critical-subtle border-critical/30"
                    >
                      <Trash2 className="h-4 w-4 mr-1" />
                      <span>{DEVICES_COPY.REVOKE_ACTION}</span>
                    </Button>
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Pairing Dialog */}
      <PairingDialog
        isOpen={isPairingOpen}
        onClose={() => setIsPairingOpen(false)}
      />

      {/* Revoke Confirmation Dialog */}
      <AlertDialog
        open={Boolean(deviceToRevoke)}
        onOpenChange={(open) => !open && setDeviceToRevoke(null)}
      >
        <AlertDialogContent className="max-w-[480px]">
          <AlertDialogHeader>
            <AlertDialogTitle className="text-sm font-semibold text-foreground">
              {deviceToRevoke && DEVICES_COPY.REVOKE_TITLE(deviceToRevoke.device_name)}
            </AlertDialogTitle>
            <AlertDialogDescription className="text-xs text-muted-foreground">
              {deviceToRevoke && DEVICES_COPY.REVOKE_BODY(deviceToRevoke.device_name)}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="gap-2">
            <AlertDialogCancel
              disabled={revokeMutation.isPending}
              className="text-xs h-8"
            >
              {DEVICES_COPY.KEEP_PAIRED}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void handleConfirmRevoke();
              }}
              disabled={revokeMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90 text-xs h-8"
            >
              {revokeMutation.isPending && (
                <Loader2 className="h-4 w-4 animate-spin mr-1.5" />
              )}
              {DEVICES_COPY.REVOKE_ACTION}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
