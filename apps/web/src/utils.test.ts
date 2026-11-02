import { describe, expect, it } from "vitest";
import { countUnresolved, formatDate, shortHash, VERDICT_LABEL } from "./utils";

describe("utils", () => {
  it("maps every verdict to a Japanese label", () => {
    expect(VERDICT_LABEL).toEqual({
      verified: "検証済",
      unverified: "未検証",
      contradicted: "矛盾",
      insufficient: "根拠不足",
    });
  });

  it("counts unresolved claims across states", () => {
    expect(countUnresolved({ unverified: 2, contradicted: 1, insufficient: 3, unchecked: 4 })).toBe(10);
  });

  it("shortens hashes and keeps empty values safe", () => {
    expect(shortHash("a".repeat(64))).toBe("aaaaaaaaaaaa…");
    expect(shortHash(null)).toBe("—");
  });

  it("formats invalid dates as a dash", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not-a-date")).toBe("—");
  });
});
