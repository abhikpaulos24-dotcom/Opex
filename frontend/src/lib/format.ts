// Indian number formatting: ₹ with lakh (L) and crore (Cr).
export function inr(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  const sign = value < 0 ? "−" : "";
  const v = Math.abs(value);
  if (v >= 1e7) return `${sign}₹${(v / 1e7).toFixed(digits)} Cr`;
  if (v >= 1e5) return `${sign}₹${(v / 1e5).toFixed(digits)} L`;
  if (v >= 1e3) return `${sign}₹${(v / 1e3).toFixed(digits === 1 ? 0 : digits)}K`;
  return `${sign}₹${v.toFixed(0)}`;
}

export function pct(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  if (value >= 0.995 && digits === 0) return ">99%";
  if (value > 0 && value < 0.005 && digits === 0) return "<1%";
  return `${(value * 100).toFixed(digits)}%`;
}

export function num(value: number | null | undefined, digits = 0): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "–";
  return value.toLocaleString("en-IN", { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

export function hours(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  if (value < 1) return `${Math.round(value * 60)} min`;
  return `${value.toFixed(1)} h`;
}

export function titleCase(text: string): string {
  return text.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());
}

/** "3 of 4" as a percentage. Unlike pct(), a whole count shows as exactly 100% (not ">99%"). */
export function share(part: number, total: number): string {
  return total ? `${Math.round((100 * part) / total)}%` : "–";
}
