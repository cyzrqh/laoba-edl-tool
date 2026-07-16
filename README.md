# 老八 EDL 刷机工具

Windows 10/11 Qualcomm EDL 图形刷机工具。新版界面使用 **Avalonia 12.1**，核心仍基于 [`bkerler/edl`](https://github.com/bkerler/edl)，并内置用户提供的高通引导资源包。

## 新版界面

- 1280 × 760 紧凑窗口，不再保留左侧功能导航。
- 左侧改为空白日志区；程序启动后不显示宣传、版本或资源包说明文字。
- 顶部直接提供 **内置引导** 下拉框，不再显示“选择设备/引导/配置”。
- 下拉框从资源包 `Config.xml` 读取所有引导，显示“引导文件名 · 品牌 / 系列 / 机型”。
- 保留端口、XML、搜索分区、中央分区表和右侧刷写操作区。
- 删除右下角版本号与“检查更新”。

## 功能

- 检测 Qualcomm HS-USB/QDLoader 9008 设备。
- 读取 GPT、读取分区、写入分区、擦除分区和设备重启。
- 整机分区备份、目录批量刷写、QFIL `rawprogram.xml + patch.xml` 刷写。
- 写入和擦除均有确认；不包含厂商认证绕过。

## 单文件 EXE

最终程序由 Avalonia 自包含单文件 EXE 和内嵌的 EDL 后端组成。Python 后端、高通资源包和运行依赖都封装在同一个 Windows EXE 中，最终用户无需安装 Python、Git 或 .NET。

GitHub Actions 同时构建：

- `老八-Windows-x64.exe`：绝大多数 Windows 10/11 电脑使用。
- `老八-Windows-x86.exe`：32 位 Windows 使用。
- 对应 GPL 源码压缩包。

本地构建需要 Git、.NET 8 SDK 和对应架构的 Python 3.9：

```powershell
.\build\build_avalonia.ps1 -Architecture x64
```

## Windows 驱动

应用可以直接打开；实际连接 9008 设备时，Windows 仍需合适的 Qualcomm/WinUSB 驱动。驱动兼容性取决于设备、USB 控制器、Windows 安全策略和签名状态。

## 授权机型

资源配置中标记为 Xiaomi、ZTE 等授权方案的引导，仍需合法厂商账号或维修授权。本工具不会绕过厂商认证。

## 许可证

项目代码按 GPLv3 发布。上游 `bkerler/edl` 的 README 对商业产品另有许可声明，商业分发前应联系上游作者确认。
