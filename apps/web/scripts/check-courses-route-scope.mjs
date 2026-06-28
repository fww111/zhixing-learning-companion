import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const pageSource = readFileSync(resolve("src/pages/CoursesPage.tsx"), "utf8");
const forbiddenSections = [
  ["kb-builtin-panel", "courses page should not render built-in knowledge-base choices"],
  ["ensureDefaultPythonCourse", "courses page should not create the Python built-in knowledge base"],
  ["ensureDefaultCCourse", "courses page should not create the C built-in knowledge base"],
  ["built-in-examples", "courses page should not link to a built-in knowledge-base section"]
];

for (const [needle, message] of forbiddenSections) {
  if (pageSource.includes(needle)) {
    throw new Error(message);
  }
}

console.log("PASS courses route only selects or creates courses");
