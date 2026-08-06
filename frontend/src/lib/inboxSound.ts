const SOUND_KEY = "ops-hub-inbox-sound";

export function isInboxSoundEnabled(): boolean {
  try {
    const v = localStorage.getItem(SOUND_KEY);
    // default: ON
    return v !== "off";
  } catch {
    return true;
  }
}

export function setInboxSoundEnabled(on: boolean): void {
  try {
    localStorage.setItem(SOUND_KEY, on ? "on" : "off");
  } catch {
    /* private mode */
  }
}

/** Beep corto suave (Web Audio). Falla en silencio si el browser bloquea audio. */
export function playHandoffBeep(): void {
  if (typeof window === "undefined") return;
  if (!isInboxSoundEnabled()) return;
  try {
    const Ctx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = 880;
    gain.gain.value = 0.0001;
    osc.connect(gain);
    gain.connect(ctx.destination);
    const t0 = ctx.currentTime;
    gain.gain.exponentialRampToValueAtTime(0.08, t0 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.22);
    osc.start(t0);
    osc.stop(t0 + 0.25);
    osc.onended = () => {
      void ctx.close().catch(() => {});
    };
  } catch {
    /* autoplay bloqueado u otro error */
  }
}
