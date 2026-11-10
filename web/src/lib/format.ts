// Dates relatives en français : « il y a 12 min », « hier », « 27 oct. ».

const rtf = new Intl.RelativeTimeFormat("fr", { numeric: "auto" });
const dateFmt = new Intl.DateTimeFormat("fr", { day: "numeric", month: "short" });
const timeFmt = new Intl.DateTimeFormat("fr", { hour: "2-digit", minute: "2-digit" });

export function relativeTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const minutes = Math.round((now.getTime() - date.getTime()) / 60_000);
  if (minutes < 1) return "à l’instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.round(hours / 24);
  if (days < 7) return rtf.format(-days, "day");
  return dateFmt.format(date);
}

export function dayAndTime(iso: string, now: Date = new Date()): string {
  const date = new Date(iso);
  const startOf = (d: Date) => new Date(d).setHours(0, 0, 0, 0);
  const days = Math.round((startOf(now) - startOf(date)) / 86_400_000);
  const day = days === 0 ? "aujourd’hui" : days === 1 ? "hier" : dateFmt.format(date);
  return `${day}, ${timeFmt.format(date)}`;
}

/** Heure seule : « 12:45 ». */
export function clockTime(iso: string): string {
  return timeFmt.format(new Date(iso));
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}

// Consommation : montants en dollars (prix de la passerelle), jetons, mois.

const usd = new Intl.NumberFormat("fr", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const usdSmall = new Intl.NumberFormat("fr", { style: "currency", currency: "USD", maximumFractionDigits: 4 });
const compact = new Intl.NumberFormat("fr", { notation: "compact", maximumFractionDigits: 1 });
const monthFmt = new Intl.DateTimeFormat("fr", { month: "long", year: "numeric", timeZone: "UTC" });

/** « 12,40 $US » ; les centimes de centime restent visibles sous 1 $. */
export function dollars(amount: number): string {
  return (amount > 0 && amount < 1 ? usdSmall : usd).format(amount);
}

/** « 12,3 k » jetons. */
export function tokens(count: number): string {
  return compact.format(count);
}

/** « 2026-11 » → « novembre 2026 ». */
export function monthLabel(month: string): string {
  const [year, number] = month.split("-").map(Number);
  return monthFmt.format(new Date(Date.UTC(year, number - 1, 1)));
}

/** Mois voisin : shiftMonth("2026-01", -1) → « 2025-12 ». */
export function shiftMonth(month: string, delta: number): string {
  const [year, number] = month.split("-").map(Number);
  const date = new Date(Date.UTC(year, number - 1 + delta, 1));
  return `${date.getUTCFullYear()}-${String(date.getUTCMonth() + 1).padStart(2, "0")}`;
}

/** Paramètre « mois » d'une URL, s'il est bien formé. */
export function monthParam(value: string | string[] | undefined): string | null {
  return typeof value === "string" && /^\d{4}-(0[1-9]|1[0-2])$/.test(value) ? value : null;
}

/** Mois en cours (UTC, comme les quotas de l'API) : « 2026-11 ». */
export function currentMonth(now: Date = new Date()): string {
  return `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}`;
}
