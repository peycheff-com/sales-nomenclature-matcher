import { describe, expect, it, vi } from "vitest";

import { formatConfidence, formatDate, pluralize } from "./format";

describe("formatConfidence", () => {
  it("formats confidence as a rounded percentage", () => {
    expect(formatConfidence(0.934)).toBe("93%");
    expect(formatConfidence(1)).toBe("100%");
  });

  it("uses an em dash for missing values", () => {
    expect(formatConfidence(null)).toBe("\u2014");
    expect(formatConfidence(undefined)).toBe("\u2014");
  });
});

describe("formatDate", () => {
  it("formats dates with the Russian locale", () => {
    const spy = vi
      .spyOn(Date.prototype, "toLocaleString")
      .mockReturnValue("01.04.2026, 12:30");

    expect(formatDate("2026-04-01T09:30:00.000Z")).toBe("01.04.2026, 12:30");
    expect(spy).toHaveBeenCalledWith("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });

    spy.mockRestore();
  });

  it("uses an em dash for missing dates", () => {
    expect(formatDate(null)).toBe("\u2014");
    expect(formatDate(undefined)).toBe("\u2014");
    expect(formatDate("")).toBe("\u2014");
  });
});

describe("pluralize", () => {
  it("uses Russian plural forms", () => {
    expect(pluralize(1, "товар", "товара", "товаров")).toBe("1 товар");
    expect(pluralize(2, "товар", "товара", "товаров")).toBe("2 товара");
    expect(pluralize(5, "товар", "товара", "товаров")).toBe("5 товаров");
    expect(pluralize(11, "товар", "товара", "товаров")).toBe("11 товаров");
    expect(pluralize(22, "товар", "товара", "товаров")).toBe("22 товара");
  });
});
