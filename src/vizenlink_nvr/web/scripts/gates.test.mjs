import { describe, expect, it } from "vitest";
import { scanSource, walkDirectory, checkLegacyDir, RULES } from "./gates.mjs";
import path from "node:path";
import { fileURLToPath } from "node:url";

describe("Design gates (scanSource)", () => {
  it("R1: flags inline style without dynamic-style comment, allows with comment", () => {
    const violating = `export const Comp = () => <div style={{ width: 100 }} />;`;
    const cleanSameLine = `export const Comp = () => <div style={{ width: 100 }} /* dynamic-style: runtime width */ />;`;
    const cleanPrevLine = `// dynamic-style: runtime width\nexport const Comp = () => <div style={{ width: 100 }} />;`;

    const v1 = scanSource("src/features/Comp.tsx", violating);
    expect(v1.some((v) => v.rule === "R1")).toBe(true);

    const v2 = scanSource("src/features/Comp.tsx", cleanSameLine);
    expect(v2.some((v) => v.rule === "R1")).toBe(false);

    const v3 = scanSource("src/features/Comp.tsx", cleanPrevLine);
    expect(v3.some((v) => v.rule === "R1")).toBe(false);
  });

  it("R2: flags hex colour literals in TSX, allows in non-TSX", () => {
    const violating = `export const Comp = () => <div className="text-[#38bdf8]">Hi</div>;`;
    const clean = `export const Comp = () => <div className="text-primary">Hi</div>;`;

    const v1 = scanSource("src/features/Comp.tsx", violating);
    expect(v1.some((v) => v.rule === "R2")).toBe(true);

    const v2 = scanSource("src/features/Comp.tsx", clean);
    expect(v2.some((v) => v.rule === "R2")).toBe(false);
  });

  it("R3: flags arbitrary bracket font sizes and spacing values", () => {
    const violating1 = `const cls = "text-[28px]";`;
    const violating2 = `const cls = "p-[14px]";`;
    const clean = `const cls = "text-display p-4";`;

    expect(scanSource("src/features/Comp.tsx", violating1).some((v) => v.rule === "R3")).toBe(true);
    expect(scanSource("src/features/Comp.tsx", violating2).some((v) => v.rule === "R3")).toBe(true);
    expect(scanSource("src/features/Comp.tsx", clean).some((v) => v.rule === "R3")).toBe(false);
  });

  it("R4: flags bare element labels in TSX", () => {
    const violating = `<button>Cancel</button>`;
    const clean = `<button>Cancel operation</button>`;

    expect(scanSource("src/features/Comp.tsx", violating).some((v) => v.rule === "R4")).toBe(true);
    expect(scanSource("src/features/Comp.tsx", clean).some((v) => v.rule === "R4")).toBe(false);
  });

  it("R5: flags disallowed font weight and size utilities", () => {
    const violatingWeight = `const cls = "font-bold";`;
    const violatingSize = `const cls = "text-lg";`;
    const clean = `const cls = "font-semibold text-xl text-sm text-xs text-display";`;

    expect(scanSource("src/features/Comp.tsx", violatingWeight).some((v) => v.rule === "R5")).toBe(true);
    expect(scanSource("src/features/Comp.tsx", violatingSize).some((v) => v.rule === "R5")).toBe(true);
    expect(scanSource("src/features/Comp.tsx", clean).some((v) => v.rule === "R5")).toBe(false);
  });

  it("R6: flags backdrop blur in src/components/ui/**", () => {
    const violating = `export const Card = () => <div className="backdrop-blur-md" />;`;
    const clean = `export const Card = () => <div className="bg-card" />;`;

    expect(scanSource("src/components/ui/card.tsx", violating).some((v) => v.rule === "R6")).toBe(true);
    expect(scanSource("src/components/ui/card.tsx", clean).some((v) => v.rule === "R6")).toBe(false);
  });

  it("R7: flags raw HTML injection props", () => {
    const violating = `<div dangerouslySetInnerHTML={{ __html: raw }} />`;
    const clean = `<div>{raw}</div>`;

    expect(scanSource("src/features/Comp.tsx", violating).some((v) => v.rule === "R7")).toBe(true);
    expect(scanSource("src/features/Comp.tsx", clean).some((v) => v.rule === "R7")).toBe(false);
  });

  it("R8: flags gradient background utilities", () => {
    const violating = `<div className="bg-gradient-to-r from-blue-500 to-indigo-500" />`;
    const clean = `<div className="bg-primary" />`;

    expect(scanSource("src/features/Comp.tsx", violating).some((v) => v.rule === "R8")).toBe(true);
    expect(scanSource("src/features/Comp.tsx", clean).some((v) => v.rule === "R8")).toBe(false);
  });

  it("R9: flags icon Button without aria-label", () => {
    const violatingSingle = `<Button size="icon"><Icon /></Button>`;
    const violatingMulti = `<Button\n  size="icon"\n  variant="ghost"\n><Icon /></Button>`;
    const clean = `<Button size="icon" aria-label="Refresh view"><Icon /></Button>`;

    expect(scanSource("src/features/Comp.tsx", violatingSingle).some((v) => v.rule === "R9")).toBe(true);
    expect(scanSource("src/features/Comp.tsx", violatingMulti).some((v) => v.rule === "R9")).toBe(true);
    expect(scanSource("src/features/Comp.tsx", clean).some((v) => v.rule === "R9")).toBe(false);
  });

  it("R10: flags off-scale spacing utilities in project code", () => {
    const violating = `<div className="p-3 m-5 gap-7" />`;
    const clean = `<div className="p-4 m-8 gap-2 space-y-4" />`;

    expect(scanSource("src/components/Comp.tsx", violating).some((v) => v.rule === "R10")).toBe(true);
    expect(scanSource("src/components/Comp.tsx", clean).some((v) => v.rule === "R10")).toBe(false);
    // Exempt in src/components/ui/
    expect(scanSource("src/components/ui/button.tsx", violating).some((v) => v.rule === "R10")).toBe(false);
  });

  it("R0: flags any file under src/legacy with R0 violation", () => {
    const cleanContent = `export const Clean = () => <div className="p-4" />;`;
    const violations = scanSource("src/legacy/OldView.tsx", cleanContent);
    expect(violations.length).toBe(1);
    expect(violations[0].rule).toBe("R0");
    expect(violations[0].message).toBe(RULES.R0);

    // Negative case: non-legacy file does not trigger R0
    expect(scanSource("src/features/users/UsersPage.tsx", cleanContent)).toEqual([]);
  });

  it("R0: checkLegacyDir flags presence of src/legacy directory", () => {
    const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
    // Negative case: currently src/legacy does not exist -> 0 violations
    expect(checkLegacyDir(rootDir)).toEqual([]);
  });

  it("scoping: src/test/** skips R1 and R2 but flags other rule violations", () => {
    // R1 inline style: skipped in test
    const r1Snippet = `<div style={{ width: 100 }} />`;
    expect(scanSource("src/test/fixture.tsx", r1Snippet)).toEqual([]);

    // R2 hex color: skipped in test
    const r2Snippet = `<div className="text-[#123456]" />`;
    expect(scanSource("src/test/fixture.tsx", r2Snippet)).toEqual([]);

    // R4 bare button label: NOT skipped in test
    const r4Snippet = `<button>Cancel</button>`;
    expect(scanSource("src/test/fixture.tsx", r4Snippet).some((v) => v.rule === "R4")).toBe(true);

    // R7 raw HTML injection: NOT skipped in test
    const r7Snippet = `<div dangerouslySetInnerHTML={{ __html: "x" }} />`;
    expect(scanSource("src/test/fixture.tsx", r7Snippet).some((v) => v.rule === "R7")).toBe(true);
  });
});
