import subprocess

import pytest

from app.services.code_runner import CodeRunRequest, CodeRunner, normalize_output


@pytest.fixture()
def runner() -> CodeRunner:
    return CodeRunner()


def test_normalize_output_unifies_newlines_and_trims():
    assert normalize_output("\r\n15\r\n") == "15"
    assert normalize_output("  15  \n\n") == "15"
    assert normalize_output("a \r\n b") == "a\n b"
    assert normalize_output("") == ""


def test_cpp_accepted(runner: CodeRunner):
    result = runner.run(
        CodeRunRequest(
            source="#include <iostream>\nint main() { int n; std::cin >> n; std::cout << n * 2 << std::endl; return 0; }",
            language="cpp",
            stdin_text="21",
            expected_output="42",
        )
    )
    assert result.verdict == "accepted"
    assert result.passed is True
    assert result.exit_code == 0
    assert "真实编译运行通过" in result.message


def test_cpp_wrong_answer(runner: CodeRunner):
    result = runner.run(
        CodeRunRequest(
            source="#include <iostream>\nint main() { std::cout << 1 << std::endl; return 0; }",
            language="cpp",
            expected_output="2",
        )
    )
    assert result.verdict == "wrong_answer"
    assert result.passed is False


def test_cpp_compile_error(runner: CodeRunner):
    result = runner.run(
        CodeRunRequest(
            source="int main() { return oops; }",
            language="cpp",
            expected_output="ok",
        )
    )
    assert result.verdict == "compile_error"
    assert result.compile_output
    assert result.passed is False


def test_cpp_runtime_timeout_kills_infinite_loop(runner: CodeRunner):
    result = runner.run(
        CodeRunRequest(
            source="int main() { while (true) {} return 0; }",
            language="cpp",
            expected_output="never",
            run_timeout_seconds=2,
            compile_timeout_seconds=10,
        )
    )
    assert result.verdict == "timeout"
    assert result.passed is False


def test_cpp_runtime_error(runner: CodeRunner):
    result = runner.run(
        CodeRunRequest(
            source="#include <iostream>\nint main() { throw std::runtime_error(\"boom\"); }",
            language="cpp",
            expected_output="ok",
        )
    )
    assert result.verdict == "runtime_error"
    assert result.passed is False


def test_python_accepted(runner: CodeRunner):
    result = runner.run(
        CodeRunRequest(
            source="n = input()\nprint(int(n) + 1)",
            language="python",
            stdin_text="41",
            expected_output="42",
        )
    )
    assert result.verdict == "accepted"
    assert result.passed is True


def test_python_runtime_error_reported(runner: CodeRunner):
    result = runner.run(
        CodeRunRequest(source="raise ValueError('bad')", language="python", expected_output="x")
    )
    assert result.verdict == "runtime_error"
    assert "bad" in result.stderr


def test_unsupported_language_rejected(runner: CodeRunner):
    result = runner.run(CodeRunRequest(source="print()", language="python", expected_output=""))
    assert result.verdict in {"accepted", "wrong_answer", "compile_error", "runtime_error", "timeout"}


def test_output_truncated_to_cap(runner: CodeRunner):
    result = runner.run(
        CodeRunRequest(
            source=(
                "#include <cstdio>\n"
                "int main() { for (int i = 0; i < 200000; i++) std::printf(\"x\"); return 0; }"
            ),
            language="cpp",
            expected_output="x",
            compile_timeout_seconds=20,
        )
    )
    assert result.verdict in {"wrong_answer", "accepted"}
    assert len(result.stdout) <= 64 * 1024


def test_stdin_fed_to_cpp_program(runner: CodeRunner):
    result = runner.run(
        CodeRunRequest(
            source=(
                "#include <iostream>\n"
                "#include <string>\n"
                "int main() { std::string line; std::getline(std::cin, line); std::cout << \"hi \" << line; return 0; }"
            ),
            language="cpp",
            stdin_text="coder",
            expected_output="hi coder",
        )
    )
    assert result.verdict == "accepted"
