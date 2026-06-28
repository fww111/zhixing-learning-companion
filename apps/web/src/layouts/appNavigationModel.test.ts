import { appNavOrder, navItemState } from "./appNavigationModel.js";

function assert(condition: boolean, message: string) {
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

test("learning path and assessment navigation are independent", () => {
  const pathUrl = "/courses/15/learning-path";
  const assessmentUrl = "/courses/15/assessment";

  assert(navItemState("learning_path", pathUrl, "", false) === "active", "learning path should be active on learning path route");
  assert(navItemState("learning_path", pathUrl, "?mode=remedial", false) === "active", "remedial path should still belong to learning path navigation");
  assert(navItemState("assessment", pathUrl, "", false) === "", "assessment should not be active on learning path route");
  assert(navItemState("learning_path", assessmentUrl, "", false) === "", "learning path should not be active on assessment route");
  assert(navItemState("assessment", assessmentUrl, "", false) === "active", "assessment should be active on assessment route");
});

test("wrong-question book route belongs to assessment navigation", () => {
  assert(
    navItemState("assessment", "/courses/15/assessment/wrong-questions", "", false) === "active",
    "wrong-question book should keep assessment navigation active"
  );
});

test("course knowledge base appears before student profile in the sidebar", () => {
  assert(appNavOrder[0] === "courses", "course knowledge base should be the first workflow navigation item");
  assert(appNavOrder[1] === "profile", "student profile should appear after course knowledge base");
});

test("course knowledge-base route marks course navigation active", () => {
  assert(navItemState("courses", "/courses/22/knowledge-base", "", false) === "active", "course knowledge-base route should belong to course navigation");
  assert(navItemState("courses", "/courses/22/graph", "", false) === "", "graph route should not mark course navigation active");
});

test("disabled navigation takes precedence over active state", () => {
  assert(navItemState("learning_path", "/courses/15/learning-path", "", true) === "disabled", "disabled item should not render active");
});

test("course-scoped profile route marks profile navigation active", () => {
  assert(navItemState("profile", "/courses/15/profile/interview", "", false) === "active", "course profile interview should belong to profile navigation");
});
