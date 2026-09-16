import { RIZG_BG, RIZG_DOT, RIZG_INK, RIZG_MONOGRAM_PATH, RIZG_SIZE, RIZG_STROKE_WIDTH } from "@/lib/rizg-mark";
import { toneColor, type MarketTone } from "@/lib/market-tone";

type RizgLogoProps = {
  className?: string;
  iconClassName?: string;
  withWordmark?: boolean;
  title?: string;
  tone?: MarketTone;
};

export function RizgLogo({
  className = "",
  iconClassName = "h-10 w-10",
  withWordmark = true,
  title = "رِزق",
  tone = "flat",
}: RizgLogoProps) {
  const color = toneColor(tone);

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <div
        className={`${iconClassName} flex shrink-0 items-center justify-center rounded-full border-[2.5px] transition-[border-color] duration-500`}
        style={{ backgroundColor: RIZG_BG, borderColor: color }}
        role="img"
        aria-label={title}
      >
        <svg
          viewBox={`0 0 ${RIZG_SIZE} ${RIZG_SIZE}`}
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className="h-[72%] w-[72%]"
          aria-hidden="true"
        >
          <title>{title}</title>
          <path
            d={RIZG_MONOGRAM_PATH}
            stroke={RIZG_INK}
            strokeWidth={RIZG_STROKE_WIDTH}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <circle cx={RIZG_DOT.cx} cy={RIZG_DOT.cy} r={RIZG_DOT.r} fill={RIZG_INK} />
        </svg>
      </div>

      {withWordmark ? (
        <div className="flex flex-col">
          <span className="text-lg font-bold tracking-wide text-zinc-50">رِزق</span>
          <span
            className="text-[10px] font-semibold uppercase tracking-widest transition-colors duration-500"
            style={{ color }}
          >
            RIZG RADAR
          </span>
        </div>
      ) : null}
    </div>
  );
}
