export type BuiltInCourseKey = "python" | "c";

export interface BuiltInCourseOption {
  key: BuiltInCourseKey;
  title: string;
  description: string;
  focus: string[];
}

export interface CourseTemplateConfirmation {
  key: BuiltInCourseKey;
  title: string;
  message: string;
}

export function courseTemplateConfirmation(
  option: BuiltInCourseOption,
  existingCourseId?: number | null
): CourseTemplateConfirmation | undefined {
  if (existingCourseId) {
    return undefined;
  }
  return {
    key: option.key,
    title: `使用内置示例：${option.title}`,
    message: `确认后，系统会把「${option.title}」内置示例知识库复制到当前账号，并生成该课程专属画像、知识库、知识图谱和学习路径数据。未确认不会创建任何课程数据。`
  };
}

export function coursePrimaryActionLabel(existingCourseId?: number | null): string {
  return existingCourseId ? "进入课程" : "使用内置示例";
}

export function courseProfileRoute(courseId: number): string {
  return `/courses/${courseId}/profile/interview`;
}
