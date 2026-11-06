import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const RULES = {
  R1: "Inline style object without dynamic-style comment",
  R2: "CSS hex colour literal in TSX",
  R3: "Arbitrary bracket font sizes or spacing values",
  R4: "Bare button/element label (Cancel, OK, Retry, Submit, Close, Dismiss)",
  R5: "Disallowed font weight or font size utility",
  R6: "Backdrop blur utility in src/components/ui",
  R7: "Raw HTML injection prop (dangerouslySetInnerHTML / innerHTML)",
  R8: "Gradient background utility",
  R9: "Icon Button missing aria-label",
  R10: "Spacing utility outside declared steps (0, 1, 2, 4, 6, 8, 12, 16)",
};

const ALLOWED_SPACING_STEPS = new Set(["0", "1", "2", "4", "6", "8", "12", "16"]);

export function scanSource(relPath, text) {
  const normPath = relPath.replace(/\\/g, "/");

  // Skip legacy and test files
  if (normPath.includes("src/legacy/") || normPath.includes("src/test/")) {
    return [];
  }

  const isTsx = normPath.endsWith(".tsx");
  const isUiComponent = normPath.includes("src/components/ui/");
  const isProjectSpacingScoped =
    (normPath.includes("src/app/") || normPath.includes("src/features/") || normPath.includes("src/components/")) &&
    !isUiComponent;

  const violations = [];
  const lines = text.split("\n");

  for (let i = 0; i < lines.length; i++) {
    const lineNum = i + 1;
    const line = lines[i];
    const prevLine = i > 0 ? lines[i - 1] : "";

    // R1: Inline style in .tsx requires dynamic-style comment on same or prev line
    if (isTsx && /style\s*=\s*\{\{/.test(line)) {
      const hasComment = line.includes("dynamic-style:") || prevLine.includes("dynamic-style:");
      if (!hasComment) {
        violations.push({
          rule: "R1",
          line: lineNum,
          message: RULES.R1,
        });
      }
    }

    // R2: No CSS hex colour literal in .tsx
    if (isTsx && /#(?:[0-9a-fA-F]{3,8})\b/.test(line)) {
      violations.push({
        rule: "R2",
        line: lineNum,
        message: RULES.R2,
      });
    }

    // R3: No arbitrary bracket font sizes (text-[0-9...) or arbitrary bracket padding/margin/gap/space
    if (/\btext-\[\d/.test(line) || /\b-?(?:p[xytblrse]?|m[xytblrse]?|gap(?:-[xy])?|space-[xy])-\[/.test(line)) {
      violations.push({
        rule: "R3",
        line: lineNum,
        message: RULES.R3,
      });
    }

    // R4: No bare element text (Cancel, OK, Retry, Submit, Close, Dismiss) in .tsx
    if (isTsx && />\s*(?:Cancel|OK|Retry|Submit|Close|Dismiss)\s*</.test(line)) {
      violations.push({
        rule: "R4",
        line: lineNum,
        message: RULES.R4,
      });
    }

    // R5: No weight utilities other than font-normal and font-semibold; no text-base, text-lg, text-2xl+
    if (
      /\bfont-(?:medium|bold|light|thin|extralight|extrabold|black)\b/.test(line) ||
      /\btext-(?:base|lg|2xl|3xl|4xl|5xl|6xl|7xl|8xl|9xl)\b/.test(line)
    ) {
      violations.push({
        rule: "R5",
        line: lineNum,
        message: RULES.R5,
      });
    }

    // R6: In src/components/ui/**, no backdrop blur utilities
    if (isUiComponent && /\bbackdrop-blur(?:-\w+)?\b/.test(line)) {
      violations.push({
        rule: "R6",
        line: lineNum,
        message: RULES.R6,
      });
    }

    // R7: No raw HTML injection prop anywhere
    if (/\b(?:dangerouslySetInnerHTML|innerHTML)\b/.test(line)) {
      violations.push({
        rule: "R7",
        line: lineNum,
        message: RULES.R7,
      });
    }

    // R8: No gradient background utilities
    if (/\b(?:bg-gradient-(?:to-)?[a-z0-9_-]+|bg-linear-(?:to-)?[a-z0-9_-]+|bg-radial|bg-conic|gradient-to-[a-z0-9_-]+)\b/.test(line)) {
      violations.push({
        rule: "R8",
        line: lineNum,
        message: RULES.R8,
      });
    }

    // R10: Spacing scale in project code
    if (isProjectSpacingScoped) {
      const spacingRegex = /\b-?(?:p[xytblrse]?|m[xytblrse]?|gap(?:-[xy])?|space-[xy])-(\d+|\[[^\]]+\])\b/g;
      let match;
      while ((match = spacingRegex.exec(line)) !== null) {
        const step = match[1];
        if (!ALLOWED_SPACING_STEPS.has(step)) {
          violations.push({
            rule: "R10",
            line: lineNum,
            message: `${RULES.R10} (found "${match[0]}")`,
          });
          break; // One violation per line is sufficient
        }
      }
    }
  }

  // R9: Icon Button without aria-label in .tsx
  if (isTsx) {
    const buttonRegex = /<Button\b([^>]*?)(?:>|\/>)/gs;
    let btnMatch;
    while ((btnMatch = buttonRegex.exec(text)) !== null) {
      const attrs = btnMatch[1];
      const hasIconSize = /\bsize=["']icon["']/.test(attrs);
      const hasAriaLabel = /\baria-label=/.test(attrs);
      if (hasIconSize && !hasAriaLabel) {
        const lineNum = text.slice(0, btnMatch.index).split("\n").length;
        violations.push({
          rule: "R9",
          line: lineNum,
          message: RULES.R9,
        });
      }
    }
  }

  return violations;
}

export function walkDirectory(dir, fileList = []) {
  if (!fs.existsSync(dir)) return fileList;
  const entries = fs.readdirSync(dir, { withFileTypes: true });
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === "node_modules" || entry.name === "dist" || entry.name === "legacy" || entry.name === "test") {
        continue;
      }
      walkDirectory(fullPath, fileList);
    } else if (entry.isFile()) {
      const ext = path.extname(entry.name);
      if ([".ts", ".tsx", ".css"].includes(ext)) {
        fileList.push(fullPath);
      }
    }
  }
  return fileList;
}

// CLI runner
const isMain = process.argv[1] && fileURLToPath(import.meta.url) === path.resolve(process.argv[1]);
if (isMain) {
  const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
  const srcDir = path.join(rootDir, "src");
  const files = walkDirectory(srcDir);

  let totalViolations = 0;
  for (const file of files) {
    const relPath = path.relative(rootDir, file);
    const content = fs.readFileSync(file, "utf8");
    const fileViolations = scanSource(relPath, content);
    for (const v of fileViolations) {
      console.error(`${relPath}:${v.line} [${v.rule}] ${v.message}`);
      totalViolations++;
    }
  }

  if (totalViolations > 0) {
    console.error(`\n❌ Design gates failed with ${totalViolations} violation(s).`);
    process.exit(1);
  } else {
    console.log(`\n✅ Design gates passed: scanned ${files.length} non-legacy files with 0 violations.`);
    process.exit(0);
  }
}
