import { useEffect, useState, type RefObject } from "react";

export function useFullscreenControls(target: RefObject<HTMLElement | null>) {
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [controlsVisible, setControlsVisible] = useState(true);

  // Fullscreen state is read from the document, not from listeners on the element: the
  // element often does not exist on the first render (Live View shows a loading state
  // first), and an effect that bailed out then never noticed fullscreen at all.
  useEffect(() => {
    const fullscreenChanged = () => {
      const element = target.current;
      const fsEl =
        document.fullscreenElement ??
        (document as unknown as { webkitFullscreenElement?: Element | null }).webkitFullscreenElement ??
        null;
      setIsFullscreen(Boolean(element) && fsEl === element);
    };
    document.addEventListener("fullscreenchange", fullscreenChanged);
    document.addEventListener("webkitfullscreenchange", fullscreenChanged);
    fullscreenChanged();
    return () => {
      document.removeEventListener("fullscreenchange", fullscreenChanged);
      document.removeEventListener("webkitfullscreenchange", fullscreenChanged);
    };
  }, [target]);

  // Controls hide after 3 s without input, only while fullscreen.
  useEffect(() => {
    const element = target.current;
    setControlsVisible(true);
    if (!isFullscreen || !element) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const hide = () => {
      // Keep keyboard navigation usable while a control has visible focus.
      if (element.querySelector("[data-video-chrome] :focus-visible")) {
        timer = setTimeout(hide, 3000);
        return;
      }
      setControlsVisible(false);
    };
    const reveal = () => {
      setControlsVisible(true);
      clearTimeout(timer);
      timer = setTimeout(hide, 3000);
    };
    timer = setTimeout(hide, 3000);
    element.addEventListener("pointermove", reveal);
    element.addEventListener("pointerdown", reveal);
    element.addEventListener("keydown", reveal);
    element.addEventListener("wheel", reveal, { passive: true });
    return () => {
      clearTimeout(timer);
      element.removeEventListener("pointermove", reveal);
      element.removeEventListener("pointerdown", reveal);
      element.removeEventListener("keydown", reveal);
      element.removeEventListener("wheel", reveal);
    };
  }, [isFullscreen, target]);

  return { isFullscreen, controlsVisible };
}
