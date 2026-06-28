import {
  courseKnowledgeBaseEntryPageSignals,
  courseKnowledgeBasePageShouldHide,
  courseKnowledgeBasePageShouldShow,
  courseKnowledgeBaseRoute,
  courseKnowledgeBaseWorkspaceSignals
} from "./courseKnowledgeBasePageModel.js";

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

test("course knowledge-base route stays course-scoped", () => {
  assert(courseKnowledgeBaseRoute(39) === "/courses/39/knowledge-base", "knowledge-base route should include course id");
});

test("knowledge-base page exposes material workspace responsibilities", () => {
  for (const signal of courseKnowledgeBaseWorkspaceSignals) {
    assert(courseKnowledgeBasePageShouldShow(signal), `workspace signal should be visible: ${signal}`);
  }
});

test("knowledge-base page hides course-entry responsibilities", () => {
  for (const signal of courseKnowledgeBaseEntryPageSignals) {
    assert(courseKnowledgeBasePageShouldHide(signal), `entry page signal should be hidden from workspace: ${signal}`);
  }
});
