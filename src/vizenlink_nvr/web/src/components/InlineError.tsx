import React from "react";
import { CircleAlert } from "lucide-react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "cn";

export type ActionLabel = `Retry ${string}` | `Reload ${string}`;

export interface InlineErrorProps {
  title?: string;
  message: string;
  actionLabel: ActionLabel;
  onAction?: () => void;
  pending?: boolean;
  className?: string;
}

export const InlineError: React.FC<InlineErrorProps> = ({
  title,
  message,
  actionLabel,
  onAction,
  pending = false,
  className,
}) => {
  return (
    <Alert
      role="alert"
      className={cn(
        "flex flex-col sm:flex-row sm:items-center justify-between gap-4 border border-critical/30 bg-critical-subtle text-foreground p-4",
        className
      )}
    >
      <div className="flex items-start gap-4 min-w-0 flex-1">
        <CircleAlert className="h-5 w-5 text-critical shrink-0 mt-0.5" />
        <div className="flex flex-col gap-1 min-w-0">
          {title && (
            <AlertTitle className="text-sm font-semibold truncate">
              {title}
            </AlertTitle>
          )}
          <AlertDescription className="text-xs text-foreground/90 break-words">
            {message}
          </AlertDescription>
        </div>
      </div>

      {actionLabel && onAction && (
        <div className="shrink-0 self-end sm:self-center">
          <Button
            variant="secondary"
            size="sm"
            onClick={onAction}
            disabled={pending}
            className="h-8 text-xs font-semibold"
          >
            {pending ? (
              <>
                <Spinner className="mr-1.5 h-3.5 w-3.5" />
                <span>{actionLabel}</span>
              </>
            ) : (
              actionLabel
            )}
          </Button>
        </div>
      )}
    </Alert>
  );
};

export default InlineError;
