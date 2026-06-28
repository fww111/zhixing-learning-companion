import { summarizeUploadSelection, uploadProgressLabel } from "./materialUploadModel.js";

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

function fakeFile(name: string, size: number): File {
  return { name, size } as File;
}

test("summarizes multiple selected course material files", () => {
  const summary = summarizeUploadSelection([
    fakeFile("chapter-1.pptx", 100),
    fakeFile("chapter-2.pptx", 240)
  ]);

  assert(summary?.fileCount === 2, "should count selected files");
  assert(summary.totalBytes === 340, "should sum selected file sizes");
  assert(summary.label.includes("待上传 2 个文件"), "multi-file label should show count");
  assert(summary.label.includes("chapter-1.pptx"), "multi-file label should include names");
});

test("uses a compact upload progress label for multiple files", () => {
  assert(uploadProgressLabel(1, 3) === "上传中 2/3", "progress should show the one-based current file");
  assert(uploadProgressLabel(0, 1) === "上传中", "single file upload keeps the original label");
});
