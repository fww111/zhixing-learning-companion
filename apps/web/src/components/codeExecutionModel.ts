import { runCodeSubmission, type CodeRunResultPayload } from "../api/client";
import { runInlinePythonLikeCode } from "./postClassroomExperienceModel";

export interface CodeExecutionOutcome {
  output: string;
  /** 服务端真实沙箱判定结果；降级（离线模拟）时为 null */
  verdict: CodeRunResultPayload["verdict"] | null;
  passed: boolean | null;
  serverVerified: boolean;
  message: string;
  /** 错误类别提示（编译错/运行错/超时/输出不一致），供 UI 徽标 */
  category: "ok" | "compile" | "runtime" | "timeout" | "mismatch" | "offline";
}

/** 按代码内容启发语言：含 #include / main( 视为 C++，否则按 Python 处理。 */
export function detectCodeLanguage(source: string): "cpp" | "python" {
  return /#include|std::|int\s+main\s*\(/.test(source) ? "cpp" : "python";
}

/**
 * 统一的代码执行入口：优先走服务端真实沙箱（判分可信、答辩可讲），
 * 后端不可用时降级为浏览器内模拟并在结果中显式标注"离线模拟"。
 */
export async function executeCode(input: {
  token: string | undefined;
  courseId: number | undefined;
  source: string;
  expectedOutput?: string;
  stdinText?: string;
}): Promise<CodeExecutionOutcome> {
  const language = detectCodeLanguage(input.source);
  if (!input.courseId || !input.token) {
    return offlineFallback(input.source, input.expectedOutput);
  }
  try {
    const result = await runCodeSubmission(input.token, input.courseId, {
      source: input.source,
      language,
      expected_output: input.expectedOutput || "",
      stdin_text: input.stdinText || ""
    });
    const category: CodeExecutionOutcome["category"] =
      result.verdict === "accepted"
        ? "ok"
        : result.verdict === "compile_error"
          ? "compile"
          : result.verdict === "timeout"
            ? "timeout"
            : result.verdict === "runtime_error"
              ? "runtime"
              : "mismatch";
    return {
      output: result.stdout || result.compile_output || result.stderr || "（无输出）",
      verdict: result.verdict,
      passed: result.passed,
      serverVerified: true,
      message: result.message,
      category
    };
  } catch {
    return offlineFallback(input.source, input.expectedOutput);
  }
}

function offlineFallback(source: string, expectedOutput?: string): CodeExecutionOutcome {
  const output = runInlinePythonLikeCode(source);
  const expected = (expectedOutput || "").replace(/\r\n/g, "\n").trim();
  const passed = Boolean(expected) && output.replace(/\r\n/g, "\n").trim() === expected;
  return {
    output,
    verdict: null,
    passed,
    serverVerified: false,
    message: passed ? "离线模拟运行通过（结果仅供参考）" : "离线模拟运行完成，结果仅供参考",
    category: passed ? "ok" : "offline"
  };
}
