import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const pageSource = readFileSync(resolve("src/pages/CourseKnowledgeBasePage.tsx"), "utf8");
const forbiddenSections = [
  ["kb-course-gallery", "course-specific knowledge-base page should not render my-course gallery"],
  ["ensureDefaultPythonCourse", "course-specific knowledge-base page should not create built-in demo courses"],
  ["ensureDefaultCCourse", "course-specific knowledge-base page should not create built-in demo courses"],
  ["listCourses", "course-specific knowledge-base page should not load the full course list"],
  ["kb-preview-metrics", "knowledge-base creation page should not render the course metric row"],
  ["kb-workspace-pipeline", "knowledge-base creation page should not render the pipeline summary row"],
  ["kb-hero-visual", "knowledge-base creation page should not render the decorative hero illustration"]
];
const requiredCoursePageStyleHooks = [
  ["kb-preview-hero", "knowledge-base page should reuse the courses page hero shell"],
  ["applyBuiltInKnowledgeBase", "knowledge-base page should apply built-in examples to the current course"],
  ["kb-builtin-panel", "knowledge-base page should expose built-in knowledge-base choices in the workspace"]
];

for (const [needle, message] of forbiddenSections) {
  if (pageSource.includes(needle)) {
    throw new Error(message);
  }
}

for (const [needle, message] of requiredCoursePageStyleHooks) {
  if (!pageSource.includes(needle)) {
    throw new Error(message);
  }
}

console.log("PASS knowledge-base route renders only the material workspace");
