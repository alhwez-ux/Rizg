import Image from "next/image";

export function RizgLogo({
  size = 56,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <Image
      src="/icons/icon-192.png"
      alt=""
      width={size}
      height={size}
      unoptimized
      priority
      className={`rounded-[14px] ring-1 ring-white/10 ${className}`}
    />
  );
}
