import React from "react";
import { Check } from "lucide-react";
import { cn } from "cn";
import { ADD_CAMERA_COPY } from "./copy";

export interface StepperProps {
  currentStep: 1 | 2 | 3;
  className?: string;
}

export const Stepper: React.FC<StepperProps> = ({ currentStep, className }) => {
  return (
    <div className={cn("flex items-center justify-between gap-4 pb-4 border-b border-border", className)}>
      <ol className="flex items-center gap-4 list-none p-0 m-0">
        {ADD_CAMERA_COPY.STEPS.map((name, index) => {
          const stepNumber = (index + 1) as 1 | 2 | 3;
          const isCurrent = stepNumber === currentStep;
          const isCompleted = stepNumber < currentStep;

          return (
            <li
              key={name}
              aria-current={isCurrent ? "step" : undefined}
              className="flex items-center gap-2"
            >
              {isCompleted ? (
                <span className="flex size-6 items-center justify-center rounded-full border border-border bg-muted/30 text-xs font-semibold text-foreground">
                  <Check className="h-3.5 w-3.5 text-foreground" />
                </span>
              ) : isCurrent ? (
                <span className="flex size-6 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                  {stepNumber}
                </span>
              ) : (
                <span className="flex size-6 items-center justify-center rounded-full border border-border text-xs font-normal text-muted-foreground">
                  {stepNumber}
                </span>
              )}
              <span
                className={cn(
                  "text-xs leading-none",
                  isCurrent
                    ? "font-semibold text-foreground"
                    : "font-normal text-muted-foreground"
                )}
              >
                {name}
              </span>
            </li>
          );
        })}
      </ol>

      <span className="text-xs text-muted-foreground shrink-0">
        {ADD_CAMERA_COPY.STEP_CAPTION(currentStep, 3)}
      </span>
    </div>
  );
};
