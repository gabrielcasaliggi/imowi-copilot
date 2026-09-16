import { useCallback, useEffect, useRef, useState } from "react";

import type { VoicePhase } from "../types";

const MAX_SECONDS = 45;

type Recording = import("expo-av").Audio.Recording;

export function formatVoiceClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
}

async function unload(rec: Recording | null) {
  if (!rec) return;
  try {
    await rec.stopAndUnloadAsync();
  } catch {
    /* already unloaded or never started */
  }
}

export function useVoiceRecorder() {
  const recRef = useRef<Recording | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);
  const [phase, setPhase] = useState<VoicePhase>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");

  const clearTick = () => {
    if (tickRef.current) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      clearTick();
      const rec = recRef.current;
      recRef.current = null;
      void unload(rec);
    };
  }, []);

  const start = useCallback(async () => {
    if (phase !== "idle") return;
    setError("");
    setSeconds(0);
    try {
      const { Audio } = await import("expo-av");
      const perm = await Audio.requestPermissionsAsync();
      if (!perm.granted) {
        setError(
          perm.canAskAgain
            ? "Necesitamos acceso al micrófono para enviar mensajes de voz."
            : "El micrófono está bloqueado. Activalo desde Ajustes para enviar mensajes de voz.",
        );
        return;
      }
      await Audio.setAudioModeAsync({
        allowsRecordingIOS: true,
        playsInSilentModeIOS: true,
        staysActiveInBackground: false,
        shouldDuckAndroid: true,
        playThroughEarpieceAndroid: false,
      });
      const { recording } = await Audio.Recording.createAsync(
        Audio.RecordingOptionsPresets.HIGH_QUALITY,
      );
      if (!mountedRef.current) {
        await unload(recording);
        return;
      }
      recRef.current = recording;
      setPhase("recording");
      tickRef.current = setInterval(() => {
        setSeconds((n) => n + 1);
      }, 1000);
    } catch {
      clearTick();
      const rec = recRef.current;
      recRef.current = null;
      await unload(rec);
      if (mountedRef.current) {
        setPhase("idle");
        setError("No pudimos iniciar la grabación. Intentá nuevamente.");
      }
    }
  }, [phase]);

  const stop = useCallback(async (): Promise<string | null> => {
    if (phase !== "recording") return null;
    clearTick();
    const rec = recRef.current;
    recRef.current = null;
    try {
      if (rec) await rec.stopAndUnloadAsync();
      const uri = rec?.getURI() || null;
      setPhase("idle");
      setSeconds(0);
      return uri;
    } catch {
      await unload(rec);
      setPhase("idle");
      setError("No pudimos guardar el audio. Intentá nuevamente.");
      return null;
    }
  }, [phase]);

  const cancel = useCallback(async () => {
    if (phase !== "recording") return;
    clearTick();
    const rec = recRef.current;
    recRef.current = null;
    setPhase("idle");
    setSeconds(0);
    await unload(rec);
  }, [phase]);

  return {
    phase,
    seconds,
    error,
    setError,
    start,
    stop,
    cancel,
    maxReached: phase === "recording" && seconds >= MAX_SECONDS,
  };
}
