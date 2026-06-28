import type { StudentProfile } from "../api/client";

export function isProfileScopedToCourse(
  profile: StudentProfile | undefined,
  profileCourseId: number | null | undefined,
  courseId: number | undefined
): boolean {
  return Boolean(profile && courseId !== undefined && profileCourseId === courseId);
}
