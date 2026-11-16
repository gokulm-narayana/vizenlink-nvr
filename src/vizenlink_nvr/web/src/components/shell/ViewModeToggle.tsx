import { useAccountPreferences } from "@/features/profile/preferences";
import React from "react";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useUiStore, type ViewMode } from "@/stores/ui";

export const ViewModeToggle: React.FC = () => {
  const { setViewMode } = useAccountPreferences();
  const viewMode = useUiStore((s) => s.viewMode);

  return (
    <div className="hidden md:flex items-center gap-2">
      <span className="text-xs font-semibold text-muted-foreground select-none">
        View
      </span>
      <ToggleGroup
        type="single"
        value={viewMode}
        onValueChange={(val) => {
          if (val === "simple" || val === "advanced") {
            setViewMode(val as ViewMode);
          }
        }}
        aria-label="View"
        variant="outline"
        size="sm"
      >
        <ToggleGroupItem value="simple" aria-label="Simple view">
          Simple
        </ToggleGroupItem>
        <ToggleGroupItem value="advanced" aria-label="Advanced view">
          Advanced
        </ToggleGroupItem>
      </ToggleGroup>
    </div>
  );
};

export default ViewModeToggle;
