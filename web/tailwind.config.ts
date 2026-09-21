import type { Config } from "tailwindcss";

const rgb = (channel: string) => `rgb(var(${channel}) / <alpha-value>)`;

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./hooks/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        zinc: {
          50: rgb("--zinc-50"),
          100: rgb("--zinc-100"),
          200: rgb("--zinc-200"),
          300: rgb("--zinc-300"),
          400: rgb("--zinc-400"),
          500: rgb("--zinc-500"),
          600: rgb("--zinc-600"),
          700: rgb("--zinc-700"),
          800: rgb("--zinc-800"),
          900: rgb("--zinc-900"),
          950: rgb("--zinc-950"),
        },
        tape: {
          bg: rgb("--tape-bg"),
          panel: rgb("--tape-panel"),
          line: rgb("--tape-line"),
        },
      },
      boxShadow: {
        glow: "var(--shadow-glow)",
      },
      keyframes: {
        pulseDot: {
          "0%, 100%": { opacity: "1", transform: "scale(1)" },
          "50%": { opacity: "0.45", transform: "scale(0.85)" },
        },
        flow: {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "200% 50%" },
        },
        toastIn: {
          "0%": { opacity: "0", transform: "translateY(-12px) scale(0.98)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        revealIn: {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        ticker: {
          "0%": { transform: "translateX(-50%)" },
          "100%": { transform: "translateX(0)" },
        },
        rocketPulse: {
          "0%, 100%": { transform: "scale(1) translateY(0)", filter: "drop-shadow(0 0 4px rgba(250,204,21,0.35))" },
          "50%": { transform: "scale(1.22) translateY(-3px)", filter: "drop-shadow(0 0 14px rgba(250,204,21,0.95))" },
        },
        lightningPulse: {
          "0%, 100%": { opacity: "1", transform: "scale(1) rotate(0deg)" },
          "50%": { opacity: "0.55", transform: "scale(1.28) rotate(-8deg)" },
        },
      },
      animation: {
        pulseDot: "pulseDot 1.4s ease-in-out infinite",
        flow: "flow 2.8s linear infinite",
        toastIn: "toastIn 0.35s ease-out",
        revealIn: "revealIn 0.45s ease-out",
        fadeIn: "fadeIn 0.4s ease-out",
        ticker: "ticker 2400s linear infinite",
        rocketPulse: "rocketPulse 1.15s ease-in-out infinite",
        lightningPulse: "lightningPulse 1.05s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};

export default config;
