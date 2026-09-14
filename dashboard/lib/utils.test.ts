import { describe, expect, it } from "vitest";
import { cn, formatDate } from "./utils";

describe("cn", () => {
  it("merges class names and resolves Tailwind conflicts (last one wins)", () => {
    expect(cn("px-2 py-1", "px-4")).toBe("py-1 px-4");
  });

  it("drops falsy values", () => {
    expect(cn("a", false && "b", null, undefined, "c")).toBe("a c");
  });
});

describe("formatDate", () => {
  it("renders month/day/hour/minute, not seconds or year", () => {
    const result = formatDate("2026-03-15T14:30:00Z");
    expect(result).toMatch(/Mar/);
    expect(result).toMatch(/15/);
    expect(result).not.toMatch(/2026/);
  });
});
