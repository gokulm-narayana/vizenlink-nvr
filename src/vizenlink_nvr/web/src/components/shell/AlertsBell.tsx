import React from "react";
import { Bell, OctagonAlert, TriangleAlert, X, CheckCircle2 } from "lucide-react";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { CameraHealthLink } from "@/components/CameraHealthLink";
import { useAlerts } from "@/lib/queries";
import { useUiStore } from "@/stores/ui";
import { cn } from "cn";

export const AlertsBell: React.FC = () => {
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

  const hasCritical = activeAlerts.some((a) => a.severity === "critical");
  const count = activeAlerts.length;

  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative h-9 w-9 rounded-md"
          aria-label={`Alerts, ${count} active`}
        >
          <Bell className="h-4 w-4" />
          {count > 0 && (
            <span
              className={cn(
                "absolute -top-1 -right-1 flex h-4 min-w-4 items-center justify-center rounded-full px-1 text-xs font-semibold leading-none tabular-nums",
                hasCritical
                  ? "bg-critical text-critical-foreground"
                  : "bg-warning text-warning-foreground"
              )}
            >
              {count > 99 ? "99+" : count}
            </span>
          )}
        </Button>
      </PopoverTrigger>

      <PopoverContent
        align="end"
        className="w-80 sm:w-96 p-0 shadow-md border-border bg-card"
      >
        <div className="flex items-center justify-between border-b border-border px-4 py-4">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold">Active alerts</h2>
            {count > 0 && (
              <Badge
                variant="outline"
                className={cn(
                  "h-5 px-1.5 text-xs font-semibold tabular-nums border-none",
                  hasCritical
                    ? "bg-critical-subtle text-critical"
                    : "bg-warning-subtle text-warning"
                )}
              >
                {count}
              </Badge>
            )}
          </div>
        </div>

        {count === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 p-6 text-center text-muted-foreground">
            <CheckCircle2 className="h-8 w-8 text-success" />
            <p className="text-sm font-normal">All clear. No active alerts.</p>
          </div>
        ) : (
          <ScrollArea className="max-h-80 overflow-y-auto">
            <div className="flex flex-col divide-y divide-border">
              {activeAlerts.map((alert) => {
                const isCritical = alert.severity === "critical";

                return (
                  <div
                    key={alert.id}
                    className={cn(
                      "flex flex-col gap-2 p-4 text-left transition-colors",
                      isCritical ? "bg-critical-subtle/30" : "bg-warning-subtle/30"
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2 min-w-0">
                        {isCritical ? (
                          <OctagonAlert className="h-4 w-4 shrink-0 text-critical mt-0.5" />
                        ) : (
                          <TriangleAlert className="h-4 w-4 shrink-0 text-warning mt-0.5" />
                        )}
                        <div className="min-w-0">
                          <h3 className="text-xs font-semibold text-foreground truncate">
                            {alert.title || (isCritical ? "Critical alert" : "Warning alert")}
                          </h3>
                          <p className="text-xs text-foreground/80 mt-0.5 break-words">
                            {alert.message}
                          </p>
                          {alert.timestamp && (
                            <span className="block text-xs text-muted-foreground mt-1 tabular-nums">
                              {new Date(alert.timestamp).toLocaleTimeString([], {
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </span>
                          )}
                          <div className="mt-1">
                            <CameraHealthLink
                              serial={alert.camera_serial}
                              source={alert.source}
                            />
                          </div>
                        </div>
                      </div>

                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => dismissAlert(alert.id)}
                        className="h-7 px-2 text-xs font-semibold text-muted-foreground hover:text-foreground shrink-0"
                      >
                        <X className="h-3 w-3 mr-1" />
                        Dismiss alert
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </ScrollArea>
        )}
      </PopoverContent>
    </Popover>
  );
};

export default AlertsBell;