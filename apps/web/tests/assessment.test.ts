import { isApplicable, missingInStep } from "@/components/domain/assessment";

const q = (key: string, dimension: string, condition: any = null, qtype: any = "single") =>
  ({ key, dimension, text: key, help_text: null, qtype, options: [{ value: "a", label: "A", score: 0 }], condition });

describe("conditional questions", () => {
  const parent = q("ai_in_prod", "strategy");
  const child = q("value_measured", "strategy", { question: "ai_in_prod", in: ["pilots", "prod"] });

  it("hides follow-ups until the parent answer matches", () => {
    expect(isApplicable(child, {})).toBe(false);
    expect(isApplicable(child, { ai_in_prod: "none" })).toBe(false);
    expect(isApplicable(child, { ai_in_prod: "pilots" })).toBe(true);
  });

  it("supports multi-select parents", () => {
    expect(isApplicable(child, { ai_in_prod: ["x", "prod"] })).toBe(true);
  });

  it("counts only applicable unanswered questions as missing", () => {
    expect(missingInStep([parent, child], {}, "strategy")).toEqual(["ai_in_prod"]);
    expect(missingInStep([parent, child], { ai_in_prod: "pilots" }, "strategy")).toEqual(["value_measured"]);
    expect(missingInStep([parent, child], { ai_in_prod: "none" }, "strategy")).toEqual([]);
  });

  it("treats a non-array multi answer as missing", () => {
    const multi = q("systems", "technology", null, "multi");
    expect(missingInStep([multi], { systems: "crm" }, "technology")).toEqual(["systems"]);
    expect(missingInStep([multi], { systems: [] }, "technology")).toEqual([]);
  });
});
