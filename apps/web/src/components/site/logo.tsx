import Link from "next/link";

import { cn } from "@/lib/utils";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cn("size-7", className)} aria-hidden>
      <rect width="32" height="32" rx="8" className="fill-primary" />
      <path d="M9 22V10h6.5a6 6 0 0 1 0 12H9Z" fill="none" stroke="white" strokeWidth="2.6" />
      <circle cx="22.5" cy="16" r="2.2" fill="#9fb2ff" />
    </svg>
  );
}

export function Logo({ href = "/", className }: { href?: string; className?: string }) {
  return (
    <Link href={href} className={cn("flex items-center gap-2 font-semibold tracking-tight", className)}>
      <LogoMark />
      <span>DeployMind</span>
    </Link>
  );
}
