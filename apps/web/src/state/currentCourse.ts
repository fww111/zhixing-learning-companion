export const CURRENT_COURSE_ID_KEY = "pla_last_course_id";
export const CURRENT_COURSE_CHANGED_EVENT = "pla_current_course_changed";

export interface CourseSummary {
  id: number;
  name: string;
  description: string;
}

export interface CourseNavigationTargets {
  courseKnowledgeBaseTarget: string;
  profileTarget: string;
  graphTarget: string;
  pathTarget: string;
  assessmentTarget: string;
  todayTarget: string;
  wrongQuestionsTarget: string;
  tutorStageTarget: string;
}

export function readCurrentCourseId(storage: Pick<Storage, "getItem"> = localStorage): number | undefined {
  const value = Number(storage.getItem(CURRENT_COURSE_ID_KEY));
  return Number.isFinite(value) && value > 0 ? value : undefined;
}

export function choosePreferredCourse(courses: CourseSummary[], previousId?: number): CourseSummary | undefined {
  return courses.find((course) => course.id === previousId)
    ?? courses.find((course) => course.description.includes("built-in:c"))
    ?? courses.find((course) => course.description.includes("built-in:python"))
    ?? courses[0];
}

export function currentCourseNavigationTargets(courseId?: number): CourseNavigationTargets {
  return {
    courseKnowledgeBaseTarget: "/courses",
    profileTarget: courseId ? `/courses/${courseId}/profile/interview` : "/courses",
    graphTarget: courseId ? `/courses/${courseId}/graph` : "/courses",
    pathTarget: courseId ? `/courses/${courseId}/learning-path` : "/courses",
    assessmentTarget: courseId ? `/courses/${courseId}/assessment` : "/courses",
    todayTarget: courseId ? `/courses/${courseId}/today` : "/courses",
    wrongQuestionsTarget: courseId ? `/courses/${courseId}/assessment/wrong-questions` : "/courses",
    tutorStageTarget: courseId ? `/courses/${courseId}/tutor-stage` : "/courses"
  };
}

export function isCourseNavigationDisabled(courseId?: number): boolean {
  return !courseId;
}

export function persistCurrentCourse(
  course?: CourseSummary,
  storage: Pick<Storage, "removeItem" | "setItem"> = localStorage,
  events: Pick<Window, "dispatchEvent"> = window
) {
  if (!course) {
    storage.removeItem(CURRENT_COURSE_ID_KEY);
    events.dispatchEvent(new CustomEvent(CURRENT_COURSE_CHANGED_EVENT));
    return;
  }
  storage.setItem(CURRENT_COURSE_ID_KEY, String(course.id));
  events.dispatchEvent(new CustomEvent(CURRENT_COURSE_CHANGED_EVENT, { detail: { courseId: course.id, courseName: course.name } }));
}
