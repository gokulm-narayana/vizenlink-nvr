import React, { useEffect, useState } from "react";
import { useIsFetching } from "@tanstack/react-query";

export interface RefetchBarProps {
  bootDelayMs?: number;
}

export const RefetchBar: React.FC<RefetchBarProps> = ({ bootDelayMs = 1000 }) => {
  const isFetching = useIsFetching();
  const [hasBooted, setHasBooted] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => {
      setHasBooted(true);
    }, bootDelayMs);
    return () => clearTimeout(timer);
  }, [bootDelayMs]);

  const show = hasBooted && isFetching > 0;

  if (!show) {
    return null;
  }

  return (
    <div
      role="progressbar"
      data-slot="refetch-bar"
      aria-label="Updating data in background"
      aria-busy="true"
      className="absolute bottom-0 left-0 right-0 h-0.5 bg-muted-foreground z-20 motion-safe:animate-pulse"
    />
  );
};

export default RefetchBar;
