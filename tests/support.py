"""测试用的公共外壳：跑仓库脚本、构建到固定产物目录。

三个测试模块原本各抄一份 run()/build()，改动一处要同步三处，因此收在这里。
"""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=ROOT):
    """在仓库根跑一个脚本，返回 CompletedProcess（文本模式，UTF-8）。"""
    return subprocess.run(
        [sys.executable] + [str(arg) for arg in args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def build(*extra):
    """跑 tools/build.py；失败就把 stdout/stderr 一起抛出来，别让断言空转。"""
    result = run("tools/build.py", *extra)
    if result.returncode != 0:
        raise AssertionError(
            "build failed (%s)\nstdout:\n%s\nstderr:\n%s"
            % (result.returncode, result.stdout, result.stderr)
        )
    return result
