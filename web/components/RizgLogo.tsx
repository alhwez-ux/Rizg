import {
  RIZG_ACCENT,
  RIZG_BG,
  RIZG_INK,
  RIZG_INK_SOFT,
  RIZG_MONOGRAM_PATH,
} from "@/lib/rizg-mark";

type RizgLogoProps = {
  size?: number;
  className?: string;
  framed?: boolean;
  title?: string;
};

export function RizgLogo({
  size = 56,
  className = "",
  framed = true,
  title = "رزق",
}: RizgLogoProps) {
  const gradientId = "rizg-mark-silver";

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 128 128"
      fill="none"
      role="img"
      aria-label={title}
      className={className}
    >
      <title>{title}</title>
      {framed ? (
        <>
          <rect width="128" height="128" rx="32" fill={RIZG_BG} />
          <rect
            x="1"
            y="1"
            width="126"
            height="126"
            rx="31"
            stroke="#FFFFFF"
            strokeOpacity="0.08"
          />
        </>
      ) : null}
      <defs>
        <linearGradient
          id={gradientId}
          x1="30"
          y1="24"
          x2="108"
          y2="100"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#F8FAFC" />
          <stop offset="0.5" stopColor={RIZG_INK_SOFT} />
          <stop offset="1" stopColor={RIZG_INK} />
        </linearGradient>
      </defs>
      <path
        d={RIZG_MONOGRAM_PATH}
        stroke={`url(#${gradientId})`}
        strokeWidth="12.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="110" cy="31" r="7" fill={RIZG_ACCENT} />
    </svg>
  );
}
