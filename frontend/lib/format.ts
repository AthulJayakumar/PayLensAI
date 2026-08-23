/** Presentation-only formatters; analytics values remain exact decimal strings from the API. */

export function formatRate(value: string | null | undefined): string {
  if (value == null) return "Not available";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

export function formatMoney(value: string, currency: string): string {
  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Number(value));
}

export function formatInteger(value: number): string {
  return new Intl.NumberFormat("en-GB").format(value);
}

export function humanise(value: string): string {
  return value.split("_").map((word) => {
    if (word === word.toUpperCase() && word.length <= 5) return word;
    return word.toLowerCase().replace(/^\w/, (letter) => letter.toUpperCase());
  }).join(" ");
}

export function segmentLabel(segment: Record<string, string>): string {
  // A stable dimension order makes equivalent segment labels consistent across every view.
  const order = ["issuer_country", "card_network", "payment_method", "provider", "currency"];
  return order.filter((key) => segment[key]).map((key) => humanise(segment[key])).join(" · ") || "Overall payments";
}
