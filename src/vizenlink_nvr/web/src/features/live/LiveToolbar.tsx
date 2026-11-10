import React from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Button } from "@/components/ui/button";
import type { GridDimension } from "@/services/grid_storage";
import type { ViewMode } from "@/stores/ui";
import { LIVE_COPY } from "./copy";

interface LiveToolbarProps {
  dimension: GridDimension;
  onDimensionChange: (dim: GridDimension) => void;
  currentPage: number;
  totalPages: number;
  onPageChange: (page: number) => void;
  totalCameras: number;
  viewMode: ViewMode;
}

export const LiveToolbar: React.FC<LiveToolbarProps> = ({
  dimension,
  onDimensionChange,
  currentPage,
  totalPages,
  onPageChange,
  totalCameras,
  viewMode,
}) => {
  const allowedDimensions: GridDimension[] =
    [1, 2, 3, 4];

  const handleToggle = (val: string) => {
    if (!val) return;
    const parsed = parseInt(val, 10) as GridDimension;
    if (allowedDimensions.includes(parsed)) {
      onDimensionChange(parsed);
    }
  };

  return (
    <div className="sticky top-0 z-10 flex min-h-14 flex-wrap gap-4 py-2 shrink-0 items-center justify-between border-b border-border bg-card px-4">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-muted-foreground">
          {LIVE_COPY.TOOLBAR_LAYOUT}
        </span>
        <ToggleGroup
          type="single"
          value={dimension.toString()}
          onValueChange={handleToggle}
          variant="outline"
          size="sm"
        >
          {allowedDimensions.map((dim) => (
            <ToggleGroupItem
              key={dim}
              value={dim.toString()}
              aria-label={`${dim} by ${dim} grid`}
              className="text-xs font-semibold px-2 py-1"
            >
              {dim}×{dim}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      <div className="flex items-center gap-4">
        {totalPages > 1 && (
          <div className="flex items-center gap-1">
            <Button
              aria-label={LIVE_COPY.PREV_PAGE}
              variant="outline"
              size="icon"
              className="h-8 w-8"
              disabled={currentPage <= 0}
              onClick={() => onPageChange(Math.max(0, currentPage - 1))}
            >
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-xs font-normal text-muted-foreground px-1">
              {LIVE_COPY.PAGE_INDICATOR(currentPage + 1, totalPages)}
            </span>
            <Button
              aria-label={LIVE_COPY.NEXT_PAGE}
              variant="outline"
              size="icon"
              className="h-8 w-8"
              disabled={currentPage >= totalPages - 1}
              onClick={() => onPageChange(Math.min(totalPages - 1, currentPage + 1))}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        )}

        <span className="text-xs font-normal text-muted-foreground">
          {LIVE_COPY.CAMERAS_COUNT(totalCameras)}
        </span>
      </div>
    </div>
  );
};
