import React from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "cn";
import { CAMERAS_COPY } from "./copy";
import type { CameraInfo } from "@/lib/queries";

export interface CameraListProps {
  cameras: CameraInfo[];
  selectedSerial: string;
}

export const CameraList: React.FC<CameraListProps> = ({
  cameras,
  selectedSerial,
}) => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const tab = searchParams.get("tab");

  const buildCameraUrl = (serial: string) => {
    return tab ? `/cameras/${serial}?tab=${encodeURIComponent(tab)}` : `/cameras/${serial}`;
  };

  const handleSelectChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    navigate(buildCameraUrl(e.target.value));
  };

  return (
    <>
      {/* Mobile Select dropdown (<1024px, lg:hidden) */}
      <div className="block lg:hidden w-full pb-4 border-b border-border">
        <label htmlFor="camera-select" className="sr-only">
          Select camera
        </label>
        <div className="flex items-center gap-2">
          <select
            id="camera-select"
            value={selectedSerial}
            onChange={handleSelectChange}
            className="flex-1 h-9 rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {cameras.map((cam) => (
              <option key={cam.serial} value={cam.serial}>
                {cam.name} ({cam.serial})
              </option>
            ))}
          </select>
          <Button
            asChild
            variant="outline"
            size="sm"
            className="h-9 gap-1 text-xs shrink-0"
          >
            <Link to="/cameras/add">
              <Plus className="h-4 w-4" />
              <span>{CAMERAS_COPY.ADD_CAMERA}</span>
            </Link>
          </Button>
        </div>
      </div>

      {/* Desktop Master Sidebar (>=1024px, hidden lg:flex) */}
      <aside
        aria-label="Cameras"
        className="hidden lg:flex flex-col w-[280px] shrink-0 border-r border-border bg-card pr-4"
      >
        <div className="flex items-center justify-between pb-4">
          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
            {CAMERAS_COPY.LIST_CAPTION}
          </span>
          <Button
            asChild
            variant="outline"
            size="sm"
            className="h-8 gap-1 text-xs"
          >
            <Link to="/cameras/add">
              <Plus className="h-4 w-4" />
              <span>{CAMERAS_COPY.ADD_CAMERA}</span>
            </Link>
          </Button>
        </div>

        <ScrollArea className="flex-1 -mr-4 pr-4">
          <div className="flex flex-col gap-1">
            {cameras.map((cam) => {
              const isSelected = cam.serial === selectedSerial;
              const isOnline = cam.is_online !== false && cam.status !== "offline" && cam.state !== "offline";

              return (
                <Link
                  key={cam.serial}
                  to={buildCameraUrl(cam.serial)}
                  className={cn(
                    "flex items-center justify-between rounded-md px-2 py-2 text-xs transition-colors",
                    isSelected
                      ? "bg-muted text-foreground font-semibold"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  )}
                >
                  <div className="flex flex-col gap-0.5 min-w-0 pr-2">
                    <span className="truncate text-foreground text-xs">
                      {cam.name}
                    </span>
                    <span className="truncate text-xs font-normal text-muted-foreground">
                      {cam.location || cam.serial}
                    </span>
                  </div>

                  <span
                    className={cn(
                      "h-2 w-2 shrink-0 rounded-full",
                      isOnline ? "bg-success" : "bg-offline"
                    )}
                    aria-label={isOnline ? "Online" : "Offline"}
                  />
                </Link>
              );
            })}
          </div>
        </ScrollArea>
      </aside>
    </>
  );
};
