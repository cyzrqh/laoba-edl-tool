# 老八刷机工具

Windows 10/11 的 Qualcomm EDL 图形刷机工具，应用名称为 **“老八”**，图标使用用户提供的图片。核心基于 [`bkerler/edl`](https://github.com/bkerler/edl)，并原样内置用户提供的高通资源包。程序读取其中 `Config.xml`，按品牌、系列和机型选择对应引导文件。

## 已实现

- 参考专业刷机工具重做的现代界面：左侧导航、顶部设备与端口区、中央分区表、右侧基础操作和底部折叠日志。
- 品牌 / 系列 / 机型三级选择，自动读取 UFS、eMMC、授权标记和引导路径。
- 检测 Qualcomm HS-USB/QDLoader 9008 设备。
- 读取 GPT、读取分区、写入分区、擦除分区、恢复出厂设置和设备重启。
- 整机分区备份、目录批量刷写、QFIL `rawprogram.xml + patch.xml` 刷写。
- 写入和擦除均有明确确认；不包含认证绕过功能。
- PyInstaller **单文件 EXE**：Python、EDL 核心、图标、驱动和资源包全部封装在一个程序中。
- x64 和 x86 自动构建；Windows 11 ARM 可尝试使用系统的 x64 应用模拟，但未承诺所有 ARM 设备、驱动和硬件组合都兼容。

## 构建 Windows 单文件版

### GitHub Actions

仓库保存的是资源包分片；构建脚本会先重组并校验资源包，再将其内置到最终程序。打开 **Actions → 构建老八 Windows 单文件版 → Run workflow**。完成后下载：

- `老八-Windows-x64.exe`：绝大多数 64 位 Windows 10/11 使用。
- `老八-Windows-x86.exe`：仅供 32 位 Windows 使用。
- 对应源码压缩包。

最终用户只需运行一个 EXE，不需要安装 Python、Git，也不需要保留 `_internal` 文件夹。

### 本地构建

构建机安装 Git 和对应架构的 Python 3.9，然后运行：

```powershell
.\build\build_windows.ps1 -Architecture x64
```

输出位于 `release`。

## Windows 驱动说明

应用本身可以直接打开；实际通过 USB 操作 9008 设备时，Windows 必须有合适的 Qualcomm/WinUSB 驱动。完整构建会把上游 `Drivers/Windows` 封装进 EXE，应用中的“安装/修复内置驱动”会在需要时单独请求管理员权限。驱动兼容性取决于设备、USB 控制器、Windows 安全策略和签名状态，因此无法保证每一台 Windows 10/11 电脑都无需驱动处理。

## 授权机型

资源配置里部分机型标记为 `Xiaomi` 或 `ZTE` 授权。本工具只选择和传递引导文件，**不绕过厂商认证**。这类机型必须使用合法厂商账号、维修授权或设备允许的官方流程。

## 许可证

本项目代码按 GPLv3 发布。由于上游 `bkerler/edl` 的 README 另有“商业产品需事先许可”的声明，本项目默认按非商业工具处理；商业分发前应联系上游作者确认许可。分发编译版时必须同时提供对应源码和许可证文件。

## 上游版本固定

默认构建固定到 `bkerler/edl` 提交 `51e11022455d26bcf0b8305b930c474e9b3c81ad`，以保证可复现。
