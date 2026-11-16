import React from "react";
import { useLocation } from "react-router";
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

  // The Dashboard lists the same alerts in its own "Recent alerts" panel; repeating them
  // here showed one problem three times on the same screen.
  const { pathname } = useLocation();
  const onDashboard = pathname === "/" || pathname === "/dashboard";

  if (activeAlerts.length === 0 || onDashboard) {
    return null;
  }

  // Show at most 2 alerts
  const visibleAlerts = activeAlerts.slice(0, 2);

  return (
    <div
      data-slot="alert-stack"
      aria-live="polite"
      className={cn("flex flex-col gap-1 px-4 pt-2", className)}
    >
      {visibleAlerts.map((alert) => {
        const isCritical = alert.severity === "critical";

        return (
          // One thin line per alert: this strip sits above every page, so it must not push
          // the page down. Full detail lives in the bell menu and on the Dashboard.
          <Alert
            key={alert.id}
            role={isCritical ? "alert" : "status"}
            className={cn(
              "flex min-h-10 items-center gap-2 border px-4 py-1",
              isCritical
                ? "bg-critical-subtle border-critical/30 text-foreground"
                : "bg-warning-subtle border-warning/30 text-foreground"
            )}
          >
            {isCritical ? (
              <OctagonAlert className="size-4 shrink-0 text-critical" />
            ) : (
              <TriangleAlert className="size-4 shrink-0 text-warning" />
            )}
            <AlertTitle className="min-w-0 shrink truncate text-sm font-semibold">
              {alert.title || (isCritical ? "Critical alert" : "Warning alert")}
            </AlertTitle>
            <AlertDescription className="hidden min-w-0 flex-1 truncate text-xs text-foreground/90 md:block">
              {alert.message}
            </AlertDescription>
            <span className="ml-auto flex shrink-0 items-center gap-2">
              <CameraHealthLink serial={alert.camera_serial} source={alert.source} />
              <Button
                variant="ghost"
                size="icon"
                aria-label="Dismiss alert"
                title="Dismiss alert"
                onClick={() => dismissAlert(alert.id)}
                className="size-8 hover:bg-black/5 dark:hover:bg-white/5"
              >
                <X className="size-4" />
              </Button>
            </span>
          </Alert>
        );
      })}
    </div>
  );
};

export default AlertStack;
