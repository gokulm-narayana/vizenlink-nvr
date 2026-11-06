import { useState, useRef, useCallback, useEffect } from "react";
import type { TimelineSegment } from "@/lib/timeline";
import { getZoneOffsetMs } from "@/lib/time";

export function toDatetimeLocal(d: Date, zone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).formatToParts(d);

  let year = "",
    month = "",
    day = "",
    hour = "",
    minute = "",
    second = "";
  for (const p of parts) {
    if (p.type === "year") year = p.value;
    else if (p.type === "month") month = p.value;
    else if (p.type === "day") day = p.value;
    else if (p.type === "hour") hour = p.value === "24" ? "00" : p.value;
    else if (p.type === "minute") minute = p.value;
    else if (p.type === "second") second = p.value;
  }
  return `${year}-${month}-${day}T${hour}:${minute}:${second}`;
}

export function parseDatetimeLocal(str: string, zone: string): Date | null {
  const match = str.trim().match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (!match) return null;
  const [_, y, m, d, hh, mm, ss] = match;
  const year = Number(y);
  const month = Number(m);
  const day = Number(d);
  const hour = Number(hh);
  const minute = Number(mm);
  const second = ss ? Number(ss) : 0;
  if (hour < 0 || hour > 23 || minute < 0 || minute > 59 || second < 0 || second > 59) return null;

  const targetUtc = Date.UTC(year, month - 1, day, hour, minute, second);
  const offset1 = getZoneOffsetMs(new Date(targetUtc), zone);
  const guess = new Date(targetUtc - offset1);
  const offset2 = getZoneOffsetMs(guess, zone);
  return new Date(targetUtc - offset2);
}

export function parseTimeToDate(dayIso: string, timeStr: string, zone: string): Date | null {
  const match = timeStr.trim().match(/^(\d{1,2}):(\d{2})(?::(\d{2}))?$/);
  if (!match) return null;
  const hours = parseInt(match[1], 10);
  const minutes = parseInt(match[2], 10);
  const seconds = match[3] ? parseInt(match[3], 10) : 0;
  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59 || seconds < 0 || seconds > 59) {
    return null;
  }
  const [year, month, day] = dayIso.split("-").map(Number);
  const targetUtc = Date.UTC(year, month - 1, day, hours, minutes, seconds);
  const offset1 = getZoneOffsetMs(new Date(targetUtc), zone);
  const guess = new Date(targetUtc - offset1);
  const offset2 = getZoneOffsetMs(guess, zone);
  return new Date(targetUtc - offset2);
}

export function findCoveringOrNextSegment(
  target: Date,
  segments: TimelineSegment[]
): { covering: TimelineSegment | null; next: TimelineSegment | null } {
  const targetMs = target.getTime();
  let covering: TimelineSegment | null = null;
  let next: TimelineSegment | null = null;

  for (const seg of segments) {
    const sMs = new Date(seg.start_time).getTime();
    const eMs = new Date(seg.end_time).getTime();

    if (targetMs >= sMs && targetMs <= eMs) {
      covering = seg;
      break;
    }
    if (sMs > targetMs) {
      if (!next || sMs < new Date(next.start_time).getTime()) {
        next = seg;
      }
    }
  }

  return { covering, next };
}

export interface UsePlaybackEngineOptions {
  videoRef: React.RefObject<HTMLVideoElement | null>;
  segments: TimelineSegment[];
  initialTime?: Date;
  onTimeChange?: (time: Date) => void;
}

