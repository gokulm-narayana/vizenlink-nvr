import * as React from "react"
import { cn } from "@/lib/utils"

import markLight from "@/assets/brand/vizenlink-mark-light.png"
import markDark from "@/assets/brand/vizenlink-mark-dark.png"
import wordmarkLight from "@/assets/brand/vizenlink-wordmark-light.png"
import wordmarkDark from "@/assets/brand/vizenlink-wordmark-dark.png"
import fullLight from "@/assets/brand/vizenlink-full-light.png"
import fullDark from "@/assets/brand/vizenlink-full-dark.png"

export interface BrandLogoProps extends React.ComponentProps<"div"> {
  variant?: "mark" | "lockup" | "full"
}

export function BrandLogo({
  variant = "lockup",
  className,
  ...props
}: BrandLogoProps) {
  if (variant === "mark") {
    return (
      <div
        data-slot="brand-logo"
        data-variant="mark"
        className={cn("inline-flex items-center", className)}
        {...props}
      >
        <img
          src={markLight}
          width={189}
          height={128}
          decoding="async"
          alt=""
          className="h-8 w-auto dark:hidden"
        />
        <img
          src={markDark}
          width={189}
          height={128}
          decoding="async"
          alt=""
          className="hidden h-8 w-auto dark:block"
        />
      </div>
    )
  }

  if (variant === "lockup") {
    return (
      <div
        data-slot="brand-logo"
        data-variant="lockup"
        className={cn("inline-flex items-center gap-2", className)}
        {...props}
      >
        <img
          src={markLight}
          width={189}
          height={128}
          decoding="async"
          alt=""
          className="h-8 w-auto dark:hidden"
        />
        <img
          src={markDark}
          width={189}
          height={128}
          decoding="async"
          alt=""
          className="hidden h-8 w-auto dark:block"
        />
        <img
          src={wordmarkLight}
          width={500}
          height={48}
          decoding="async"
          alt=""
          className="h-3 w-auto dark:hidden"
        />
        <img
          src={wordmarkDark}
          width={500}
          height={48}
          decoding="async"
          alt=""
          className="hidden h-3 w-auto dark:block"
        />
      </div>
    )
  }

  return (
    <div
      data-slot="brand-logo"
      data-variant="full"
      className={cn("inline-flex flex-col items-center", className)}
      {...props}
    >
      <img
        src={fullLight}
        width={627}
        height={480}
        decoding="async"
        alt="VizenLink"
        className="h-20 w-auto min-[480px]:h-30 max-[640px]:h-20 dark:hidden"
      />
      <img
        src={fullDark}
        width={627}
        height={480}
        decoding="async"
        alt="VizenLink"
        className="hidden h-20 w-auto min-[480px]:h-30 max-[640px]:h-20 dark:block"
      />
    </div>
  )
}
