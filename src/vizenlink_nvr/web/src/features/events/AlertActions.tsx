import React, { useState } from "react";
import { Check, CheckCheck, RotateCcw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
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
import { useCurrentUser } from "@/lib/queries";
import { cn } from "cn";
import { useHideEvent, useReviewEvent, type EventItem } from "./api";

export const SEVERITY_LABEL = { critical: "Critical", warning: "Warning", info: "Info" } as const;
export const REVIEW_LABEL = { new: "New", acknowledged: "Acknowledged", resolved: "Resolved" } as const;

export function SeverityBadge({ severity }: { severity?: EventItem["severity"] }) {
  const s = severity ?? "info";
  return (
    <span
      data-severity={s}
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-semibold",
        s === "critical" && "bg-critical-subtle text-critical",
        s === "warning" && "bg-warning-subtle text-warning",
        s === "info" && "bg-info-subtle text-info"
      )}
    >
      {SEVERITY_LABEL[s]}
    </span>
  );
}

export function ReviewBadge({ state }: { state?: EventItem["review_state"] }) {
  const s = state ?? "new";
  return (
    <span
      data-review={s}
      className={cn(
        "rounded-full border px-2 py-0.5 text-xs font-semibold",
        s === "new" && "border-primary text-primary-text",
        s === "acknowledged" && "border-border text-muted-foreground",
        s === "resolved" && "border-success text-success"
      )}
    >
      {REVIEW_LABEL[s]}
    </span>
  );
}

/** Acknowledge / Resolve / Reopen / Remove, shared by the alert panel and the details page. */
export const AlertActions: React.FC<{ event: EventItem; onRemoved?: () => void; className?: string }> = ({
  event,
  onRemoved,
  className,
}) => {
  const user = useCurrentUser();
  const isManager = user?.role === "owner" || user?.role === "operator";
  const review = useReviewEvent();
  const hide = useHideEvent();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const state = event.review_state ?? "new";

  const run = (action: "acknowledge" | "resolve" | "reopen") =>
    review.mutate(
      { id: event.id, action },
      {
        onSuccess: () =>
          toast.success(action === "acknowledge" ? "Alert acknowledged" : action === "resolve" ? "Alert resolved" : "Alert reopened"),
        onError: (e) => toast.error(e.message),
      }
    );

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      {state === "new" && (
        <Button variant="outline" size="sm" disabled={review.isPending} onClick={() => run("acknowledge")}>
          <Check className="size-4" />
          Acknowledge
        </Button>
      )}
      {state !== "resolved" && (
        <Button variant="outline" size="sm" disabled={review.isPending} onClick={() => run("resolve")}>
          <CheckCheck className="size-4" />
          Resolve
        </Button>
      )}
      {state !== "new" && (
        <Button variant="ghost" size="sm" disabled={review.isPending} onClick={() => run("reopen")}>
          <RotateCcw className="size-4" />
          Reopen
        </Button>
      )}
      {isManager && (
        <Button
          variant="ghost"
          size="sm"
          className="text-destructive"
          disabled={hide.isPending}
          onClick={() => setConfirmOpen(true)}
        >
          <Trash2 className="size-4" />
          Remove alert
        </Button>
      )}
      {event.reviewed_by && (
        <span className="text-xs text-muted-foreground">
          {REVIEW_LABEL[state]} by {event.reviewed_by}
        </span>
      )}

      <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove this alert?</AlertDialogTitle>
            <AlertDialogDescription>
              It disappears from alert lists for everyone. The recorded footage is not deleted, and the removal is kept in the audit log.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Keep alert</AlertDialogCancel>
            <AlertDialogAction
              onClick={() =>
                hide.mutate(event.id, {
                  onSuccess: () => {
                    toast.success("Alert removed");
                    onRemoved?.();
                  },
                  onError: (e) => toast.error(e.message),
                })
              }
            >
              Remove alert
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
};
