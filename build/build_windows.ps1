param(
    [ValidateSet("x64", "x86")]
    [string]$Architecture = "x64",
    [string]$EdlRef = "51e11022455d26bcf0b8305b930c474e9b3c81ad",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function Require-Command([string]$Name) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "缺少构建命令：$Name。构建机需要 Git 和 Python 3.9；最终应用运行时不需要。"
    }
}

function Assert-NativeSuccess([string]$Description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Description 失败，退出代码：$LASTEXITCODE"
    }
}

Require-Command git
Require-Command python

& python (Join-Path $Root "tools\assemble_resource.py")
Assert-NativeSuccess "重组内置资源包"

$Version = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Assert-NativeSuccess "读取 Python 版本"
if ($Version -ne "3.9") {
    Write-Warning "上游官方 Windows 说明使用 Python 3.9；当前为 Python $Version。"
}

$Vendor = Join-Path $Root "vendor\edl"
if (-not (Test-Path (Join-Path $Vendor ".git"))) {
    if (Test-Path $Vendor) { Remove-Item $Vendor -Recurse -Force }
    & git clone --filter=blob:none https://github.com/bkerler/edl.git $Vendor
    Assert-NativeSuccess "克隆 bkerler/edl"
}
& git -C $Vendor fetch --depth 1 origin $EdlRef
Assert-NativeSuccess "获取 bkerler/edl 指定版本"
& git -C $Vendor checkout --force FETCH_HEAD
Assert-NativeSuccess "检出 bkerler/edl 指定版本"
# Loaders 子模块不参与本工具的机型选择；使用用户提供的内置资源包。

$Venv = Join-Path $Root ".venv-$Architecture"
if (-not (Test-Path $Venv)) {
    & python -m venv $Venv
    Assert-NativeSuccess "创建 $Architecture Python 虚拟环境"
}
$Py = Join-Path $Venv "Scripts\python.exe"
if (-not (Test-Path $Py)) { throw "虚拟环境中找不到 Python：$Py" }

& $Py -m pip install --upgrade pip wheel setuptools
Assert-NativeSuccess "更新 pip/wheel/setuptools"
& $Py -m pip install -r (Join-Path $Root "requirements-build.txt")
Assert-NativeSuccess "安装本项目构建依赖"
& $Py -m pip install -r (Join-Path $Vendor "requirements.txt")
Assert-NativeSuccess "安装 bkerler/edl 运行依赖"

$LibusbArchive = Get-ChildItem (Join-Path $Vendor "Drivers\Windows") -Filter "libusb-*-binaries.7z" |
    Sort-Object Name -Descending |
    Select-Object -First 1
if (-not $LibusbArchive) { throw "上游 Drivers/Windows 中没有 libusb 二进制压缩包。" }
$LibusbOutput = Join-Path $Root "build\runtime-dll-$Architecture\libusb-1.0.dll"
& $Py (Join-Path $Root "build\prepare_libusb.py") `
    --archive $LibusbArchive.FullName `
    --architecture $Architecture `
    --output $LibusbOutput
Assert-NativeSuccess "准备 $Architecture libusb-1.0.dll"

if (-not $SkipTests) {
    & $Py -m pytest -q
    Assert-NativeSuccess "运行自动测试"
}

$Dist = Join-Path $Root "dist"
$BuildDir = Join-Path $Root "build\pyinstaller-$Architecture"
if (Test-Path $Dist) { Remove-Item $Dist -Recurse -Force }
if (Test-Path $BuildDir) { Remove-Item $BuildDir -Recurse -Force }

$env:LAOBA_ARCH = $Architecture
& $Py -m PyInstaller `
    --noconfirm `
    --clean `
    --distpath $Dist `
    --workpath $BuildDir `
    (Join-Path $Root "build\laoba.spec")
Assert-NativeSuccess "运行 PyInstaller"

$AppDist = Join-Path $Dist "老八"
if (-not (Test-Path $AppDist)) {
    throw "PyInstaller 未生成预期目录：$AppDist"
}

$Commit = & git -C $Vendor rev-parse HEAD
Assert-NativeSuccess "读取 bkerler/edl 提交号"
$Commit = $Commit.Trim()
$Info = @"
老八刷机工具 1.0.0
目标架构：$Architecture
EDL 上游提交：$Commit
构建时间：$([DateTime]::UtcNow.ToString("u")) UTC
资源包 SHA-256：$((Get-FileHash (Join-Path $Root "assets\qualcomm_resource_pack.zip") -Algorithm SHA256).Hash.ToLower())
"@
$Info | Out-File -FilePath (Join-Path $AppDist "BUILD-INFO.txt") -Encoding utf8
Copy-Item (Join-Path $Root "README.md") (Join-Path $AppDist "README.md")

$OutDir = Join-Path $Root "release"
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$PortableZip = Join-Path $OutDir "老八-Windows-$Architecture-portable.zip"
if (Test-Path $PortableZip) { Remove-Item $PortableZip -Force }
Compress-Archive -Path (Join-Path $AppDist "*") -DestinationPath $PortableZip -CompressionLevel Optimal

$SourceStage = Join-Path $env:TEMP ("laoba-source-stage-" + $PID)
if (Test-Path $SourceStage) { Remove-Item $SourceStage -Recurse -Force }
New-Item -ItemType Directory -Path $SourceStage | Out-Null

$SourceItems = @(
    "app.py",
    "laoba",
    "assets",
    "tools",
    ".github",
    "tests",
    "vendor",
    "build\laoba.spec",
    "build\build_windows.ps1",
    "build\build_windows.bat",
    "build\version_info.txt",
    "build\prepare_libusb.py",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "LICENSE",
    "requirements-build.txt",
    ".gitignore"
)
foreach ($Relative in $SourceItems) {
    $Source = Join-Path $Root $Relative
    if (-not (Test-Path $Source)) { continue }
    $Destination = Join-Path $SourceStage $Relative
    $DestinationParent = Split-Path -Parent $Destination
    if ($DestinationParent) { New-Item -ItemType Directory -Path $DestinationParent -Force | Out-Null }
    Copy-Item $Source $Destination -Recurse -Force
}
Get-ChildItem $SourceStage -Directory -Recurse -Force |
    Where-Object { $_.Name -in @("__pycache__", ".pytest_cache", ".git") } |
    Sort-Object { $_.FullName.Length } -Descending |
    Remove-Item -Recurse -Force
$SourceZip = Join-Path $OutDir "老八-对应源码-$Architecture.zip"
if (Test-Path $SourceZip) { Remove-Item $SourceZip -Force }
Compress-Archive -Path (Join-Path $SourceStage "*") -DestinationPath $SourceZip -CompressionLevel Optimal
Remove-Item $SourceStage -Recurse -Force

Write-Host "构建完成：" -ForegroundColor Green
Write-Host "  $PortableZip"
Write-Host "  $SourceZip"
