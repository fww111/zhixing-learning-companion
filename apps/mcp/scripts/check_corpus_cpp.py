"""Compile-check every ```cpp block in the C++ corpus with g++ -std=c++17.

Complete programs (contain `int main`) are compiled as-is; code fragments get a
preamble of the common loop/accumulator variables they reference.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[3] / "data" / "seed" / "cpp_algorithms" / "corpus"

FRAGMENT_PREAMBLE = """
#include <bits/stdc++.h>
using namespace std;
int n = 5, m = 5, q = 5, cnt = 0, blocks = 0;
long long sum = 0, target = 10;
vector<int> a(10, 1);
vector<string> grid(3, string(3, '.'));
vector<vector<bool>> vis(3, vector<bool>(3, false));
vector<vector<int>> g(3, vector<int>(3, 0));
vector<pair<long long, long long>> seg(3, {1, 2});
"""

PATTERNS = [
    (re.compile(r"```cpp\n(.*?)```", re.DOTALL), "corpus"),
]

def try_compile(src: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["g++", "-std=c++17", "-fsyntax-only", str(src)],
        capture_output=True,
        text=True,
    )


def main() -> int:
    failures = 0
    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        for md in sorted(CORPUS.glob("chapter-*.md")):
            blocks = re.findall(r"```cpp\n(.*?)```", md.read_text(encoding="utf-8"), re.DOTALL)
            for index, block in enumerate(blocks, start=1):
                total += 1
                standalone = "int main" in block
                candidates = [] if standalone else [
                    # 函数/结构体等声明片段：原样作为翻译单元
                    FRAGMENT_PREAMBLE + block,
                    # 裸语句片段：包进函数体
                    FRAGMENT_PREAMBLE + "int main() {\n" + block + "\nreturn 0;\n}\n",
                ]
                if standalone:
                    candidates = [block]
                src = Path(tmp) / f"{md.stem}-{index}.cpp"
                src.write_text(candidates[0], encoding="utf-8")
                result = try_compile(src)
                strategy = "standalone" if standalone else "fragment"
                if result.returncode != 0 and len(candidates) > 1:
                    src.write_text(candidates[1], encoding="utf-8")
                    result = try_compile(src)
                    strategy = "fragment-wrapped"
                if result.returncode != 0:
                    failures += 1
                    print(f"FAIL {md.name} block#{index} ({strategy})")
                    print("\n".join("    " + line for line in result.stderr.strip().splitlines()[:6]))
                else:
                    print(f"ok   {md.name} block#{index} ({strategy})")
    print(f"\n{total - failures}/{total} cpp blocks compile")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
