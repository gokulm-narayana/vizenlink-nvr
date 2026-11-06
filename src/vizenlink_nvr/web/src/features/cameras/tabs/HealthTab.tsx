import React from "react";
import { HealthPanel } from "../HealthPanel";

export interface HealthTabProps {
  serial: string;
}

export function HealthTab({ serial }: HealthTabProps) {
  return (
    <div className="flex flex-col gap-4">
      <HealthPanel serial={serial} />
    </div>
  );
}
