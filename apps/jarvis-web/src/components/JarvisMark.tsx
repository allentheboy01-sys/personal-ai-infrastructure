export function JarvisMark({ size = 24, className }: { size?: number; className?: string }) {
  return <svg className={className} width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M18.6 16.9A8 8 0 1 0 6.2 18" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    <path d="m15.9 18.6 3.15.35-.45-3.1" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="12" cy="12" r="2.15" fill="currentColor" />
    <path d="M12 7.1V5.4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
  </svg>
}
