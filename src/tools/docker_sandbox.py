"""
Docker 沙箱执行封装（可选功能）。
当 DOCKER_ENABLED=true 时启用，否则回退到本地执行。
"""

from __future__ import annotations

import subprocess
from typing import Dict, Any


class DockerSandbox:
    """
    Docker 隔离执行器：在容器内运行 pytest 测试。

    属性:
        image: Docker 镜像名称。
        timeout: 最大执行时间（秒）。
    """

    def __init__(self, image: str = "python:3.11-slim", timeout: int = 30) -> None:
        self.image = image
        self.timeout = timeout

    def run_tests(
        self,
        test_code: str,
        target_code: str,
    ) -> Dict[str, Any]:
        """
        在 Docker 容器中运行测试。

        Args:
            test_code: pytest 测试代码。
            target_code: 被测代码。

        Returns:
            测试结果字典（passed, output, coverage, failed_cases）。

        Raises:
            subprocess.TimeoutExpired: 容器执行超时。
        """
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            # 写入被测代码和测试代码
            target_file = os.path.join(tmpdir, "target.py")
            test_file = os.path.join(tmpdir, "test_target.py")

            with open(target_file, "w") as f:
                f.write(target_code)
            with open(test_file, "w") as f:
                f.write(test_code)

            # 构建 Docker 命令
            cmd = [
                "docker", "run",
                "--rm",
                "-v", f"{tmpdir}:/workspace",
                "-w", "/workspace",
                self.image,
                "python", "-m", "pytest",
                test_file,
                "-v", "--tb=short",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )

            output = result.stdout + result.stderr
            passed = result.returncode == 0

            return {
                "passed": passed,
                "output": output,
                "coverage": 0.0,  # Docker 模式暂不支持覆盖率统计
                "failed_cases": [],
            }
