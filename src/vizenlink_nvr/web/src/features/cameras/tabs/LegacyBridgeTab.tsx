/**
 * TEMPORARY BRIDGE TAB: Owned by Plan 09-18 for deletion.
 *
 * This bridge tab renders the legacy CameraSettingsView so that maintenance actions
 * (reboot, factory reset) and camera health diagnostics remain reachable until
 * Plan 09-18 replaces it with modern Health & Maintenance tabs.
 */

import React from "react";
import { CameraSettingsView } from "@/legacy/CameraSettingsView";
import type { CameraInfo } from "@/lib/queries";

export interface LegacyBridgeTabProps {
  cameras: CameraInfo[];
  userRole?: string;
}

export const LegacyBridgeTab: React.FC<LegacyBridgeTabProps> = ({
  cameras,
  userRole,
}) => {
  return (
    <div className="flex flex-col flex-1 border border-border rounded-lg bg-card p-4">
      <CameraSettingsView cameras={cameras as any} userRole={userRole} />
    </div>
  );
};
