export function CloseRecommendationIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      className={className}
    >
      <rect
        x="7.25"
        y="12"
        width="9.5"
        height="8.25"
        rx="1.6"
        className="fill-current opacity-20"
      />
      <rect
        x="7.25"
        y="12"
        width="9.5"
        height="8.25"
        rx="1.6"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path
        d="M12 12V9.2"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path
        d="M12 15.6V3.8M12 3.8 8.7 7.1M12 3.8 15.3 7.1"
        stroke="currentColor"
        strokeWidth="1.85"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default CloseRecommendationIcon;
