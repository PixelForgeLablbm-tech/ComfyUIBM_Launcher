# -*- coding: utf-8 -*-
"""配置读写：实例列表、当前实例、启动参数、镜像/代理设置，JSON 持久化。"""
import json
import os
from pathlib import Path

APP_NAME = "ComfyUILauncher"


def dpi_scale_factor(dpi_setting: str, system_dpi: int = 96):
    """把"期望的最终界面缩放"换算成 QT_SCALE_FACTOR 环境变量值。

    QT_SCALE_FACTOR 是**乘数**：实际缩放 = 系统缩放 × QT_SCALE_FACTOR。
    所以要让最终缩放等于用户选择的值，必须除以系统缩放反算。
    返回字符串（如 "0.8333"）；auto/off/非法值返回 None（不设置）。
    """
    s = str(dpi_setting or "").strip().lower()
    if s in ("", "auto", "off"):
        return None
    try:
        desired = float(s)
    except ValueError:
        return None
    system_scale = max(int(system_dpi) or 96, 96) / 96.0
    if desired <= 0 or system_scale <= 0:
        return None
    return f"{desired / system_scale:.4f}"


def default_config_dir() -> Path:
    """配置文件目录：Windows 用 %APPDATA%，否则用用户主目录。"""
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / ("." + APP_NAME.lower())


DEFAULT_LAUNCH = {
    "mode": "normalvram",           # 标准：默认行为，不传参（兼容所有版本）
    "port": 8188,
    "listen": False,                # --listen
    "auto_launch_browser": True,    # 就绪后自动打开浏览器
    "force_fp16": False,
    "attention": "auto",            # auto|split|pytorch
    "cuda_device": None,            # int 或 None
    "extra_args": [],               # 全局额外启动参数
    "auto_restart": False,          # 异常退出自动重启
}

DEFAULT_MIRRORS = {
    "pypi_mirror": "aliyun",        # aliyun|tsinghua|tencent|official
    "hf_mirror": False,             # HF_ENDPOINT=https://hf-mirror.com
    "use_proxy": False,             # 代理总开关（各人机器自行配置，不固化）
    "proxy": "",                    # 代理地址（机器特有，不固化）
    "gh_proxy": True,               # GitHub 加速开关
    "gh_proxy_prefix": "https://gh-proxy.com/",
}

DEFAULT_SETTINGS = {
    "python_path": "python",        # 默认 Python（实例未指定时使用）
    "default_launch_args": "",      # 兼容旧版：默认启动参数文本
    "theme": "dark",                # 界面主题：dark|light|system
    "dpi_scaling": "auto",          # DPI 缩放：auto|off|1.0|1.25|1.5|2.0
    "launch": dict(DEFAULT_LAUNCH),
    "mirrors": dict(DEFAULT_MIRRORS),
}


class Config:
    """负责加载与保存 launcher 配置。"""

    def __init__(self, path=None):
        self.path = Path(path) if path else default_config_dir() / "config.json"
        self.settings = {}
        self.instances = []          # list[dict]
        self.current_instance_id = None
        self.load()

    # ---------- 便捷访问 ----------
    @property
    def launch(self) -> dict:
        return self.settings.setdefault("launch", dict(DEFAULT_LAUNCH))

    @property
    def mirrors(self) -> dict:
        return self.settings.setdefault("mirrors", dict(DEFAULT_MIRRORS))

    # ---------- 读写 ----------
    def load(self):
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                self.settings = data.get("settings", {})
                self.instances = data.get("instances", [])
                self.current_instance_id = data.get("current_instance_id")
        except Exception:
            # 配置文件损坏时回退到默认值，避免启动崩溃
            self.settings = {}
            self.instances = []
            self.current_instance_id = None
        self.normalize()

    def normalize(self):
        """兼容旧配置 / 空值修复。"""
        s = self.settings
        for k, v in DEFAULT_SETTINGS.items():
            s.setdefault(k, dict(v) if isinstance(v, dict) else v)
        launch = s["launch"]
        for k, v in DEFAULT_LAUNCH.items():
            if k not in launch:
                launch[k] = v
        # 旧版默认启动参数并入额外参数
        legacy = s.get("default_launch_args", "").strip()
        if legacy and legacy != "--auto-launch":
            extra = [t for t in launch["extra_args"] if t.strip()]
            for t in legacy.split():
                if t not in extra:
                    extra.append(t)
            launch["extra_args"] = extra
        s["default_launch_args"] = ""
        if launch["port"] <= 0 or launch["port"] > 65535:
            launch["port"] = 8188
        mirrors = s["mirrors"]
        for k, v in DEFAULT_MIRRORS.items():
            if k not in mirrors:
                mirrors[k] = v

    def save(self) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "settings": self.settings,
                "instances": self.instances,
                "current_instance_id": self.current_instance_id,
            }
            tmp = self.path.with_name(self.path.name + ".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                           encoding="utf-8")
            tmp.replace(self.path)      # 原子替换
            return True
        except Exception:
            return False
