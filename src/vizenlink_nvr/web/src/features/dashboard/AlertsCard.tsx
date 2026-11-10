import React from "react";
import { Bell, OctagonAlert, TriangleAlert, CircleCheck } from "lucide-react";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAlerts } from "@/lib/queries";
import { formatDateTime, useSiteTimeZone } from "@/lib/time";
import { useUiStore } from "@/stores/ui";
import { CameraHealthLink } from "@/components/CameraHealthLink";
import { DASHBOARD_COPY } from "./copy";

export const AlertsCard: React.FC = () => {
  const { data: allAlerts = [] } = useAlerts();
  const siteZone = useSiteTimeZone();
  const dismissedAlertIds = useUiStore((s) => s.dismissedAlertIds);
  const dismissAlert = useUiStore((s) => s.dismissAlert);

  const activeAlerts = allAlerts.filter((a) => !dismissedAlertIds.has(a.id));

  return (
    <Card className="flex flex-col gap-0 border-border bg-card py-0">
      <CardHeader className="flex flex-row items-center justify-between border-b border-border p-4">
        <div className="flex items-center gap-2">
          <Bell className="h-4 w-4 text-muted-foreground" />
          <CardTitle className="text-sm font-semibold text-foreground">
            {DASHBOARD_COPY.ALERTS_TITLE}
          </CardTitle>
        </div>

        {activeAlerts.length > 0 && (
          <span className="text-xs font-semibold text-critical">
            {activeAlerts.length} active
          </span>
        )}
      </CardHeader>

      <CardContent className="flex flex-col gap-4 p-4">
        {activeAlerts.length === 0 ? (
          <div className="flex items-center gap-3 py-2 text-sm text-muted-foreground">
            <CircleCheck className="size-5 shrink-0 text-success" />{DASHBOARD_COPY.ALERTS_EMPTY}
          </div>
        ) : (
          <div className="flex flex-col gap-2 max-h-[240px] overflow-y-auto pr-1">
            {activeAlerts.map((alert) => {
              const isCrit = alert.severity === "critical";
              const formattedTime = alert.timestamp
                ? formatDateTime(alert.timestamp, siteZone)
                : null;

              return (
                <div
                  key={alert.id}
                  className="flex items-start justify-between gap-4 rounded-md border border-border bg-muted/30 p-2 text-xs"
                >
                  <div className="flex items-start gap-2 min-w-0 flex-1">
                    {isCrit ? (
                      <OctagonAlert className="h-4 w-4 text-critical shrink-0 mt-0.5" />
                    ) : (
                      <TriangleAlert className="h-4 w-4 text-warning shrink-0 mt-0.5" />
                    )}
                    <div className="flex flex-col gap-1 min-w-0 flex-1">
                      <span className="font-semibold text-foreground break-words">
                        {alert.message}
                      </span>
                      <div className="flex flex-wrap items-center gap-2 text-muted-foreground text-xs font-normal">
                        {formattedTime && <span>{formattedTime}</span>}
                        {alert.camera_serial && (
                          <CameraHealthLink
                            serial={alert.camera_serial}
                            className="text-xs"
                          />
                        )}
                      </div>
                    </div>
                  </div>

                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => dismissAlert(alert.id)}
                    className="h-7 text-xs font-normal text-muted-foreground hover:text-foreground shrink-0"
                  >
                    {DASHBOARD_COPY.ALERTS_DISMISS}
                  </Button>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
};
