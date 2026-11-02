import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(v?: string | null, opts: Intl.DateTimeFormatOptions = { dateStyle: "medium" }) {
  if (!v) return "—";
  return new Intl.DateTimeFormat("en-GB", opts).format(new Date(v));
}

export function formatDateTime(v?: string | null) {
  return formatDate(v, { dateStyle: "medium", timeStyle: "short" });
}

export function relativeTime(v?: string | null) {
  if (!v) return "—";
  const diff = (Date.now() - new Date(v).getTime()) / 1000;
  const abs = Math.abs(diff);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [["year", 31536000], ["month", 2592000], ["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [unit, secs] of units) if (abs >= secs) return rtf.format(-Math.round(diff / secs), unit);
  return "just now";
}

export function money(v?: number | string | null, currency = "GBP") {
  if (v === null || v === undefined || v === "") return "—";
  return new Intl.NumberFormat("en-GB", { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(v));
}

export function usd(v?: number | null, digits = 2) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: digits, maximumFractionDigits: Math.max(digits, 4) }).format(v);
}

export function compact(v?: number | null) {
  if (v === null || v === undefined) return "—";
  return new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 }).format(v);
}

export function pct(v?: number | null, digits = 0) {
  if (v === null || v === undefined) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}
