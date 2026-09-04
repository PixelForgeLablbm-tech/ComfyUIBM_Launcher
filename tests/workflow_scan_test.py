# -*- coding: utf-8 -*-
"""工作流识别功能自测：解析格式 + 已装/未装分类（用真实节点映射表）。"""
import json
import os
import shutil
import sys
import tempfile

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from launcher import workflow_scan as ws

tmp = tempfile.mkdtemp(prefix="wf_test_")
ok = True


def check(label, cond):
    global ok
    print(("PASS " if cond else "FAIL ") + label)
    ok = ok and cond


# 1) 两种格式的工作流
ui_wf = {"nodes": [
    {"type": "KSampler"}, {"type": "CLIPTextEncode"},
    {"type": "ImageGetMetadata"}, {"type": "SimplePrompt"},
], "links": []}
api_wf = {"1": {"class_type": "KSampler", "inputs": {}},
          "2": {"class_type": "ImageGetMetadata", "inputs": {}}}
f1 = os.path.join(tmp, "ui.json")
f2 = os.path.join(tmp, "api.json")
json.dump(ui_wf, open(f1, "w"))
json.dump(api_wf, open(f2, "w"))

nodes1 = ws.parse_workflow(f1)
check("UI 格式解析", nodes1 == ["KSampler", "CLIPTextEncode",
                                "ImageGetMetadata", "SimplePrompt"])
nodes2 = ws.parse_workflow(f2)
check("API 格式解析", set(nodes2) == {"KSampler", "ImageGetMetadata"})

# 2) 映射表加载
idx = ws._indexes()
check("节点映射表加载", "ImageGetMetadata" in idx["node2repo"]
      and "ComfyUI-Metadata-Tools" in idx["node2repo"]["ImageGetMetadata"])

# 3) 假实例：已装 ComfyUI-Metadata-Tools
inst = os.path.join(tmp, "ComfyUI")
cn = os.path.join(inst, "custom_nodes", "ComfyUI-Metadata-Tools")
os.makedirs(cn)
open(os.path.join(cn, "__init__.py"), "w", encoding="utf-8").write(
    "NODE_CLASS_MAPPINGS = {'ImageGetMetadata': 1}\n")

res = ws.analyze_workflow(inst, f1)
print("已安装:", res["installed"])
print("未安装:", res["missing"])
print("未识别:", res["unmapped"])
check("ImageGetMetadata 判为已安装",
      any("Metadata-Tools" in x["name"] for x in res["installed"]))
check("SimplePrompt 判为未安装",
      any(x["name"] == "ComfyUI-Simple-Prompt" for x in res["missing"]))
check("内置节点归入未识别", "KSampler" in res["unmapped"])

# 4) 名字复制
check("仓库短名", ws.repo_short_name(
    "https://github.com/0nikod/ComfyUI-Simple-Prompt.git")
      == "ComfyUI-Simple-Prompt")

shutil.rmtree(tmp, ignore_errors=True)
print("RESULT:", "ALL PASS" if ok else "HAS FAILURES")
sys.exit(0 if ok else 1)