export function usePlaybackEngine({
  videoRef,
  segments,
  initialTime,
  onTimeChange,
}: UsePlaybackEngineOptions) {
  const [currentTime, setCurrentTime] = useState<Date>(() => initialTime || new Date());
  const [isPlaying, setIsPlaying] = useState(false);
  const [playbackRate, setPlaybackRateState] = useState(1);
  const [isMuted, setIsMutedState] = useState(true);
  const [activeSegment, setActiveSegment] = useState<TimelineSegment | null>(null);

  const isPlayingRef = useRef(isPlaying);
  isPlayingRef.current = isPlaying;

  const syncPlaybackPosition = useCallback(
    (target: Date, autoPlay: boolean = false) => {
      const { covering, next } = findCoveringOrNextSegment(target, segments);

      if (covering) {
        setActiveSegment(covering);
        setCurrentTime(target);
        onTimeChange?.(target);

        if (videoRef.current) {
          const segStartMs = new Date(covering.start_time).getTime();
          const targetOffsetSec = Math.max(0, (target.getTime() - segStartMs) / 1000);
          const srcUrl = `/api/v1/playback/segment/${covering.id}`;

          if (!videoRef.current.src.endsWith(srcUrl)) {
            videoRef.current.src = srcUrl;
            videoRef.current.currentTime = targetOffsetSec;
            if (autoPlay) {
              videoRef.current
                .play()
                ?.then(() => setIsPlaying(true))
                .catch(() => setIsPlaying(false));
            }
          } else {
            if (Math.abs(videoRef.current.currentTime - targetOffsetSec) > 0.5) {
              videoRef.current.currentTime = targetOffsetSec;
            }
            if (autoPlay && videoRef.current.paused) {
              videoRef.current
                .play()
                ?.then(() => setIsPlaying(true))
                .catch(() => setIsPlaying(false));
            }
          }
        }
      } else if (next) {
        // Gap skipping: advance smoothly to next segment start
        const nextStart = new Date(next.start_time);
        setActiveSegment(next);
        setCurrentTime(nextStart);
        onTimeChange?.(nextStart);

        if (videoRef.current) {
          videoRef.current.src = `/api/v1/playback/segment/${next.id}`;
          videoRef.current.currentTime = 0;
          if (autoPlay) {
            videoRef.current
              .play()
              ?.then(() => setIsPlaying(true))
              .catch(() => setIsPlaying(false));
          }
        }
      } else {
        // No footage available forward
        setActiveSegment(null);
        setCurrentTime(target);
        onTimeChange?.(target);
        if (videoRef.current) {
          videoRef.current.pause();
        }
        setIsPlaying(false);
      }
    },
    [segments, onTimeChange, videoRef]
  );

  // Sync to initialTime or segments change
  const prevSegmentsRef = useRef(segments);
  useEffect(() => {
    if (segments !== prevSegmentsRef.current) {
      prevSegmentsRef.current = segments;
      if (segments.length > 0) {
        syncPlaybackPosition(currentTime, isPlayingRef.current);
      }
    }
  }, [segments, currentTime, syncPlaybackPosition]);

  const prevInitialTimeRef = useRef<number | undefined>(initialTime?.getTime());
  useEffect(() => {
    if (initialTime && initialTime.getTime() !== prevInitialTimeRef.current) {
      prevInitialTimeRef.current = initialTime.getTime();
      syncPlaybackPosition(initialTime, isPlayingRef.current);
    }
  }, [initialTime, syncPlaybackPosition]);

  const handleTimeUpdate = useCallback(() => {
    if (!videoRef.current || !activeSegment) return;
    const segStartMs = new Date(activeSegment.start_time).getTime();
    const currentMs = segStartMs + videoRef.current.currentTime * 1000;
    const updated = new Date(currentMs);
    setCurrentTime(updated);
    onTimeChange?.(updated);
  }, [activeSegment, onTimeChange, videoRef]);

  const handleEnded = useCallback(() => {
    if (!activeSegment) return;
    const segEnd = new Date(activeSegment.end_time);
    syncPlaybackPosition(new Date(segEnd.getTime() + 100), true);
  }, [activeSegment, syncPlaybackPosition]);

  const seek = useCallback(
    (target: Date, autoPlay: boolean = isPlayingRef.current) => {
      syncPlaybackPosition(target, autoPlay);
    },
    [syncPlaybackPosition]
  );

  const play = useCallback(() => {
    if (!videoRef.current) return;
    if (!activeSegment) {
      if (segments.length > 0) {
        syncPlaybackPosition(new Date(segments[0].start_time), true);
      }
    } else {
      videoRef.current
        .play()
        ?.then(() => setIsPlaying(true))
        .catch(() => setIsPlaying(false));
    }
  }, [activeSegment, segments, syncPlaybackPosition, videoRef]);

  const pause = useCallback(() => {
    if (videoRef.current) {
      videoRef.current.pause();
    }
    setIsPlaying(false);
  }, [videoRef]);

  const togglePlay = useCallback(() => {
    if (isPlaying) {
      pause();
    } else {
      play();
    }
  }, [isPlaying, pause, play]);

  const skip = useCallback(
    (seconds: number) => {
      const nextTime = new Date(currentTime.getTime() + seconds * 1000);
      syncPlaybackPosition(nextTime, isPlayingRef.current);
    },
    [currentTime, syncPlaybackPosition]
  );

  const setPlaybackRate = useCallback(
    (rate: number) => {
      setPlaybackRateState(rate);
      if (videoRef.current) {
        videoRef.current.playbackRate = rate;
      }
    },
    [videoRef]
  );

  const toggleMute = useCallback(() => {
    setIsMutedState((prev) => {
      const next = !prev;
      if (videoRef.current) {
        videoRef.current.muted = next;
      }
      return next;
    });
  }, [videoRef]);

  const setMuted = useCallback(
    (muted: boolean) => {
      setIsMutedState(muted);
      if (videoRef.current) {
        videoRef.current.muted = muted;
      }
    },
    [videoRef]
  );

  return {
    currentTime,
    setCurrentTime,
    isPlaying,
    playbackRate,
    isMuted,
    activeSegment,
    hasActiveSegment: activeSegment !== null,
    seek,
    play,
    pause,
    togglePlay,
    skip,
    setPlaybackRate,
    toggleMute,
    setMuted,
    handleTimeUpdate,
    handleEnded,
  };
}
