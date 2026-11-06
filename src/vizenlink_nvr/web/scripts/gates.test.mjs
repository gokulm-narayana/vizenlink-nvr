import { describe, expect, it } from "vitest";
import { scanSource, walkDirectory, RULES } from "./gates.mjs";
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

  it("skips src/legacy and src/test files in scanSource and walkDirectory", () => {
    const violating = `<div style={{ width: 100 }}><Button size="icon">Cancel</Button></div>`;
    expect(scanSource("src/legacy/LegacyApp.tsx", violating)).toEqual([]);
    expect(scanSource("src/test/setup.ts", violating)).toEqual([]);

    const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
    const files = walkDirectory(path.join(rootDir, "src"));
    expect(files.some((f) => f.includes("/legacy/"))).toBe(false);
    expect(files.some((f) => f.includes("/test/"))).toBe(false);
  });
});
