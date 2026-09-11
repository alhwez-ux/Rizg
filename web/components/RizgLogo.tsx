import {
  RIZG_ACCENT,
  RIZG_BG,
  RIZG_DOT,
  RIZG_INK,
  RIZG_MONOGRAM_PATH,
  RIZG_SIZE,
  RIZG_STROKE_WIDTH,
} from "@/lib/rizg-mark";

type RizgLogoProps = {
  className?: string;
  iconClassName?: string;
  withWordmark?: boolean;
  title?: string;
};

export function RizgLogo({
  className = "",
  iconClassName = "h-10 w-10",
  withWordmark = true,
  title = "رِزق",
}: RizgLogoProps) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <svg
        viewBox={`0 0 ${RIZG_SIZE} ${RIZG_SIZE}`}
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
        className={`${iconClassName} shrink-0`}
        role="img"
        aria-label={title}
      >
        <title>{title}</title>
        <rect width={RIZG_SIZE} height={RIZG_SIZE} rx="12" fill={RIZG_BG} />
        <path
          d={RIZG_MONOGRAM_PATH}
          stroke={RIZG_INK}
          strokeWidth={RIZG_STROKE_WIDTH}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <circle cx={RIZG_DOT.cx} cy={RIZG_DOT.cy} r={RIZG_DOT.r} fill={RIZG_ACCENT} />
      </svg>

      {withWordmark ? (
        <div className="flex flex-col">
          <span className="text-lg font-bold tracking-wide text-white">رِزق</span>
          <span className="text-[10px] font-semibold uppercase tracking-widest text-emerald-400">
            RIZG RADAR
          </span>
        </div>
      ) : null}
    </div>
  );
}
