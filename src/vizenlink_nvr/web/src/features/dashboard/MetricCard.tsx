import React from "react";
import { Card } from "@/components/ui/card";
import { cn } from "cn";

export interface MetricCardProps {
  label: string;
  value: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  footer,
  className,
}) => {
  return (
    <Card
      className={cn(
        "flex min-w-0 flex-col justify-between gap-2 p-4 bg-card border-border",
        className
      )}
    >
      <div className="flex flex-col gap-1">
        <span className="text-sm font-normal text-muted-foreground">
          {label}
        </span>
        <div className="flex items-center gap-2">
          {typeof value === "string" || typeof value === "number" ? (
            <span className="text-xl font-semibold text-foreground">{value}</span>
          ) : (
            value
          )}
        </div>
      </div>
      {footer && <div className="mt-auto pt-2">{footer}</div>}
    </Card>
  );
};
