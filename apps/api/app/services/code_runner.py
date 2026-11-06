from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Literal

from pydantic import BaseModel, Field

CodeLanguage = Literal["cpp", "python"]
CodeVerdict = Literal["accepted", "wrong_answer", "compile_error", "runtime_error", "timeout"]

MAX_OUTPUT_BYTES = 64 * 1024
COMPILE_TIMEOUT_SECONDS = 15
RUN_TIMEOUT_SECONDS = 5
MAX_SOURCE_CHARS = 60_000
MAX_STDIN_CHARS = 20_000

SUPPORTED_LANGUAGES = ("cpp", "python")


class CodeRunRequest(BaseModel):
    source: str = Field(min_length=1, max_length=MAX_SOURCE_CHARS)
    language: CodeLanguage = "cpp"
    stdin_text: str = Field(default="", max_length=MAX_STDIN_CHARS)
    expected_output: str = Field(default="", max_length=4000)
    compile_timeout_seconds: int = Field(default=COMPILE_TIMEOUT_SECONDS, ge=3, le=30)
    run_timeout_seconds: int = Field(default=RUN_TIMEOUT_SECONDS, ge=1, le=15)


class CodeRunResult(BaseModel):
    verdict: CodeVerdict
    passed: bool
    stdout: str = ""
    stderr: str = ""
    compile_output: str = ""
    exit_code: int | None = None
    execution_ms: int = 0
    expected_output: str = ""
    server_verified: bool = True
    message: str = ""


def _truncate(text: str) -> str:
    return text[:MAX_OUTPUT_BYTES]


def normalize_output(text: str) -> str:
    """输出归一化：统一换行、去首尾空白、丢弃行尾多余空格。"""
    unified = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in unified.split("\n")]
    while lines and lines[0] == "":
        lines.pop(0)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).strip()


