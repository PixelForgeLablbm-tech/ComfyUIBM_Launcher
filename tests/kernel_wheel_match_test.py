# -*- coding: utf-8 -*-
"""内核 wheel 匹配逻辑测试（参考 TE 启动器实测方法实现，但补上版本匹配）。

运行: python tests/kernel_wheel_match_test.py
"""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher import kernel_manager as km  # noqa: E402


class VerTests(unittest.TestCase):
    def test_ver_key(self):
        self.assertEqual(km._ver_key("2.7.1"), (2, 7, 1, 0))
        self.assertEqual(km._ver_key("2.9.0.post4"), (2, 9, 0, 4))

    def test_ver_ge(self):
        self.assertTrue(km._ver_ge("2.9.1", "2.9.0"))
        self.assertFalse(km._ver_ge("2.7.1", "2.9.0"))


# 模拟 woct0rdho/SageAttention releases（对齐真实命名规则）
SAGE_RELEASES = [
    {"tag_name": "v2.2.0-windows.post6", "assets": [
        {"name": "sageattention-2.2.0+cu128torch2.10.0andhigher.post6-cp310-abi3-win_amd64.whl",
         "browser_download_url": "u://post6-cu128-andhigher-2.10"},
        {"name": "sageattention-2.2.0+cu128torch2.9.1.post6-cp310-abi3-win_amd64.whl",
         "browser_download_url": "u://post6-cu128-2.9.1"},
    ]},
    {"tag_name": "v2.2.0-windows.post4", "assets": [
        {"name": "sageattention-2.2.0+cu128torch2.9.0andhigher.post4-cp39-abi3-win_amd64.whl",
         "browser_download_url": "u://post4-cu128-andhigher-2.9.0"},
        {"name": "sageattention-2.2.0+cu130torch2.9.0andhigher.post4-cp39-abi3-win_amd64.whl",
         "browser_download_url": "u://post4-cu130-andhigher"},
    ]},
    {"tag_name": "v2.2.0-windows.post3", "assets": [
        {"name": "sageattention-2.2.0+cu128torch2.7.1.post3-cp39-abi3-win_amd64.whl",
         "browser_download_url": "u://post3-cu128-2.7.1"},
        {"name": "sageattention-2.2.0+cu128torch2.8.0.post3-cp39-abi3-win_amd64.whl",
         "browser_download_url": "u://post3-cu128-2.8.0"},
    ]},
    {"tag_name": "v2.2.0-windows.post1", "assets": [
        {"name": "sageattention-2.2.0+cu128torch2.7.1.post1-cp39-abi3-win_amd64.whl",
         "browser_download_url": "u://post1-cu128-2.7.1"},
    ]},
    {"tag_name": "v2.2.0-windows", "assets": [
        {"name": "sageattention-2.2.0+cu128torch2.7.1-cp312-cp312-win_amd64.whl",
         "browser_download_url": "u://base-cu128-2.7.1-cp312"},
    ]},
]


class SageAttentionMatchTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(km, "_http_json", return_value=SAGE_RELEASES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_exact_preferred_over_newer_andhigher(self):
        """torch 2.7.1 + cu128：精确版（post3）优先于 post4 的 andhigher。"""
        url, name = km._match_sageattention_wheel("2.7.1", "cu128")
        self.assertIn("2.7.1", name)
        self.assertEqual(url, "u://post3-cu128-2.7.1")

    def test_andhigher_covers(self):
        """torch 2.9.0 + cu128：post4 的 andhigher(>=2.9.0) 覆盖。"""
        url, name = km._match_sageattention_wheel("2.9.0", "cu128")
        self.assertIn("2.9.0andhigher", name)
        self.assertEqual(url, "u://post4-cu128-andhigher-2.9.0")

    def test_exact_9_1_preferred(self):
        """torch 2.9.1 + cu128：post6 精确版胜出。"""
        url, name = km._match_sageattention_wheel("2.9.1", "cu128")
        self.assertIn("2.9.1.post6", name)
        self.assertEqual(url, "u://post6-cu128-2.9.1")

    def test_cu_must_match(self):
        """cu 不匹配（cu130）不能选 cu128 的轮子。"""
        self.assertIsNone(km._match_sageattention_wheel("2.7.1", "cu130"))

    def test_no_match(self):
        """torch 2.5.0 + cu128：没有任何轮子覆盖 → None。"""
        self.assertIsNone(km._match_sageattention_wheel("2.5.0", "cu128"))


# 模拟 PyPI xformers 索引（对齐真实 requires_dist：torch==2.8.0）
PYPI_IDX = {"releases": {
    "0.0.35": {}, "0.0.34": {}, "0.0.33": {}, "0.0.32.post2": {},
    "0.0.31": {}, "0.0.30": {}, "0.0.29": {},
}}
PYPI_DATA = {
    "0.0.32.post2": {"info": {"requires_dist": ["numpy", "torch==2.8.0"]},
                     "urls": [{"filename": "xformers-0.0.32.post2-cp39-abi3-win_amd64.whl",
                               "url": "u://pypi/xformers-0.0.32.post2.whl"}]},
    "0.0.31": {"info": {"requires_dist": ["numpy", "torch==2.7.0"]},
               "urls": [{"filename": "xformers-0.0.31-cp39-abi3-win_amd64.whl",
                         "url": "u://pypi/xformers-0.0.31.whl"}]},
}


class XformersMatchTests(unittest.TestCase):
    def setUp(self):
        def fake(url, timeout=30):
            if url.endswith("xformers/json"):
                return PYPI_IDX
            v = url.split("/pypi/xformers/")[1].split("/json")[0]
            if v in PYPI_DATA:
                return PYPI_DATA[v]
            return {"info": {"requires_dist": []}, "urls": []}
        patcher = mock.patch.object(km, "_http_json", side_effect=fake)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_match_torch_2_8(self):
        ver, url = km._match_xformers_wheel("2.8.0")
        self.assertEqual(ver, "0.0.32.post2")
        self.assertIn("0.0.32.post2.whl", url)

    def test_no_match_torch_2_7_1(self):
        """torch 2.7.1 无对应 Windows 轮子 → None（避免 TE 的错配）。"""
        self.assertIsNone(km._match_xformers_wheel("2.7.1"))


# 模拟 JamePeng/llama-cpp-python releases
LLAMA_RELEASES = [
    {"tag_name": "v0.3.48-cu128-win-20260821", "assets": [
        {"name": "llama_cpp_python-0.3.48+cu128-cp312-cp312-win_amd64.whl",
         "browser_download_url": "u://llama/cu128-cp312"},
        {"name": "llama_cpp_python-0.3.48+cu128-cp310-cp310-win_amd64.whl",
         "browser_download_url": "u://llama/cu128-cp310"},
    ]},
    {"tag_name": "v0.3.47-cu126-win-20260810", "assets": [
        {"name": "llama_cpp_python-0.3.47+cu126-cp312-cp312-win_amd64.whl",
         "browser_download_url": "u://llama/cu126-cp312"},
    ]},
]


class LlamaCppMatchTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(km, "_http_json", return_value=LLAMA_RELEASES)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_match_cu128_cp312(self):
        url, name = km._match_llamacpp_wheel("cu128", "312")
        self.assertIn("0.3.48", name)
        self.assertEqual(url, "u://llama/cu128-cp312")

    def test_no_match(self):
        self.assertIsNone(km._match_llamacpp_wheel("cu130", "312"))


class PlanTests(unittest.TestCase):
    """wheel_install_plan：弹窗方案的预选下标与列表内容。"""

    class _Inst:
        def __init__(self):
            self.path = os.getcwd()

        def resolve_python(self, fallback):
            return "python.exe"

    def test_xformers_plan_preselect(self):
        def fake(url, timeout=30):
            if url.endswith("xformers/json"):
                return PYPI_IDX
            v = url.split("/pypi/xformers/")[1].split("/json")[0]
            if v in PYPI_DATA:
                return PYPI_DATA[v]
            return {"info": {"requires_dist": []}, "urls": []}

        with mock.patch.object(km, "_http_json", side_effect=fake), \
                mock.patch.object(km, "_installed_torch",
                                  return_value=("2.8.0", "cu128")), \
                mock.patch.object(km, "_run", return_value=(0, "312", "")):
            plan = km.wheel_install_plan(self._Inst(), "xformers")
        self.assertEqual(plan["torch"], "2.8.0")
        self.assertEqual(plan["cu"], "cu128")
        self.assertEqual(plan["matched"], 0)
        self.assertIn("0.0.32.post2", plan["items"][0][0])
        self.assertEqual(plan["items"][0][1],
                         "u://pypi/xformers-0.0.32.post2.whl")

    def test_sageattention_plan_no_match_still_lists(self):
        """未匹配到（torch 2.5.0）也要列出全部候选，matched=None 供手动选择。"""
        with mock.patch.object(km, "_http_json",
                               return_value=SAGE_RELEASES), \
                mock.patch.object(km, "_installed_torch",
                                  return_value=("2.5.0", "cu128")), \
                mock.patch.object(km, "_run", return_value=(0, "312", "")):
            plan = km.wheel_install_plan(self._Inst(), "sageattention")
        self.assertIsNone(plan["matched"])
        self.assertGreater(len(plan["items"]), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
