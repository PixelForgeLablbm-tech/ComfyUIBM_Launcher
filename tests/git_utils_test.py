# -*- coding: utf-8 -*-
"""git_utils 测试：safe.directory 自动注入（免 dubious ownership 报错）。

运行: python tests/git_utils_test.py
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher import git_utils  # noqa: E402


class RunGitSafeDirTests(unittest.TestCase):
    @staticmethod
    def _fake_run(*_a, **_k):
        return mock.Mock(returncode=0, stdout="true", stderr="")

    def test_injects_safe_directory(self):
        """每条 git 命令自动带 -c safe.directory=<仓库路径>（正斜杠）。"""
        with mock.patch.object(git_utils.subprocess, "run",
                               side_effect=self._fake_run) as mr:
            git_utils.run_git(r"C:\Repo\Path", "rev-parse",
                              "--is-inside-work-tree", check=False)
        cmd = mr.call_args[0][0]
        self.assertEqual(cmd[0], "git")
        self.assertIn("-c", cmd)
        self.assertIn("safe.directory=C:/Repo/Path", cmd)
        self.assertIn("rev-parse", cmd)

    def test_safe_directory_coexists_with_extra_args(self):
        """与 GitHub 加速等 -c 参数共存，互不影响。"""
        with mock.patch.object(git_utils.subprocess, "run",
                               side_effect=self._fake_run) as mr:
            git_utils.run_git(
                r"E:\AI\x", "fetch", "origin",
                extra_args=["-c", "url.https://gh-proxy.com/.insteadOf="
                                  "https://github.com/"])
        cmd = mr.call_args[0][0]
        self.assertIn("safe.directory=E:/AI/x", cmd)
        self.assertIn("url.https://gh-proxy.com/.insteadOf="
                      "https://github.com/", cmd)

    def test_no_cwd_no_injection(self):
        with mock.patch.object(git_utils.subprocess, "run",
                               side_effect=self._fake_run) as mr:
            git_utils.run_git(None, "version", check=False)
        cmd = mr.call_args[0][0]
        self.assertEqual(cmd, ["git", "version"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