class CodeRunner:
    """服务端真实代码执行与判分。

    开发环境直接用本机工具链（g++ / python）；生产 Linux 建议以容器/受限
    用户运行（见 deployment 文档），本模块只负责超时、输出截断与判分。
    """

    def __init__(self, gpp_path: str = "g++", python_path: str = sys.executable) -> None:
        self.gpp_path = gpp_path
        self.python_path = python_path

    def run(self, request: CodeRunRequest) -> CodeRunResult:
        if request.language not in SUPPORTED_LANGUAGES:
            return CodeRunResult(
                verdict="compile_error",
                passed=False,
                message=f"不支持的语言：{request.language}",
                expected_output=request.expected_output,
            )

        workdir = tempfile.mkdtemp(prefix="code_runner_")
        try:
            if request.language == "cpp":
                return self._run_cpp(request, workdir)
            return self._run_python(request, workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    # ------------------------------------------------------------------ runners
    def _run_cpp(self, request: CodeRunRequest, workdir: str) -> CodeRunResult:
        source_path = os.path.join(workdir, "main.cpp")
        binary_path = os.path.join(workdir, "main.exe" if os.name == "nt" else "main")
        with open(source_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(request.source)

        compile_started = time.perf_counter()
        try:
            compile_result = subprocess.run(
                [self.gpp_path, "-std=c++17", "-O0", "-pipe", "-o", binary_path, source_path],
                capture_output=True,
                text=True,
                timeout=request.compile_timeout_seconds,
                cwd=workdir,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return CodeRunResult(
                verdict="compile_error",
                passed=False,
                compile_output=_truncate(f"编译超时（>{request.compile_timeout_seconds}s）"),
                expected_output=request.expected_output,
                message="编译超时，请检查代码是否包含编译器无法处理的构造。",
            )
        except FileNotFoundError:
            return CodeRunResult(
                verdict="compile_error",
                passed=False,
                compile_output="服务端未安装 g++ 编译器",
                expected_output=request.expected_output,
                message="运行环境缺少 C++ 编译器，请联系管理员。",
            )
        compile_ms = int((time.perf_counter() - compile_started) * 1000)

        if compile_result.returncode != 0:
            return CodeRunResult(
                verdict="compile_error",
                passed=False,
                compile_output=_truncate(compile_result.stderr or compile_result.stdout or "编译失败"),
                exit_code=compile_result.returncode,
                execution_ms=compile_ms,
                expected_output=request.expected_output,
                message="编译失败，请根据编译器输出修正语法错误。",
            )

        run_started = time.perf_counter()
        try:
            run_result = subprocess.run(
                [binary_path],
                capture_output=True,
                text=True,
                timeout=request.run_timeout_seconds,
                cwd=workdir,
                input=request.stdin_text,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return CodeRunResult(
                verdict="timeout",
                passed=False,
                stdout=_truncate("（程序运行超时被终止）"),
                expected_output=request.expected_output,
                execution_ms=int((time.perf_counter() - run_started) * 1000),
                message=f"运行超过 {request.run_timeout_seconds} 秒被终止，请检查是否存在死循环或等待输入。",
            )
        except OSError as exc:
            return CodeRunResult(
                verdict="runtime_error",
                passed=False,
                stderr=_truncate(str(exc)),
                expected_output=request.expected_output,
                execution_ms=int((time.perf_counter() - run_started) * 1000),
                message="程序无法启动运行。",
            )
        return self._grade(request, run_result.stdout, run_result.stderr, run_result.returncode, run_started)

    def _run_python(self, request: CodeRunRequest, workdir: str) -> CodeRunResult:
        source_path = os.path.join(workdir, "main.py")
        with open(source_path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(request.source)

        run_started = time.perf_counter()
        try:
            run_result = subprocess.run(
                [self.python_path, "-I", source_path],
                capture_output=True,
                text=True,
                timeout=request.run_timeout_seconds,
                cwd=workdir,
                input=request.stdin_text,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            return CodeRunResult(
                verdict="timeout",
                passed=False,
                stdout=_truncate("（程序运行超时被终止）"),
                expected_output=request.expected_output,
                execution_ms=int((time.perf_counter() - run_started) * 1000),
                message=f"运行超过 {request.run_timeout_seconds} 秒被终止，请检查是否存在死循环或等待输入。",
            )
        return self._grade(request, run_result.stdout, run_result.stderr, run_result.returncode, run_started)

    # ------------------------------------------------------------------- grading
    def _grade(
        self,
        request: CodeRunRequest,
        stdout: str,
        stderr: str,
        exit_code: int,
        run_started: float,
    ) -> CodeRunResult:
        execution_ms = int((time.perf_counter() - run_started) * 1000)
        truncated_stdout = _truncate(stdout)
        truncated_stderr = _truncate(stderr)

        if exit_code != 0:
            return CodeRunResult(
                verdict="runtime_error",
                passed=False,
                stdout=truncated_stdout,
                stderr=truncated_stderr or f"进程以退出码 {exit_code} 结束",
                exit_code=exit_code,
                execution_ms=execution_ms,
                expected_output=request.expected_output,
                message="程序运行时出错，请检查数组越界、除零或未处理的输入。",
            )

        expected = normalize_output(request.expected_output)
        actual = normalize_output(truncated_stdout)
        if expected and actual == expected:
            return CodeRunResult(
                verdict="accepted",
                passed=True,
                stdout=truncated_stdout,
                stderr=truncated_stderr,
                exit_code=exit_code,
                execution_ms=execution_ms,
                expected_output=request.expected_output,
                message="真实编译运行通过，输出与期望一致。",
            )
        if not expected and exit_code == 0:
            # 自由练习模式：无期望输出，程序正常退出即视为运行成功
            return CodeRunResult(
                verdict="accepted",
                passed=True,
                stdout=truncated_stdout,
                stderr=truncated_stderr,
                exit_code=exit_code,
                execution_ms=execution_ms,
                expected_output=request.expected_output,
                message="真实编译运行成功（本练习未设置期望输出判分）。",
            )
        return CodeRunResult(
            verdict="wrong_answer",
            passed=False,
            stdout=truncated_stdout,
            stderr=truncated_stderr,
            exit_code=exit_code,
            execution_ms=execution_ms,
            expected_output=request.expected_output,
            message="程序正常运行，但输出与期望不一致。",
        )


def build_default_runner() -> CodeRunner:
    gpp = os.environ.get("CODE_RUNNER_GPP", "g++")
    python_path = os.environ.get("CODE_RUNNER_PYTHON", sys.executable)
    return CodeRunner(gpp_path=gpp, python_path=python_path)
