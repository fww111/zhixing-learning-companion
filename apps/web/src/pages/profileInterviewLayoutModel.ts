export type ProfileInterviewLayoutMode = "dashboard_only" | "interview_builder";

export interface ProfileInterviewLayout {
  mode: ProfileInterviewLayoutMode;
  gridClassName: string;
  heroClassName: string;
  heading: string;
  description: string;
  primaryActionLabel: string;
  readyDescription: string;
  completionDescription: string;
  pendingHint: string;
}

export function profileInterviewLayout(hasConfirmedProfile: boolean): ProfileInterviewLayout {
  if (hasConfirmedProfile) {
    return {
      mode: "dashboard_only",
      gridClassName: "profile-workbench-grid profile-dashboard-only",
      heroClassName: "kb-preview-hero profile-course-hero profile-course-hero-compact",
      heading: "课程学生画像",
      description: "多维画像数据会随着课堂学习、随堂测试、编程练习和学习评估持续更新。",
      primaryActionLabel: "进入课程知识库",
      readyDescription: "已读取该课程的确认画像。可以直接进入课程知识库，继续上传课程材料、生成知识图谱和学习路径。",
      completionDescription: "画像维度已补齐，系统将保存画像并进入课程知识库。",
      pendingHint: "画像维度齐全后会自动保存，并进入课程知识库流程。"
    };
  }

  return {
    mode: "interview_builder",
    gridClassName: "profile-workbench-grid",
    heroClassName: "kb-preview-hero profile-course-hero profile-course-hero-compact",
    heading: "构建当前课程画像",
    description: "每门课程独立构建画像；切换到另一门课时，画像、知识库、图谱和学习记录不会混用。",
    primaryActionLabel: "进入课程知识库",
    readyDescription: "已读取该课程的确认画像。可以直接进入课程知识库，继续上传课程材料、生成知识图谱和学习路径。",
    completionDescription: "画像维度已补齐，系统将保存画像并进入课程知识库。",
    pendingHint: "画像维度齐全后会自动保存，并进入课程知识库流程。"
  };
}

export function profileInterviewCompletionTarget(courseId?: number): string {
  return courseId && Number.isFinite(courseId) ? `/courses/${courseId}/knowledge-base` : "/courses";
}

export function shouldAutoConfirmProfileInterview(status: string): boolean {
  return status === "ready_to_confirm";
}
