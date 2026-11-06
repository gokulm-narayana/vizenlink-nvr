import React from "react";

export const HatchPattern: React.FC<{ id?: string }> = ({ id = "outage-hatch" }) => {
  return (
    <svg className="absolute h-0 w-0 pointer-events-none" aria-hidden="true">
      <defs>
        <pattern
          id={id}
          width="8"
          height="8"
          patternUnits="userSpaceOnUse"
          patternTransform="rotate(45)"
        >
          <line
            x1="0"
            y1="0"
            x2="0"
            y2="8"
            stroke="currentColor"
            strokeWidth="3"
          />
        </pattern>
      </defs>
    </svg>
  );
};
