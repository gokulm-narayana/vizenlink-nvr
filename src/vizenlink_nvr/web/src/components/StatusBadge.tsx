import React from "react";
import {
  Wifi,
  WifiOff,
  TriangleAlert,
  OctagonAlert,
  CircleOff,
  UserCheck,
  UserX,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "cn";

export type StatusKind =
  | "online"
  | "offline"
  | "recording"
  | "not-recording"
  | "degraded"
  | "critical"
  | "disabled"
  | "user-active"
  | "user-disabled";

interface StatusConfig {
  icon: React.ReactNode;
  defaultLabel: string;
  className: string;
}

const CONFIGS: Record<StatusKind, StatusConfig> = {
  online: {
    icon: <Wifi className="h-4 w-4 text-success shrink-0" />,
    defaultLabel: "Online",
    className: "bg-success-subtle text-foreground border-success/30",
  },
  offline: {
    icon: <WifiOff className="h-4 w-4 text-offline shrink-0" />,
    defaultLabel: "Offline",
    className: "bg-offline-subtle text-foreground border-offline/30",
  },
  recording: {
    icon: <span className="h-2 w-2 rounded-full bg-rec shrink-0" />,
    defaultLabel: "Recording",
    className: "bg-rec-subtle text-foreground border-rec/30",
  },
  "not-recording": {
    icon: <TriangleAlert className="h-4 w-4 text-warning shrink-0" />,
    defaultLabel: "Not recording",
    className: "bg-warning-subtle text-foreground border-warning/30",
  },
  degraded: {
    icon: <TriangleAlert className="h-4 w-4 text-warning shrink-0" />,
    defaultLabel: "Degraded",
    className: "bg-warning-subtle text-foreground border-warning/30",
  },
  critical: {
    icon: <OctagonAlert className="h-4 w-4 text-critical shrink-0" />,
    defaultLabel: "Critical",
    className: "bg-critical-subtle text-foreground border-critical/30",
  },
  disabled: {
    icon: <CircleOff className="h-4 w-4 text-muted-foreground shrink-0" />,
    defaultLabel: "Disabled",
    className: "bg-muted text-muted-foreground border-border",
  },
  "user-active": {
    icon: <UserCheck className="h-4 w-4 text-success shrink-0" />,
    defaultLabel: "Active",
    className: "bg-success-subtle text-foreground border-success/30",
  },
  "user-disabled": {
    icon: <UserX className="h-4 w-4 text-muted-foreground shrink-0" />,
    defaultLabel: "Disabled",
    className: "bg-muted text-muted-foreground border-border",
  },
};

export interface StatusBadgeProps {
  kind: StatusKind;
  label?: string;
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  kind,
  label,
  className,
}) => {
  const config = CONFIGS[kind] || CONFIGS.disabled;
  const text = label || config.defaultLabel;

  return (
    <Badge
      variant="outline"
      data-slot="status-badge"
      data-kind={kind}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold border",
        config.className,
        className
      )}
    >
      {config.icon}
      <span>{text}</span>
    </Badge>
  );
};

export default StatusBadge;
