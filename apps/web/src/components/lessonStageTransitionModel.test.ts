import { shouldPersistLessonStageTransition } from "./lessonStageTransitionModel.js";

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

test("lesson state stage transitions do not move backward after test opens", () => {
  assert(shouldPersistLessonStageTransition("classroom", "artifacts"), "classroom should advance to artifacts");
  assert(shouldPersistLessonStageTransition("artifacts", "test"), "artifacts should advance to test");
  assert(!shouldPersistLessonStageTransition("test", "artifacts"), "test stage should not regress to artifacts");
  assert(!shouldPersistLessonStageTransition("assessment", "test"), "assessment should be terminal for stage persistence");
});
