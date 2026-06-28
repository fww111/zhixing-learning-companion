import {
  profileInterviewCompletionTarget,
  profileInterviewLayout,
  shouldAutoConfirmProfileInterview
} from "./profileInterviewLayoutModel.js";

function assert(condition: boolean, message: string): asserts condition {
  if (!condition) {
    throw new Error(message);
  }
}

function test(name: string, fn: () => void) {
  try {
    fn();
    console.log(`PASS ${name}`);
  } catch (error) {
    console.error(`FAIL ${name}`);
    throw error;
  }
}

test("confirmed course profile uses the full-page visual dashboard", () => {
  const layout = profileInterviewLayout(true);

  assert(layout.mode === "dashboard_only", "confirmed profile page should hide the interview panel");
  assert(layout.gridClassName.includes("profile-dashboard-only"), "dashboard mode should use the full-width grid class");
  assert(layout.heroClassName.includes("profile-course-hero-compact"), "profile hero should use compact layout without decorative image");
  assert(layout.heading === "课程学生画像", "confirmed profile page should use the profile display heading");
  assert(layout.primaryActionLabel === "进入课程知识库", "confirmed profile action should enter the course knowledge base");
});

test("missing profile keeps the interview builder visible", () => {
  const layout = profileInterviewLayout(false);

  assert(layout.mode === "interview_builder", "missing profile still needs the interview builder");
  assert(!layout.gridClassName.includes("profile-dashboard-only"), "interview mode should keep the two-column construction layout");
  assert(layout.heroClassName.includes("profile-course-hero-compact"), "interview hero should not reserve a decorative image column");
  assert(layout.heading === "构建当前课程画像", "interview mode should keep the construction heading");
  assert(layout.completionDescription.includes("课程知识库"), "completion hint should point to knowledge base construction");
  assert(!layout.completionDescription.includes("知识图谱"), "profile completion should not skip to knowledge graph");
});

test("ready-to-confirm interview should auto-confirm and continue to course knowledge base", () => {
  assert(shouldAutoConfirmProfileInterview("ready_to_confirm"), "ready profile should be confirmed without another manual click");
  assert(!shouldAutoConfirmProfileInterview("in_progress"), "incomplete interview should stay on interview page");
  assert(profileInterviewCompletionTarget(39) === "/courses/39/knowledge-base", "course profile completion should open that course knowledge base");
});
