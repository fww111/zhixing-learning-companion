import type { StudentProfile } from "../api/client";

export function scopedProfile(
  profile: StudentProfile | undefined,
  profileCourseId: number | null | undefined,
  routeCourseId: number,
  isCourseScoped: boolean
): StudentProfile | undefined {
  if (!profile) {
    return undefined;
  }
  if (!isCourseScoped) {
    return profileCourseId == null ? profile : undefined;
  }
  return profileCourseId === routeCourseId ? profile : undefined;
}

export { isProfileScopedToCourse } from "./profileCourseBindingModel";
