import React, { useMemo } from "react";
import { encode } from "uqr";
import { cn } from "cn";

export interface QrCodeProps {
  payload: string;
  dimmed?: boolean;
  className?: string;
}

export const QrCode: React.FC<QrCodeProps> = ({
  payload,
  dimmed = false,
  className,
}) => {
  const qr = useMemo(() => {
    try {
      return encode(payload, { ecc: "M", border: 2 });
    } catch {
      return null;
    }
  }, [payload]);

  if (!qr) {
    return (
      <div
        className={cn(
          "flex aspect-square w-full max-w-60 items-center justify-center rounded-lg bg-white p-2 text-center text-xs text-black",
          className
        )}
      >
        Failed to generate QR code
      </div>
    );
  }

  // Collect dark cells
  const darkCells: Array<{ x: number; y: number }> = [];
  for (let y = 0; y < qr.size; y++) {
    for (let x = 0; x < qr.size; x++) {
      if (qr.data[y]?.[x]) {
        darkCells.push({ x, y });
      }
    }
  }

  return (
    <div
      className={cn(
        "inline-flex w-full max-w-60 items-center justify-center rounded-lg bg-white p-2 transition-opacity duration-200",
        dimmed && "opacity-30",
        className
      )}
    >
      <svg
        role="img"
        aria-label="Pairing QR code"
        viewBox={`0 0 ${qr.size} ${qr.size}`}
        width={224}
        height={224}
        className="block h-auto w-full"
      >
        {/* White background */}
        <rect width={qr.size} height={qr.size} fill="white" />

        {/* Dark modules */}
        {darkCells.map(({ x, y }) => (
          <rect
            key={`${x}-${y}`}
            x={x}
            y={y}
            width={1}
            height={1}
            fill="black"
          />
        ))}
      </svg>
    </div>
  );
};
