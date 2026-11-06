import React from "react";
import { Lock } from "lucide-react";
import { TIMELINE_COPY } from "./copy";

export const TimelineLegend: React.FC = () => {
  return (
    <div className="flex flex-wrap items-center gap-4 text-xs font-normal text-muted-foreground select-none">
      {/* Recorded */}
      <div className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-xs bg-primary" />
        <span>{TIMELINE_COPY.LEGEND_RECORDED}</span>
      </div>

      {/* Recording Outage */}
      <div className="flex items-center gap-1.5">
        <span className="relative h-3 w-3 rounded-xs border border-warning text-warning overflow-hidden bg-background">
          <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
            <rect width="100%" height="100%" fill="url(#outage-hatch)" />
          </svg>
        </span>
        <span>{TIMELINE_COPY.LEGEND_OUTAGE}</span>
      </div>

      {/* Removed by Retention */}
      <div className="flex items-center gap-1.5">
        <span className="h-3 w-3 rounded-xs bg-input border-b-2 border-dotted border-foreground/60" />
        <span>{TIMELINE_COPY.LEGEND_RETENTION}</span>
      </div>

      {/* Event */}
      <div className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rotate-45 bg-info border border-background" />
        <span>{TIMELINE_COPY.LEGEND_EVENT}</span>
      </div>

      {/* Locked */}
      <div className="flex items-center gap-1.5">
        <span className="flex items-center justify-center">
          <Lock className="h-3 w-3 text-foreground" />
        </span>
        <span>{TIMELINE_COPY.LEGEND_LOCKED}</span>
      </div>
    </div>
  );
};
