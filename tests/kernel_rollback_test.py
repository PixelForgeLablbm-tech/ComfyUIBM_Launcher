# -*- coding: utf-8 -*-
"""内核维护「事务式安装」测试：失败不破坏原有版本。

覆盖：
  - 纯函数：torch/torchvision 配对、包名提取、+cu 索引反推、失败原因分析；
  - 编排：预检失败不碰环境 / 安装失败自动回滚 / 验证失败自动回滚 /
    全部通过不回滚 / torch 参数按版本配对；
  - 回滚索引必须取"旧版本来源"，不能被新安装的索引覆盖；
  - _stream_pip 实时输出、ANSI 清理、超时终止。

运行: python tests/kernel_rollback_test.py
"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher import kernel_manager as km  # noqa: E402


class FakeInst:
    def __init__(self, python="python.exe"):
        self.path = os.getcwd()
        self._python = python

    def resolve_python(self, fallback):
        return self._python or fallback


CU126 = "https://download.pytorch.org/whl/cu126"
SNAP = {
    "pkgs": {"torch": "2.7.1+cu126", "torchvision": "0.22.1+cu126",
             "torchaudio": "2.7.1+cu126"},
    "index": CU126,
    "file": None,
    "names": ["torch", "torchvision", "torchaudio"],
}


class PureTests(unittest.TestCase):
    def test_torch_pair(self):
        self.assertEqual(km._torch_pair("2.7.1"), ("0.22.1", "2.7.1"))
        self.assertEqual(km._torch_pair("2.0.0"), ("0.15.0", "2.0.0"))
        self.assertEqual(km._torch_pair("2.13.0"), ("0.28.0", "2.13.0"))
        self.assertEqual(km._torch_pair(""), ("", ""))

    def test_spec_names(self):
        self.assertEqual(km._spec_names("sageattention==2.2.0"),
                         ["sageattention"])
        self.assertEqual(km._spec_names("torch torchvision torchaudio"),
                         ["torch", "torchvision", "torchaudio"])
        self.assertEqual(km._spec_names(""), [])

    def test_cu_index(self):
        self.assertEqual(km._cu_index_from_version("2.7.1+cu126"), CU126)
        self.assertEqual(km._cu_index_from_version("2.7.1"), "")

    def test_analyze_failure(self):
        self.assertIn("网络连接失败",
                      km._analyze_failure("connection timed out"))
        self.assertIn("找不到匹配版本", km._analyze_failure(
            "ERROR: Could not find a version that satisfies the requirement "
            "torch==2.1.2 (from versions: 2.2.0+cu118, ...)"))
        self.assertIn("磁盘空间不足",
                      km._analyze_failure("no space left on device"))
        self.assertIn("下载中断",
                      km._analyze_failure("connection reset by peer"))


class TransactionTests(unittest.TestCase):
    def _patch(self, dry=(True, "", ""), stream=(0, "done"),
               verify=(True, "ok")):
        patches = [
            mock.patch("launcher.kernel_manager._pip_dry_run",
                       return_value=dry),
            mock.patch("launcher.kernel_manager._stream_pip",
                       return_value=stream),
            mock.patch("launcher.kernel_manager._verify_kernel",
                       return_value=verify),
            mock.patch("launcher.kernel_manager._snapshot_packages",
                       return_value=dict(SNAP)),
            mock.patch("launcher.kernel_manager._rollback",
                       return_value=(True, "已恢复原版本")),
        ]
        started = {}
        for p in patches:
            started[p.attribute] = p.start()
            self.addCleanup(p.stop)
        return {"dry": started["_pip_dry_run"],
                "stream": started["_stream_pip"],
                "verify": started["_verify_kernel"],
                "snap": started["_snapshot_packages"],
                "rollback": started["_rollback"]}

    def test_precheck_fail_never_touches_env(self):
        """预检失败：不执行安装、不执行回滚，原环境保持不变。"""
        m = self._patch(dry=(False, "找不到匹配版本：torch 无可用轮子",
                             "ERROR: Could not find a version"))
        with self.assertRaises(RuntimeError) as ctx:
            km.install_torch(FakeInst(), "cu126", {}, version="2.7.1")
        msg = str(ctx.exception)
        self.assertIn("预检未通过", msg)
        self.assertIn("原版本保持不变", msg)
        self.assertIn("Could not find a version", msg)  # 预检输出可见
        m["stream"].assert_not_called()   # 正式安装从未发生
        m["rollback"].assert_not_called()  # 无需回滚

    def test_install_fail_rolls_back(self):
        """安装失败：自动回滚并提示环境未被破坏。"""
        m = self._patch(stream=(1, "ERROR: connection reset by peer"))
        with self.assertRaises(RuntimeError) as ctx:
            km.install_torch(FakeInst(), "cu126", {}, version="2.7.1")
        msg = str(ctx.exception)
        self.assertIn("安装失败", msg)
        self.assertIn("已自动恢复原版本", msg)
        self.assertIn("下载中断", msg)
        m["rollback"].assert_called_once()

    def test_verify_fail_rolls_back(self):
        """pip 成功但 import 验证失败（装成残破组合）：同样自动回滚。"""
        m = self._patch(stream=(0, "done"),
                        verify=(False, "import torch: DLL load failed"))
        with self.assertRaises(RuntimeError) as ctx:
            km.install_torch(FakeInst(), "cu126", {}, version="2.7.1")
        msg = str(ctx.exception)
        self.assertIn("安装后验证失败", msg)
        self.assertIn("DLL load failed", msg)
        self.assertIn("已自动恢复原版本", msg)
        m["rollback"].assert_called_once()

    def test_all_ok_no_rollback(self):
        """安装 + 验证全部通过：不执行回滚，进度给出验证结果。"""
        progress = []
        m = self._patch(stream=(0, "done"),
                        verify=(True, "torch=2.7.1+cu126; torchvision=0.22.1; "
                                      "torchaudio=2.7.1; cuda=True"))
        km.install_torch(FakeInst(), "cu126", {}, progress.append,
                         version="2.7.1")
        m["rollback"].assert_not_called()
        joined = "\n".join(progress)
        self.assertIn("验证通过", joined)
        self.assertIn("torch=2.7.1+cu126", joined)

    def test_torch_pins_paired_versions(self):
        """指定版本时 torchvision/torchaudio 按官方配套锁定。"""
        m = self._patch(stream=(0, "done"),
                        verify=(True, "torch=2.7.1; cuda=True"))
        km.install_torch(FakeInst(), "cu126", {}, version="2.7.1")
        args = m["stream"].call_args[0][1]
        self.assertIn("torch==2.7.1", args)
        self.assertIn("torchvision==0.22.1", args)
        self.assertIn("torchaudio==2.7.1", args)
        self.assertIn("--index-url", args)
        self.assertIn(CU126, args)

    def test_torch_latest_not_pinned(self):
        """最新版：三个包都不锁版本，并带 --upgrade。"""
        m = self._patch(stream=(0, "done"), verify=(True, "torch=ok"))
        km.install_torch(FakeInst(), "cu126", {})
        args = m["stream"].call_args[0][1]
        self.assertIn("torch", args)
        self.assertIn("torchvision", args)
        self.assertIn("torchaudio", args)
        self.assertIn("--upgrade", args)

    def test_rollback_uses_old_index_not_new(self):
        """回滚索引必须来自旧版本（cu126），不能被新装的 cu130 覆盖。"""
        m = self._patch(stream=(1, "boom"))
        with self.assertRaises(RuntimeError):
            km.install_torch(FakeInst(), "cu130", {}, version="2.13.0")
        _, snapshot = m["rollback"].call_args[0][:2]
        self.assertEqual(snapshot["index"], CU126)

    def test_rollback_uses_direct_url(self):
        """wheel 直链装的包（GitHub 轮子不在 pip 索引上）回滚时先按原 URL
        下载，再装本地轮子文件。"""
        snap = {
            "pkgs": {"sageattention": {
                "version": "2.2.0+cu130torch2.9.0andhigher.post4",
                "url": "https://github.com/woct0rdho/SageAttention/releases/"
                       "download/v2.2.0-windows.post4/sageattention-2.2.0%2B"
                       "cu130torch2.9.0andhigher.post4-cp39-abi3-win_amd64.whl"}},
            "index": "", "file": None,
            "names": ["sageattention"],
        }
        with mock.patch.object(km, "_download_file",
                               return_value="mock") as dl, \
                mock.patch.object(km, "_stream_pip",
                                  return_value=(0, "done")) as sp:
            ok, msg = km._rollback("python.exe", snap, {}, os.getcwd(), None)
        self.assertTrue(ok)
        self.assertEqual(dl.call_args[0][0],
                         snap["pkgs"]["sageattention"]["url"])
        # 回滚下载到本地后安装该文件
        local = os.path.join(
            tempfile.gettempdir(),
            "sageattention-2.2.0+cu130torch2.9.0andhigher.post4-"
            "cp39-abi3-win_amd64.whl")
        self.assertEqual(str(dl.call_args[0][1]), local)
        args = [str(a) for a in sp.call_args[0][1]]
        self.assertIn(local, args)        # 装本地下载好的轮子
        self.assertIn("--no-deps", args)
        self.assertNotIn("--index-url", args)

    def test_install_package_generic(self):
        """通用安装（xformers 等）同样走事务式：失败回滚。"""
        m = self._patch(stream=(1, "boom"))
        with self.assertRaises(RuntimeError) as ctx:
            km.install_package(FakeInst(), "xformers", {}, lambda s: None)
        self.assertIn("已自动恢复原版本", str(ctx.exception))
        m["rollback"].assert_called_once()


class StreamPipTests(unittest.TestCase):
    """真实子进程验证 _stream_pip：实时输出 / ANSI 清理 / 超时终止。"""

    def test_realtime_lines(self):
        lines = []
        code = ("import sys\n"
                "for i in range(3):\n"
                "    print('line%d' % i)\n"
                "    sys.stdout.flush()\n")
        rc, out = km._stream_pip(sys.executable, ["-c", code],
                                 dict(os.environ), tempfile.gettempdir(),
                                 lines.append, 60)
        self.assertEqual(rc, 0)
        self.assertIn("line0", out)
        self.assertIn("line1", lines)

    def test_ansi_stripped(self):
        lines = []
        code = "print('\\x1b[31mhello\\x1b[0m')"
        rc, out = km._stream_pip(sys.executable, ["-c", code],
                                 dict(os.environ), tempfile.gettempdir(),
                                 lines.append, 60)
        self.assertEqual(rc, 0)
        self.assertEqual(lines, ["hello"])

    def test_timeout_kills(self):
        lines = []
        code = "import time\nprint('start')\ntime.sleep(30)\nprint('end')"
        rc, out = km._stream_pip(sys.executable, ["-c", code],
                                 dict(os.environ), tempfile.gettempdir(),
                                 lines.append, 2)
        self.assertEqual(rc, -1)
        self.assertIn("超时", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
