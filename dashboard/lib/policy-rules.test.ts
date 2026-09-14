import { describe, expect, it } from "vitest";
import { DEFAULT_TOGGLES, isSimpleYaml, togglesToYaml, yamlToToggles } from "./policy-rules";

describe("togglesToYaml / yamlToToggles round-trip", () => {
  it("round-trips the default toggle state", () => {
    const yaml = togglesToYaml(DEFAULT_TOGGLES);
    expect(yamlToToggles(yaml)).toEqual(DEFAULT_TOGGLES);
  });

  it("round-trips every toggle flipped on", () => {
    const allOn = { delete_data: true, data_access: true, external: true, internal: true };
    expect(yamlToToggles(togglesToYaml(allOn))).toEqual(allOn);
  });

  it("round-trips every toggle flipped off", () => {
    const allOff = { delete_data: false, data_access: false, external: false, internal: false };
    expect(yamlToToggles(togglesToYaml(allOff))).toEqual(allOff);
  });
});

describe("yamlToToggles", () => {
  it("returns null for empty text rather than treating it as everything off", () => {
    expect(yamlToToggles("")).toBeNull();
    expect(yamlToToggles("   ")).toBeNull();
  });

  it("returns null for unparseable YAML", () => {
    expect(yamlToToggles("not: valid: yaml: [[")).toBeNull();
  });

  it("treats valid YAML with no `rules` key as an empty rule set (all four toggles off), not null", () => {
    // Only empty text and a genuine parse failure return null (see the two
    // tests above) -- valid-but-unrelated YAML is "best-effort" territory
    // per this function's own docstring, and reads as no rules at all.
    expect(yamlToToggles("just: a string\n")).toEqual({
      delete_data: false,
      data_access: false,
      external: false,
      internal: false,
    });
  });

  it("treats a rule for an unrecognized action_type as leaving all four known toggles off", () => {
    const yaml = "rules:\n  - match:\n      action_type: something_custom\n    require_approval: true\n";
    const toggles = yamlToToggles(yaml);
    expect(toggles).toEqual({ delete_data: false, data_access: false, external: false, internal: false });
  });

  it("defaults a matched rule with no explicit require_approval to false", () => {
    const yaml = "rules:\n  - match:\n      action_type: external\n";
    expect(yamlToToggles(yaml)?.external).toBe(false);
  });
});

describe("isSimpleYaml", () => {
  it("is true for the default 4-rule policy", () => {
    expect(isSimpleYaml(togglesToYaml(DEFAULT_TOGGLES))).toBe(true);
  });

  it("is true for an empty rules list", () => {
    expect(isSimpleYaml("rules: []\n")).toBe(true);
  });

  it("is false once a 5th rule is added", () => {
    const yaml =
      "rules:\n" +
      "  - match:\n      action_type: data_access\n      action_name: delete_*\n    require_approval: true\n" +
      "  - match:\n      action_type: data_access\n    require_approval: false\n" +
      "  - match:\n      action_type: external\n    require_approval: true\n" +
      "  - match:\n      action_type: internal\n    require_approval: false\n" +
      "  - match:\n      action_name: send_refund\n    require_approval: true\n";
    expect(isSimpleYaml(yaml)).toBe(false);
  });

  it("is false for unparseable YAML", () => {
    expect(isSimpleYaml("not: valid: [[")).toBe(false);
  });
});
