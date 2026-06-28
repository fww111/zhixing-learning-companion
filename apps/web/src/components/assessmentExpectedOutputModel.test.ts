import { expectedCodeOutputForAssessment } from "./assessmentExpectedOutputModel.js";

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

test("assessment code expected output comes from the generated challenge", () => {
  assert(
    expectedCodeOutputForAssessment("1.1.1 Python语言的特点 达标\n") === "1.1.1 Python语言的特点 达标",
    "generated challenge expected output should be normalized before submit"
  );
  assert(
    expectedCodeOutputForAssessment("   ") === "",
    "blank generated output should stay blank"
  );
});
