# ComfyUIBM启动器

一个基于 **Python + PyQt5** 的 ComfyUI 桌面启动器：实例绑定、启动控制台、模型（模组）管理、版本更新与回滚、插件管理、网络加速。

> 术语说明：**模组 = 模型**（checkpoints / LoRA / VAE 等），**插件 = 自定义节点**（custom_nodes 下的扩展）。

---

## ⬇️ 下载软件（请勿点右上角 Download ZIP）

> 仓库页面的 **Download ZIP** 下载的是源码压缩包（只有 README），**不是软件**。
> 软件安装包在下方 **Releases** 页面里：

### 👉 [前往 Releases 下载](https://github.com/PixelForgeLablbm-tech/ComfyUIBM_Launcher/releases)

| 文件 | 说明 | 适用人群 |
| --- | --- | --- |
| `ComfyUIBM_Launcher_Setup.exe` | **安装版**（推荐）：选择安装路径 + 桌面快捷方式，内置卸载器 | 一般用户 |
| `ComfyUIBM_Launcher.exe` | **单文件免安装版**：双击即用，可放在任意位置 | 便携 / 免安装用户 |

下载后如遇 **"Windows 已保护你的电脑"** 弹窗：点 **更多信息 → 仍要运行** 即可
（程序未做数字签名，属正常提示，非病毒）。

启动器内自带「检查更新」（设置页 / 左下角版本徽章点击），有新版本可一键自动更新。

---

## 功能

| 模块 | 说明 |
| --- | --- |
| 启动控制台 | 显存模式（自动/低显存/标准/高显存/无限制/纯CPU）、端口（启动前占用检测）、GPU 设备选择（nvidia-smi 自动探测）、Force FP16、--listen、注意力实现、额外启动参数、**就绪后自动打开浏览器**、**异常退出自动重启**、**启动参数版本适配**（自动探测 `main.py --help` 过滤不支持的参数）、实时日志（去 ANSI、按回车拆分）、运行时长显示 |
| 实例管理 | **自动扫描本机 ComfyUI 安装**（盘符根目录 / 已配置实例父目录 / 用户目录，含子目录）；一键添加；自动探测 Python（python_embeded / python / venv / .venv / 秋叶整合包父目录）；版本（git 标签）显示；设为当前实例 |
| 模型管理 | 27 个分类（含 VAE 近似、AnimateDiff、InsightFace、Diffusers 等）；分类显示数量与总大小；搜索、排序（大小/名称/时间）、分页（100/页）；导入（复制，**同名自动加后缀 _1 _2 不覆盖**）；打开所在目录、删除 |
| 插件管理 | 扫描 custom_nodes（区分 git / 本地文件夹）；**本地改动(dirty)检测**、**有依赖文件提示**（requirements.txt / install.py）；克隆安装（浅克隆）、更新（**本地改动自动 stash 保护**）、安装依赖（requirements.txt 或 install.py）、启用/禁用（.disabled）、删除 |
| 更新维护 | **发布版（Tags）与主干分支（master/main）版本列表**、每个版本的发布日期、当前/最新标记；**更新或回滚到指定版本**（自动暂存本地改动，`git checkout` + `reset --hard`）；**requirements 智能对比**（目标版本与当前版本依赖无变化则跳过安装）；一键更新到最新版；安装 requirements（带 PyPI 镜像） |
| 网络加速 | PyPI 镜像（阿里云/清华/腾讯/官方）、HuggingFace 镜像（HF_ENDPOINT）、代理开关与地址、**GitHub 加速**（`-c url.<前缀>https://github.com/.insteadOf` 注入，不改全局 git 配置，含 gh-proxy.com 等预设前缀） |
| 系统状态条 | 顶栏实时显示：端口监听状态、GPU（名称/显存/利用率/温度）、内存使用率、当前实例；进程运行中 2 秒轮询，空闲 8 秒 |
| 其他 | 深色/浅色主题、侧边栏导航、关闭最小化到托盘、窗口大小位置记忆、运行日志面板 |

## 环境要求

- Windows（GPU 状态需要 nvidia-smi）
- 使用「更新维护 / 插件更新」功能需安装 [git](https://git-scm.com/) 并加入 PATH

## 使用说明

### 1. 启动控制台
- 选择当前实例（未配置时先去「实例管理」添加）。
- 设置显存模式、端口、GPU 设备、各开关与额外参数，点击 **▶ 启动 ComfyUI**。
- 右侧实时日志显示运行输出；日志出现 `To see the GUI go to` 或端口可连通时视为就绪，自动打开浏览器（可在选项关闭）；进程异常退出会自动重启（可关闭）。
- 点击 **■ 停止** 通过 `taskkill /T /F` 结束整个进程树。

### 2. 实例管理
- **扫描本机**：自动发现所有 ComfyUI 安装（含子目录布局），一键「添加」或「设为当前」。
- 手动添加：选择目录即可（自动校验 main.py、自动识别便携版 Python）。
- 支持远程实例（HTTP 地址）：仅用于在线检测与浏览器打开，不能本机启动。

### 3. 模型管理
- 左侧分类（含数量与总大小统计），右侧文件列表支持搜索/排序/分页。
- **导入模型**：选择文件 → 复制到当前分类（同名自动改名，不覆盖原文件）。

### 4. 插件管理
- 顶部输入 git 地址「克隆安装」，或选择本地插件文件夹复制。
- 「更新」会自动暂存本地改动，更新成功后恢复；「装依赖」处理 requirements.txt 或 install.py。

### 5. 更新维护
- 「刷新版本列表」拉取远端 Tags 与分支，显示发布日期与当前/最新标记。
- 选择任意版本「更新到所选版本」即可升级或回滚（自动对比依赖，有变化才安装）。
- 「一键更新到最新版」切换到最新发布版。
- 下方可开关 **GitHub 加速** 并选择/自定义加速前缀。

### 6. 设置
- 默认 Python、启动时检查更新、关闭最小化到托盘。
- PyPI 镜像 / HF 镜像 / 代理（仅对本启动器发起的 git/pip 命令生效）。

## 配置

配置保存在 `%APPDATA%\ComfyUILauncher\config.json`，包含实例列表、当前实例、启动参数与镜像/代理设置。卸载/更新**不会删除**该配置及你的 ComfyUI 模型/插件。

## 开发与打包（仅开发者）

```bash
pip install -r requirements.txt
python main.py                 # 运行源码版
```

打包发布流程：`launcher/__init__.py` 改版本号 → 依次构建 onedir 主程序、`ComfyUIBM_Launcher_Setup.spec`（安装包）、`ComfyUIBM_Launcher.spec`（单文件版）→ `tools/release.py` 发布 Release → `tools/upload_asset.py` 上传单文件版。

## 测试

```bash
python tests/logic_test.py    # 核心逻辑端到端（含真实 git 仓库：版本列表/更新回滚/插件/模型）
python tests/smoke_test.py    # GUI 冒烟：页面 + 对话框 + 进程启动/停止端到端（离屏）
```

## 注意事项

- 版本更新/回滚依赖 git 仓库安装；zip 下载的非 git 安装无法在线更新。
- 更新前会自动暂存本地改动并恢复；若恢复冲突会保留 stash 记录，可手动 `git stash pop`。
- 启动器关闭不会终止已启动的 ComfyUI 进程（停止需点「停止」按钮）。
- GPU 状态依赖 nvidia-smi；无 NVIDIA 显卡时状态条自动隐藏 GPU 项。
