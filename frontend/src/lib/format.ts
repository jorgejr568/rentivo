const MONTHS_PT: Record<string, string> = {
  "01": "Janeiro",
  "02": "Fevereiro",
  "03": "Março",
  "04": "Abril",
  "05": "Maio",
  "06": "Junho",
  "07": "Julho",
  "08": "Agosto",
  "09": "Setembro",
  "10": "Outubro",
  "11": "Novembro",
  "12": "Dezembro"
};

export function formatBrlInput(centavos: number): string {
  const normalized = Math.trunc(centavos);
  const sign = normalized < 0 ? "-" : "";
  const absolute = Math.abs(normalized);
  const integer = Math.floor(absolute / 100);
  const fraction = absolute % 100;
  const grouped = String(integer).replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${sign}${grouped},${String(fraction).padStart(2, "0")}`;
}

export function formatBrl(centavos: number): string {
  return `R$ ${formatBrlInput(centavos)}`;
}

export function parseBrl(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const normalized = trimmed.includes(",")
    ? trimmed.replaceAll(".", "").replace(",", ".")
    : trimmed;
  if (!/^\d+(?:\.\d+)?$/.test(normalized)) {
    return null;
  }

  const [integerPart, fractionPart = ""] = normalized.split(".");
  let centavos = BigInt(integerPart) * 100n;
  centavos += BigInt((fractionPart.slice(0, 2) || "0").padEnd(2, "0"));
  if ((fractionPart[2] ?? "0") >= "5") {
    centavos += 1n;
  }
  if (centavos > BigInt(Number.MAX_SAFE_INTEGER)) {
    return null;
  }
  return Number(centavos);
}

export function formatMonth(reference: string): string {
  const separator = reference.indexOf("-");
  if (!reference || separator < 0) {
    return reference;
  }
  const year = reference.slice(0, separator);
  const month = reference.slice(separator + 1);
  return `${MONTHS_PT[month] ?? month}/${year}`;
}

export function formatIsoDate(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : value;
}
