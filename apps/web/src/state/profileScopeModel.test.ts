import type { StudentProfile } from "../api/client.js";
import { scopedProfile } from "./profileScopeModel.js";

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

test("course route only uses profile loaded for that course", () => {
  assert(scopedProfile(profile, 7, 7, true) === profile, "matching course profile should be visible");
  assert(scopedProfile(profile, 8, 7, true) === undefined, "another course profile must not unlock this route");
  assert(scopedProfile(profile, null, 7, true) === undefined, "account-level profile must not unlock course route");
});

test("account route only uses account-level profile", () => {
  assert(scopedProfile(profile, null, Number.NaN, false) === profile, "account-level profile should be visible on account route");
  assert(scopedProfile(profile, 7, Number.NaN, false) === undefined, "course profile should not leak into account profile route");
});
