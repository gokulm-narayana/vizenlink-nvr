import React, { useState, useEffect, useCallback } from "react";
import { toast } from "sonner";
import { Copy, RefreshCw, Loader2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { InlineError } from "@/components/InlineError";
import { QrCode } from "./QrCode";
import { useQrInit, type QRInitResponse } from "./api";
import { DEVICES_COPY } from "./copy";

export interface PairingDialogProps {
  isOpen: boolean;
  onClose: () => void;
}

export function formatExpiry(secondsRemaining: number): string {
  if (secondsRemaining <= 0) return "Code expired";
  const mins = Math.floor(secondsRemaining / 60);
  const secs = secondsRemaining % 60;
  if (mins > 0) return `Expires in ${mins}m ${secs}s`;
  return `Expires in ${secs}s`;
}

export const PairingDialog: React.FC<PairingDialogProps> = ({
  isOpen,
  onClose,
}) => {
  const qrInitMutation = useQrInit();
  const [data, setData] = useState<QRInitResponse | null>(null);
  const [secondsRemaining, setSecondsRemaining] = useState<number>(300);
  const [showHttpFallback, setShowHttpFallback] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const fetchCode = useCallback(async () => {
    setErrorMessage(null);
    setShowHttpFallback(false);
    try {
      const res = await qrInitMutation.mutateAsync();
      setData(res);
      const expDate = new Date(res.expires_at).getTime();
      const now = Date.now();
      setSecondsRemaining(Math.max(0, Math.floor((expDate - now) / 1000)));
    } catch {
      setErrorMessage(DEVICES_COPY.INIT_FAILED);
    }
  }, [qrInitMutation]);

  useEffect(() => {
    if (isOpen) {
      void fetchCode();
    } else {
      setData(null);
      setErrorMessage(null);
      setShowHttpFallback(false);
    }
  }, [isOpen]);

  // Expiry countdown timer
  useEffect(() => {
    if (!isOpen || !data || secondsRemaining <= 0) return;
    const interval = setInterval(() => {
      setSecondsRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [isOpen, data, secondsRemaining]);

  const handleCopyCode = async () => {
    if (!data?.pairing_code) return;
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(data.pairing_code);
        toast(DEVICES_COPY.CODE_COPIED_TOAST);
      } else {
        setShowHttpFallback(true);
      }
    } catch {
      setShowHttpFallback(true);
    }
  };

  const isExpired = secondsRemaining <= 0;

  return (
    <Dialog open={isOpen} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[30rem] gap-0 border-border bg-card p-0">
        <DialogHeader className="border-b border-border px-4 py-4 pr-12 sm:px-6 sm:pr-12">
          <DialogTitle className="text-sm font-semibold text-foreground">
            {DEVICES_COPY.PAIR_DEVICE}
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Connect the VizenLink mobile app to this NVR.
          </DialogDescription>
        </DialogHeader>

        <div className="flex min-w-0 flex-col items-center gap-4 p-4 sm:p-6">
          {qrInitMutation.isPending && !data ? (
            <div className="flex flex-col items-center gap-4 w-full py-8">
              <Skeleton className="aspect-square w-full max-w-60 rounded-lg" />
              <Skeleton className="h-6 w-36" />
              <Skeleton className="h-4 w-48" />
            </div>
          ) : errorMessage ? (
            <div className="w-full py-4">
              <InlineError
                message={errorMessage}
                actionLabel={DEVICES_COPY.RETRY_INIT}
                onAction={() => void fetchCode()}
              />
            </div>
          ) : data ? (
            <>
              {/* QR Code Container */}
              <div className="flex w-full flex-col items-center gap-2">
                <QrCode payload={data.qr_payload} dimmed={isExpired} />
                <span className="text-xs text-muted-foreground tabular-nums">
                  {formatExpiry(secondsRemaining)}
                </span>
              </div>

              {/* Pairing Code + Copy Button */}
              <div className="flex flex-col items-center gap-2 w-full">
                <div className="flex w-full items-center gap-2 rounded-md border border-border bg-muted/40 px-4 py-2">
                  <span className="min-w-0 flex-1 select-all font-mono text-sm font-semibold wrap-anywhere text-foreground">
                    {data.pairing_code}
                  </span>
                  <TooltipProvider>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon"
                          aria-label={DEVICES_COPY.COPY_CODE}
                          onClick={handleCopyCode}
                          className="h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground"
                        >
                          <Copy className="h-4 w-4" />
                        </Button>
                      </TooltipTrigger>
                      <TooltipContent side="top">
                        <span>{DEVICES_COPY.COPY_CODE}</span>
                      </TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </div>

                {showHttpFallback && (
                  <span className="text-xs text-muted-foreground">
                    {DEVICES_COPY.HTTP_FALLBACK}
                  </span>
                )}
              </div>

              {/* Numbered Instructions */}
              <ol className="w-full text-xs text-muted-foreground list-decimal list-inside flex flex-col gap-1.5 rounded-md border border-border bg-muted/20 p-4">
                <li>Open VizenLink on your mobile device.</li>
                <li>Tap <strong>Add NVR</strong> in Settings.</li>
                <li>Scan this QR code or enter the pairing code above.</li>
              </ol>

              {/* Generate new code */}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => void fetchCode()}
                disabled={qrInitMutation.isPending}
                className="gap-2 text-xs h-8"
              >
                {qrInitMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                <span>{DEVICES_COPY.GENERATE_NEW_CODE}</span>
              </Button>
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="flex justify-end border-t border-border bg-card p-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={onClose}
            className="text-xs h-8"
          >
            {DEVICES_COPY.CLOSE_PAIRING}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
};
