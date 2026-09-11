let audioContext: AudioContext | null = null;
let unlocked = false;

function context(): AudioContext | null {
  if (typeof window === "undefined") return null;
  const Ctor = window.AudioContext || (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!Ctor) return null;
  if (!audioContext) audioContext = new Ctor();
  return audioContext;
}

export async function unlockAudio(): Promise<boolean> {
  const ctx = context();
  if (!ctx) return false;
  if (ctx.state === "suspended") {
    try {
      await ctx.resume();
    } catch {
      return false;
    }
  }
  unlocked = ctx.state === "running";
  return unlocked;
}

export function isAudioUnlocked(): boolean {
  return unlocked;
}

function tone(ctx: AudioContext, frequency: number, start: number, duration: number, gain = 0.09) {
  const oscillator = ctx.createOscillator();
  const amp = ctx.createGain();
  oscillator.type = "sine";
  oscillator.frequency.setValueAtTime(frequency, start);
  amp.gain.setValueAtTime(0.0001, start);
  amp.gain.exponentialRampToValueAtTime(gain, start + 0.02);
  amp.gain.exponentialRampToValueAtTime(0.0001, start + duration);
  oscillator.connect(amp);
  amp.connect(ctx.destination);
  oscillator.start(start);
  oscillator.stop(start + duration + 0.02);
}

export function playSignalSound(kind: "entry" | "exit"): void {
  const ctx = context();
  if (!ctx || ctx.state !== "running") return;
  const now = ctx.currentTime;
  if (kind === "entry") {
    tone(ctx, 660, now, 0.12, 0.1);
    tone(ctx, 880, now + 0.13, 0.16, 0.1);
  } else {
    tone(ctx, 420, now, 0.16, 0.11);
    tone(ctx, 280, now + 0.14, 0.22, 0.1);
  }
}
