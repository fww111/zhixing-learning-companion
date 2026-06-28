import {
  courseProfileRoute,
  coursePrimaryActionLabel,
  courseTemplateConfirmation,
  type BuiltInCourseOption
} from "./courseTemplateModel.js";

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

const cOption: BuiltInCourseOption = {
  key: "c",
  title: "C语言程序设计",
  description: "C language course",
  focus: ["指针"]
};

test("requires explicit confirmation before creating a built-in course instance", () => {
  const confirmation = courseTemplateConfirmation(cOption, undefined);

  assert(confirmation !== undefined, "missing confirmation for unowned built-in template");
  assert(confirmation?.key === "c", "confirmation should preserve the selected course key");
  assert(confirmation.title.includes("C语言程序设计"), "confirmation should name the selected course");
  assert(confirmation.message.includes("复制到当前账号"), "confirmation should explain account-local copying");
  assert(confirmation.message.includes("未确认不会创建任何课程数据"), "confirmation should state that cancel creates nothing");
});

test("does not ask for template confirmation after the user already owns the course", () => {
  assert(courseTemplateConfirmation(cOption, 33) === undefined, "existing course should enter directly");
});

test("labels unowned built-in templates differently from owned courses", () => {
  assert(coursePrimaryActionLabel(undefined) === "使用内置示例", "unowned template should not say enter course");
  assert(coursePrimaryActionLabel(33) === "进入课程", "owned course should say enter course");
});

test("routes newly created courses to their course-specific profile interview", () => {
  assert(courseProfileRoute(88) === "/courses/88/profile/interview", "new courses should start with course profile construction");
});
