export function SmartMoneyIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true" className={className}>
      <path
        d="M4.8 10.2 12 5.6l7.2 4.6"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path d="M6.4 10.2V18.4H17.6V10.2" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" />
      <path d="M3.7 18.4h16.6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M9.1 18.4V13.4h2.2V18.4M12.7 18.4V13.4h2.2V18.4" stroke="currentColor" strokeWidth="1.55" />
      <circle cx="12" cy="8.7" r="1.15" className="fill-current" />
    </svg>
  );
}

export default SmartMoneyIcon;
