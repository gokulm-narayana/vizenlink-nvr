import { NativeSelect } from "@/components/ui/native-select";
import { isCameraOffline } from "@/lib/recorder-status";
import React, { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { Input } from "@/components/ui/input";
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
  const [search, setSearch] = useState("");
  const filtered = cameras.filter(c => `${c.name} ${c.location || ""} ${c.serial}`.toLowerCase().includes(search.toLowerCase()));
  const [searchParams] = useSearchParams();
  const tab = searchParams.get("tab");

  const buildCameraUrl = (serial: string) => {
    return tab ? `/cameras/${encodeURIComponent(serial)}?tab=${encodeURIComponent(tab)}` : `/cameras/${encodeURIComponent(serial)}`;
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
          <NativeSelect
            id="camera-select"
            value={selectedSerial}
            onChange={handleSelectChange}
            className="min-w-0 flex-1"
          >
            {cameras.map((cam) => (
              <option key={cam.serial} value={cam.serial}>
                {cam.name} ({cam.serial})
              </option>
            ))}
          </NativeSelect>
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

      {/* Desktop Master Sidebar (>=1024px): stays in view below the header while details scroll */}
      <aside
        aria-label="Cameras"
        className="hidden lg:flex lg:sticky lg:top-20 lg:self-start lg:h-[calc(100dvh-6rem)] overflow-y-auto flex-col w-60 shrink-0 border-r border-border bg-card pr-4"
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

        <Input aria-label="Search camera settings" placeholder="Search cameras or locations…" value={search} onChange={e => setSearch(e.target.value)} className="mb-4" />
        <ScrollArea className="flex-1 -mr-4 pr-4">
          {filtered.length === 0 && <p className="py-4 text-sm text-muted-foreground">No cameras match your search.</p>}
          <div className="flex flex-col gap-1">
            {filtered.map((cam) => {
              const isSelected = cam.serial === selectedSerial;
              const isOnline = !isCameraOffline(cam);

              return (
                <Link
                  key={cam.serial}
                  to={buildCameraUrl(cam.serial)}
                  className={cn(
                    "flex items-center justify-between rounded-md px-2 py-2 text-xs transition-colors",
                    isSelected
                      ? "bg-selected text-selected-foreground font-semibold"
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
