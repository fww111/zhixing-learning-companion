export const courseKnowledgeBaseWorkspaceSignals = [
  "上传 PDF / PPT / PPTX",
  "MinerU 精准解析",
  "MySQL 知识切片",
  "Milvus 向量索引"
] as const;

export const courseKnowledgeBaseEntryPageSignals = [
  "我的课程",
  "内置示例知识库",
  "创建我的课程",
  "选择一门作为当前课程"
] as const;

export function courseKnowledgeBaseRoute(courseId: number): string {
  return `/courses/${courseId}/knowledge-base`;
}

export function courseKnowledgeBasePageShouldShow(signal: string): boolean {
  return (courseKnowledgeBaseWorkspaceSignals as readonly string[]).includes(signal);
}

export function courseKnowledgeBasePageShouldHide(signal: string): boolean {
  return (courseKnowledgeBaseEntryPageSignals as readonly string[]).includes(signal);
}
