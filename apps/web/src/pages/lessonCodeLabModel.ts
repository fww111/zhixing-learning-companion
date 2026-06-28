import type { Course, Resource } from "../api/client";

export type LessonCodeLanguage = "python" | "c";

export interface LessonCodeLabViewModel {
  language: LessonCodeLanguage;
  labLabel: string;
  starterCode: string;
}

export function lessonCodeLabViewModel(input: {
  course?: Course;
  resource?: Resource;
  topic: string;
}): LessonCodeLabViewModel {
  const language = detectLessonCodeLanguage(input.course, input.resource, input.topic);
  return {
    language,
    labLabel: language === "c" ? "Browser C Lab" : "Browser Python Lab",
    starterCode: extractStarterCode(input.resource, input.topic, language)
  };
}

export function detectLessonCodeLanguage(course: Course | undefined, resource: Resource | undefined, topic: string): LessonCodeLanguage {
  const text = [
    course?.name,
    course?.description,
    resource?.title,
    resource?.content,
    ...(resource?.tags ?? []),
    topic
  ].filter(Boolean).join("\n").toLowerCase();
  if (
    text.includes("```c")
    || text.includes("#include <stdio.h>")
    || text.includes("printf(")
    || text.includes("c语言")
    || text.includes("c 语言")
    || text.includes("built-in:c")
  ) {
    return "c";
  }
  return "python";
}

export function extractStarterCode(resource: Resource | undefined, topic: string, language: LessonCodeLanguage): string {
  const fenced = /```([a-z0-9+#-]*)\s*([\s\S]*?)```/i.exec(resource?.content || "");
  if (fenced?.[2]?.trim()) {
    const fenceLanguage = fenced[1].trim().toLowerCase();
    const matchesLanguage = language === "c"
      ? ["c", "cpp", "c++"].includes(fenceLanguage)
      : ["", "python", "py"].includes(fenceLanguage);
    if (matchesLanguage) {
      return fenced[2].trim();
    }
  }
  if (language === "c") {
    return [
      `/* ${topic}: C language practice */`,
      "#include <stdio.h>",
      "",
      "int main(void) {",
      "    printf(\"Hello C\\n\");",
      "    return 0;",
      "}"
    ].join("\n");
  }
  return [
    `# ${topic}: practice while learning`,
    "language = 'Python'",
    "feature = 'interpreted, object-oriented, cross-platform'",
    "print('Hello ' + language)",
    "print(f'{language} feature: {feature}')"
  ].join("\n");
}
