import React, { useEffect, useRef } from "react";
import { useNavigate } from "react-router";

export const Shortcuts: React.FC = () => {
  const navigate = useNavigate();
  const lastGTimeRef = useRef<number>(0);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) {
        return;
      }

      const target = e.target as HTMLElement | null;
      if (
        target &&
        typeof target.getAttribute === "function" &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable ||
          target.getAttribute("contenteditable") === "true")
      ) {
        return;
      }

      const key = e.key.toLowerCase();
      const now = Date.now();

      if (key === "g") {
        if (now - lastGTimeRef.current <= 1500) {
          // 'g' then 'g' within 1.5s -> gallery
          lastGTimeRef.current = 0;
          void navigate("/gallery");
        } else {
          lastGTimeRef.current = now;
        }
        return;
      }

      if (now - lastGTimeRef.current <= 1500) {
        if (key === "l") {
          lastGTimeRef.current = 0;
          void navigate("/live");
        } else if (key === "p") {
          lastGTimeRef.current = 0;
          void navigate("/playback");
        } else if (key === "e") {
          lastGTimeRef.current = 0;
          void navigate("/events");
        } else if (key === "d") {
          lastGTimeRef.current = 0;
          void navigate("/");
        } else {
          lastGTimeRef.current = 0;
        }
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [navigate]);

  return null;
};

export default Shortcuts;