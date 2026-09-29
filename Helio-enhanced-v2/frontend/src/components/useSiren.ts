import { useEffect, useState } from "react";

type AudioWindow = Window & { webkitAudioContext?: typeof AudioContext };

/**
 * Plays a two-tone emergency siren for as long as `active` is true and the
 * siren is not muted. Uses the Web Audio API, so no audio file is needed.
 *
 * Returns `blocked: true` if the browser refused to start audio (autoplay
 * policy), so the UI can tell the doctor to click once to enable sound.
 */
export function useSiren(active: boolean, muted: boolean) {
  const [blocked, setBlocked] = useState(false);

  useEffect(() => {
    if (!active || muted) return;

    const Ctx = window.AudioContext || (window as AudioWindow).webkitAudioContext;
    if (!Ctx) return;

    const ctx = new Ctx();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sawtooth";
    gain.gain.value = 0.14;
    osc.frequency.value = 650;
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.start();

    let high = true;
    const sweep = () => {
      const t = ctx.currentTime;
      osc.frequency.cancelScheduledValues(t);
      osc.frequency.setValueAtTime(osc.frequency.value, t);
      osc.frequency.linearRampToValueAtTime(high ? 1100 : 650, t + 0.55);
      high = !high;
    };
    sweep();
    const timer = window.setInterval(sweep, 600);

    ctx.resume().then(
      () => setBlocked(ctx.state !== "running"),
      () => setBlocked(true),
    );

    // If the browser started the context suspended, the first click anywhere
    // lets the siren begin.
    const unlock = () => {
      ctx.resume().then(() => setBlocked(ctx.state !== "running"));
    };
    window.addEventListener("pointerdown", unlock);
    window.addEventListener("keydown", unlock);

    return () => {
      window.clearInterval(timer);
      window.removeEventListener("pointerdown", unlock);
      window.removeEventListener("keydown", unlock);
      try {
        osc.stop();
      } catch {
        /* already stopped */
      }
      void ctx.close();
    };
  }, [active, muted]);

  return { blocked: active && !muted && blocked };
}
