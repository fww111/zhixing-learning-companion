import type { StudentProfile } from "../api/client.js";
import { isProfileScopedToCourse } from "./profileCourseBindingModel.js";

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

const profile = { student_id: "user-1" } as StudentProfile;

test("course shell status only binds a matching course profile", () => {
  assert(isProfileScopedToCourse(profile, 7, 7), "matching course profile should be bound");
  assert(!isProfileScopedToCourse(profile, 8, 7), "previous course profile should not be bound");
  assert(!isProfileScopedToCourse(profile, null, 7), "account profile should not be shown as course-bound");
  assert(!isProfileScopedToCourse(undefined, 7, 7), "missing profile should not be bound");
});
