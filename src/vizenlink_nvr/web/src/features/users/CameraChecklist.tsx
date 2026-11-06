import React from "react";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useCameras } from "@/lib/queries";
import { USERS_COPY } from "./copy";

export interface CameraChecklistProps {
  selectedSerials: string[];
  onChange: (serials: string[]) => void;
  disabled?: boolean;
}

export const CameraChecklist: React.FC<CameraChecklistProps> = ({
  selectedSerials,
  onChange,
  disabled = false,
}) => {
  const { data: cameras = [] } = useCameras();

  const handleSelectAll = () => {
    onChange(cameras.map((c) => c.serial));
  };

  const handleClearAll = () => {
    onChange([]);
  };

  const handleToggle = (serial: string, checked: boolean) => {
    if (checked) {
      if (!selectedSerials.includes(serial)) {
        onChange([...selectedSerials, serial]);
      }
    } else {
      onChange(selectedSerials.filter((s) => s !== serial));
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-foreground">
          {USERS_COPY.ASSIGNED_CAMERAS_LABEL}
        </span>
        <div className="flex items-center gap-1">
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleSelectAll}
            disabled={disabled || cameras.length === 0}
            className="h-7 text-xs px-2"
          >
            {USERS_COPY.SELECT_ALL_CAMERAS}
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={handleClearAll}
            disabled={disabled || selectedSerials.length === 0}
            className="h-7 text-xs px-2"
          >
            {USERS_COPY.CLEAR_ALL_CAMERAS}
          </Button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">
        {USERS_COPY.CAMERA_CHECKLIST_HELPER}
      </p>

      <ScrollArea className="h-44 rounded-md border border-border bg-card p-2">
        {cameras.length === 0 ? (
          <p className="p-4 text-center text-xs text-muted-foreground">
            No cameras available on NVR.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {cameras.map((camera) => {
              const isChecked = selectedSerials.includes(camera.serial);
              const checkboxId = `perm-camera-${camera.serial}`;

              return (
                <div
                  key={camera.serial}
                  className="flex items-center gap-2 rounded p-1.5 transition-colors hover:bg-muted/40"
                >
                  <Checkbox
                    id={checkboxId}
                    checked={isChecked}
                    onCheckedChange={(checked) =>
                      handleToggle(camera.serial, Boolean(checked))
                    }
                    disabled={disabled}
                  />
                  <Label
                    htmlFor={checkboxId}
                    className="flex flex-1 items-center justify-between gap-2 text-xs font-normal text-foreground cursor-pointer select-none"
                  >
                    <span className="font-semibold truncate">{camera.name}</span>
                    <span className="font-mono text-muted-foreground truncate">
                      {camera.serial}
                    </span>
                  </Label>
                </div>
              );
            })}
          </div>
        )}
      </ScrollArea>
    </div>
  );
};
