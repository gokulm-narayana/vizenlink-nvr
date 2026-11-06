import React, { useEffect } from "react";
import { useUiStore, resolvedTheme } from "@/stores/ui";

export const ThemeSync: React.FC = () => {
  const theme = useUiStore((s) => s.theme);

  useEffect(() => {
    const applyTheme = () => {
      const resolved = resolvedTheme(theme);
      if (resolved === "dark") {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    };

    applyTheme();

    if (theme === "system" && typeof window !== "undefined" && window.matchMedia) {
      const media = window.matchMedia("(prefers-color-scheme: dark)");
      const handler = () => applyTheme();
      if (media.addEventListener) {
        media.addEventListener("change", handler);
        return () => media.removeEventListener("change", handler);
      } else if (media.addListener) {
        media.addListener(handler);
        return () => media.removeListener(handler);
      }
    }
  }, [theme]);

  return null;
};

export default ThemeSync;
