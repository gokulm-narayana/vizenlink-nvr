import React from "react";
import { Link } from "react-router";
import { useCurrentUser } from "@/lib/queries";
import { isRegistered } from "@/app/routes";
import { cn } from "cn";

interface CameraHealthLinkProps {
  serial?: string;
  source?: string;
  className?: string;
}

export function extractCameraSerial(serial?: string, source?: string): string | null {
  if (serial) return serial;
  if (!source) return null;
  if (source.startsWith("camera:") || source.startsWith("watchdog:")) {
    const parts = source.split(":");
    return parts[1] || null;
  }
  return null;
}

export const CameraHealthLink: React.FC<CameraHealthLinkProps> = ({
  serial: directSerial,
  source,
  className,
}) => {
  const user = useCurrentUser();
  const serial = extractCameraSerial(directSerial, source);

  if (!serial) {
    return null;
  }

  const role = user?.role || "viewer";

  if (role === "owner" || role === "operator") {
    return (
      <Link
        to={`/cameras/${encodeURIComponent(serial)}?tab=health`}
        className={cn(
          "inline-flex items-center text-xs font-semibold text-primary-text hover:underline",
          className
        )}
      >
        Open camera health
      </Link>
    );
  }

  // Viewer role
  if (isRegistered("/cameras/:serial/health")) {
    return (
      <Link
        to={`/cameras/${encodeURIComponent(serial)}/health`}
        className={cn(
          "inline-flex items-center text-xs font-semibold text-primary-text hover:underline",
          className
        )}
      >
        View camera health
      </Link>
    );
  }

  return null;
};

export default CameraHealthLink;
