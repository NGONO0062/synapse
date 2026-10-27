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

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();
}
