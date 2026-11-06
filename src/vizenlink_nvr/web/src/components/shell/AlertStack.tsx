import React from "react";
import { OctagonAlert, TriangleAlert, X } from "lucide-react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { CameraHealthLink } from "@/components/CameraHealthLink";
import { useAlerts } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import { cn } from "cn";

export const AlertStack: React.FC<{ className?: string }> = ({ className }) => {
  const { data: rawAlerts = [] } = useAlerts();
  const dismissedAlertIds = useUiStore((s) => s.dismissedAlertIds);
  const dismissAlert = useUiStore((s) => s.dismissAlert);

  const activeAlerts = React.useMemo(() => {
    return (rawAlerts as any[])
      .filter((a) => !dismissedAlertIds.has(a.id))
      .sort((a, b) => {
        if (a.severity === "critical" && b.severity !== "critical") return -1;
        if (a.severity !== "critical" && b.severity === "critical") return 1;
        const timeA = a.timestamp ? new Date(a.timestamp).getTime() : 0;
        const timeB = b.timestamp ? new Date(b.timestamp).getTime() : 0;
        return timeB - timeA;
      });
  }, [rawAlerts, dismissedAlertIds]);

  if (activeAlerts.length === 0) {
    return null;
  }

  // Show at most 2 alerts
  const visibleAlerts = activeAlerts.slice(0, 2);

  return (
    <div
      data-slot="alert-stack"
      aria-live="polite"
      className={cn("flex flex-col gap-2 p-4 pb-0", className)}
    >
      {visibleAlerts.map((alert) => {
        const isCritical = alert.severity === "critical";

        return (
          <Alert
            key={alert.id}
            role={isCritical ? "alert" : "status"}
            className={cn(
              "relative flex flex-col md:flex-row md:items-center justify-between gap-4 border p-4",
              isCritical
                ? "bg-critical-subtle border-critical/30 text-foreground"
                : "bg-warning-subtle border-warning/30 text-foreground"
            )}
          >
            <div className="flex items-start gap-4 min-w-0 flex-1">
              {isCritical ? (
                <OctagonAlert className="h-5 w-5 shrink-0 text-critical mt-0.5" />
              ) : (
                <TriangleAlert className="h-5 w-5 shrink-0 text-warning mt-0.5" />
              )}
              <div className="flex flex-col gap-0.5 min-w-0">
                <AlertTitle className="text-sm font-semibold truncate">
                  {alert.title || (isCritical ? "Critical alert" : "Warning alert")}
                </AlertTitle>
                <AlertDescription className="text-xs text-foreground/90 break-words">
                  {alert.message}
                </AlertDescription>
                <div className="mt-1">
                  <CameraHealthLink
                    serial={alert.camera_serial}
                    source={alert.source}
                  />
                </div>
              </div>
            </div>

            <div className="flex items-center shrink-0 self-end md:self-center">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => dismissAlert(alert.id)}
                className="h-8 text-xs font-semibold hover:bg-black/5 dark:hover:bg-white/5"
              >
                <X className="h-3.5 w-3.5 mr-1" />
                Dismiss alert
              </Button>
            </div>
          </Alert>
        );
      })}
    </div>
  );
};

export default AlertStack;
