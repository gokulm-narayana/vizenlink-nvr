import React from "react";
import { PairedDevicesView } from "@/legacy/PairedDevicesView";
import { useCurrentUser } from "@/lib/queries";
import type { ShellRoute } from "@/app/routes";

function DevicesRouteAdapter() {
  const user = useCurrentUser();
  return <PairedDevicesView userRole={user?.role} />;
}

export const routes: ShellRoute[] = [
  {
    path: "/devices",
    title: "Mobile devices",
    minRole: "owner",
    element: <DevicesRouteAdapter />,
  },
];
