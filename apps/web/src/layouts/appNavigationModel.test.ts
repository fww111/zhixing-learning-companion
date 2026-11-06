import { appNavGroups, appNavOrder, navItemState } from "./appNavigationModel.js";

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

test("wrong-question book route belongs to wrong_questions navigation without double highlight", () => {
  assert(
    navItemState("wrong_questions", "/courses/15/assessment/wrong-questions", "", false) === "active",
    "wrong-question book should highlight its own navigation entry"
  );
  assert(
    navItemState("assessment", "/courses/15/assessment/wrong-questions", "", false) === "",
    "assessment should not double-highlight on wrong-question route"
  );
});

test("student journey navigation groups: today first, then growth, then course", () => {
  assert(appNavGroups[0].key === "learning", "learning group comes first");
  assert(appNavGroups[0].items[0] === "today", "today dashboard is the first workflow entry");
  assert(appNavGroups[1].key === "growth", "growth group comes second");
  assert(appNavGroups[2].key === "course", "course group comes last");
  assert(appNavOrder.includes("wrong_questions"), "wrong-question book has its own entry");
  assert(appNavOrder.includes("tutor_stage"), "tutor stage has its own entry");
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

test("today and tutor-stage routes highlight their own entries", () => {
  assert(navItemState("today", "/courses/15/today", "", false) === "active", "today route highlights today entry");
  assert(navItemState("tutor_stage", "/courses/15/tutor-stage", "", false) === "active", "tutor stage route highlights its entry");
  assert(navItemState("today", "/courses/15/learning-path", "", false) === "", "today stays quiet on other routes");
});
