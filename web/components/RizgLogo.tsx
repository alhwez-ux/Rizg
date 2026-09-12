import {
  RIZG_ACCENT,
  RIZG_BG,
  RIZG_DOT,
  RIZG_INK,
  RIZG_MONOGRAM_PATH,
  RIZG_SIZE,
  RIZG_STROKE_WIDTH,
} from "@/lib/rizg-mark";
import { TASI_DOWN_FILL, TASI_UP_FILL, type MarketTone } from "@/lib/market-tone";

type RizgLogoProps = {
  className?: string;
  iconClassName?: string;
  withWordmark?: boolean;
  title?: string;
  tone?: MarketTone;
};

const FILL: Record<MarketTone, string> = {
  up: TASI_UP_FILL,
  down: TASI_DOWN_FILL,
  flat: RIZG_BG,
};

const WORDMARK: Record<MarketTone, string> = {
  up: "text-emerald-400",
  down: "text-rose-400",
  flat: "text-zinc-400",
};

export function RizgLogo({
  className = "",
  iconClassName = "h-10 w-10",
  withWordmark = true,
  title = "رِزق",
  tone = "flat",
}: RizgLogoProps) {
  const fill = FILL[tone];
  const accent = tone === "flat" ? RIZG_ACCENT : RIZG_INK;

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <svg
        viewBox={`0 0 ${RIZG_SIZE} ${RIZG_SIZE}`}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`${iconClassName} shrink-0 transition-colors duration-500`}
        role="img"
        aria-label={title}
      >
        <title>{title}</title>
        <rect width={RIZG_SIZE} height={RIZG_SIZE} rx="12" fill={fill} />
        <path
          d={RIZG_MONOGRAM_PATH}
          stroke={RIZG_INK}
          strokeWidth={RIZG_STROKE_WIDTH}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={RIZG_DOT.cx} cy={RIZG_DOT.cy} r={RIZG_DOT.r} fill={accent} />
      </svg>

      {withWordmark ? (
        <div className="flex flex-col">
          <span className="text-lg font-bold tracking-wide text-white">رِزق</span>
          <span
            className={`text-[10px] font-semibold uppercase tracking-widest transition-colors duration-500 ${WORDMARK[tone]}`}
          >
            RIZG RADAR
          </span>
        </div>
      ) : null}
    </div>
  );
}
