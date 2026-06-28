import {
  choosePreferredCourse,
  currentCourseNavigationTargets,
  isCourseNavigationDisabled,
  persistCurrentCourse,
  readCurrentCourseId,
  type CourseSummary
} from "./currentCourse.js";

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

function storageStub(initial?: string) {
  const values = new Map<string, string>();
  if (initial) {
    values.set("pla_last_course_id", initial);
  }
  return {
    getItem: (key: string) => values.get(key) ?? null,
    removeItem: (key: string) => values.delete(key),
    setItem: (key: string, value: string) => values.set(key, value),
    value: (key: string) => values.get(key)
  };
}

const courses: CourseSummary[] = [
  { id: 11, name: "C语言程序设计", description: "built-in:c demo" },
  { id: 22, name: "Python 程序设计", description: "built-in:python demo" }
];

test("reads the current course id from local storage", () => {
  assert(readCurrentCourseId(storageStub("22")) === 22, "stored course id should be parsed");
  assert(readCurrentCourseId(storageStub("not-a-number")) === undefined, "invalid ids should be ignored");
});

test("keeps a user's selected course as the preferred course", () => {
  assert(choosePreferredCourse(courses, 22)?.id === 22, "previously selected Python course should stay current");
});

test("falls back to C then Python when there is no selected course", () => {
  assert(choosePreferredCourse(courses)?.id === 11, "C should be the first default selectable course");
  assert(choosePreferredCourse(courses.slice(1))?.id === 22, "Python should be used when C is absent");
});

test("builds sidebar targets from the current course id", () => {
  const targets = currentCourseNavigationTargets(22);

  assert(targets.courseKnowledgeBaseTarget === "/courses", "course knowledge base should open the course entry page");
  assert(targets.profileTarget === "/courses/22/profile/interview", "profile should target current course");
  assert(targets.graphTarget === "/courses/22/graph", "graph should target current course");
  assert(targets.pathTarget === "/courses/22/learning-path", "learning path should target current course");
  assert(targets.assessmentTarget === "/courses/22/assessment", "assessment should target current course");
});

test("enables course navigation once a current course is selected", () => {
  assert(isCourseNavigationDisabled(undefined), "course navigation should be disabled without a current course");
  assert(!isCourseNavigationDisabled(22), "course navigation should stay clickable even while the course profile is loading or incomplete");
});

test("persists selected course and emits a current course event", () => {
  const storage = storageStub();
  let eventName = "";
  const events = {
    dispatchEvent: (event: Event) => {
      eventName = event.type;
      return true;
    }
  };

  persistCurrentCourse(courses[1], storage, events);

  assert(storage.value("pla_last_course_id") === "22", "selected course id should be stored");
  assert(eventName === "pla_current_course_changed", "selection should notify layout listeners");
});
