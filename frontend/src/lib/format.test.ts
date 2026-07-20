import { formatBrl, formatBrlInput, formatIsoDate, formatMonth, parseBrl } from "./format";

describe("BRL formatting", () => {
  it.each([
    [285000, "R$ 2.850,00"],
    [0, "R$ 0,00"],
    [-150, "R$ -1,50"]
  ])("formats %i centavos", (centavos, expected) => {
    expect(formatBrl(centavos)).toBe(expected);
  });

  it("formats form values without the currency prefix", () => {
    expect(formatBrlInput(123456789)).toBe("1.234.567,89");
  });

  it.each([
    ["2850", 285000],
    ["2850.00", 285000],
    ["2.850,00", 285000],
    ["2850,50", 285050],
    ["0,015", 2],
    ["0,025", 3],
    ["0,005", 1],
    ["1.234.567,89", 123456789],
    ["  100  ", 10000],
    ["0", 0]
  ])("parses %s with decimal half-up rounding", (value, expected) => {
    expect(parseBrl(value)).toBe(expected);
  });

  it.each(["", "   ", "abc", "-2850,00", "1,2,3", "90071992547410.00"])("rejects invalid value %j", (value) => {
    expect(parseBrl(value)).toBeNull();
  });
});

describe("date formatting", () => {
  it.each([
    ["2025-03", "Março/2025"],
    ["2024-01", "Janeiro/2024"],
    ["2025-99", "99/2025"],
    ["202503", "202503"],
    ["", ""]
  ])("formats month reference %j", (value, expected) => {
    expect(formatMonth(value)).toBe(expected);
  });

  it.each([
    ["2026-07-18", "18/07/2026"],
    ["", ""],
    [null, ""],
    ["invalid", "invalid"]
  ])("formats ISO date %j without timezone drift", (value, expected) => {
    expect(formatIsoDate(value)).toBe(expected);
  });
});
