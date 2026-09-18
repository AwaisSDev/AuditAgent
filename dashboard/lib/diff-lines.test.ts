import { describe, expect, it } from "vitest";
import { diffLines } from "./diff-lines";

describe("diffLines", () => {
  it("marks everything as same when the text is unchanged", () => {
    const text = "a\nb\nc";
    expect(diffLines(text, text)).toEqual([
      { type: "same", text: "a" },
      { type: "same", text: "b" },
      { type: "same", text: "c" },
    ]);
  });

  it("marks an appended line as an add, keeping the rest as same", () => {
    expect(diffLines("a\nb", "a\nb\nc")).toEqual([
      { type: "same", text: "a" },
      { type: "same", text: "b" },
      { type: "add", text: "c" },
    ]);
  });

  it("marks a removed line as remove, keeping the rest as same", () => {
    expect(diffLines("a\nb\nc", "a\nc")).toEqual([
      { type: "same", text: "a" },
      { type: "remove", text: "b" },
      { type: "same", text: "c" },
    ]);
  });

  it("represents a one-line edit as a remove immediately followed by an add", () => {
    expect(diffLines("a\nb\nc", "a\nx\nc")).toEqual([
      { type: "same", text: "a" },
      { type: "remove", text: "b" },
      { type: "add", text: "x" },
      { type: "same", text: "c" },
    ]);
  });

  it("handles a completely empty before text", () => {
    expect(diffLines("", "a")).toEqual([
      { type: "remove", text: "" },
      { type: "add", text: "a" },
    ]);
  });
});
