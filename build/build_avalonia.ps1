param(
    [ValidateSet("x64", "x86")]
    [string]$Architecture = "x64",
    [string]$EdlRef = "51e11022455d26bcf0b8305b930c474e9b3c81ad"
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $true
}
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$Utf8 = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = $Utf8
[Console]::OutputEncoding = $Utf8
$OutputEncoding = $Utf8
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

function Assert-NativeSuccess([string]$Description) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Description 失败，退出代码：$LASTEXITCODE"
    }
}

foreach ($Command in @("git", "python", "dotnet")) {
    if (-not (Get-Command $Command -ErrorAction SilentlyContinue)) {
        throw "缺少构建命令：$Command"
    }
}

& python (Join-Path $Root "tools\assemble_resource.py")
Assert-NativeSuccess "重组内置资源包"

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

$Venv = Join-Path $Root ".venv-avalonia-$Architecture"
if (-not (Test-Path $Venv)) {
    & python -m venv $Venv
    Assert-NativeSuccess "创建 Python 虚拟环境"
}
$Py = Join-Path $Venv "Scripts\python.exe"

& $Py -m pip install --upgrade pip wheel setuptools
Assert-NativeSuccess "更新 Python 构建工具"
& $Py -m pip install "pyinstaller==6.11.1" "py7zr>=0.21"
Assert-NativeSuccess "安装后端打包依赖"
if ($Architecture -eq "x86") {
    & $Py -m pip install "capstone==5.0.2" "cryptography==43.0.3"
    Assert-NativeSuccess "安装 32 位兼容依赖"
}
& $Py -m pip install -r (Join-Path $Vendor "requirements.txt")
Assert-NativeSuccess "安装 EDL 运行依赖"

$LibusbArchive = Get-ChildItem (Join-Path $Vendor "Drivers\Windows") -Filter "libusb-*-binaries.7z" |
    Sort-Object Name -Descending |
    Select-Object -First 1
if (-not $LibusbArchive) { throw "上游 Drivers/Windows 中没有 libusb 二进制压缩包。" }
$LibusbOutput = Join-Path $Root "build\runtime-dll-$Architecture\libusb-1.0.dll"
& $Py (Join-Path $Root "build\prepare_libusb.py") `
    --archive $LibusbArchive.FullName `
    --architecture $Architecture `
    --output $LibusbOutput
Assert-NativeSuccess "准备 libusb-1.0.dll"

$BackendDist = Join-Path $Root "build\backend-dist-$Architecture"
$BackendWork = Join-Path $Root "build\backend-work-$Architecture"
foreach ($Path in @($BackendDist, $BackendWork)) {
    if (Test-Path $Path) { Remove-Item $Path -Recurse -Force }
}
& $Py -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --optimize 2 `
    --exclude-module tkinter `
    --exclude-module unittest `
    --exclude-module pydoc `
    --exclude-module doctest `
    --name laoba-backend `
    --distpath $BackendDist `
    --workpath $BackendWork `
    --paths $Vendor `
    --collect-all edlclient `
    --add-binary "$LibusbOutput;." `
    (Join-Path $Root "backend_cli.py")
Assert-NativeSuccess "构建内置 EDL 后端"

$BackendExe = Join-Path $BackendDist "laoba-backend.exe"
if (-not (Test-Path $BackendExe)) { throw "未生成内置 EDL 后端：$BackendExe" }

$Rid = if ($Architecture -eq "x64") { "win-x64" } else { "win-x86" }
$PublishDir = Join-Path $Root "build\avalonia-publish-$Architecture"
if (Test-Path $PublishDir) { Remove-Item $PublishDir -Recurse -Force }

& dotnet publish (Join-Path $Root "avalonia\Laoba.App\Laoba.App.csproj") `
    -c Release `
    -r $Rid `
    --self-contained true `
    -o $PublishDir `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -p:EnableCompressionInSingleFile=true `
    "-p:BackendExePath=$BackendExe"
Assert-NativeSuccess "发布 Avalonia 单文件程序"

$BuiltExe = Join-Path $PublishDir "Laoba.App.exe"
if (-not (Test-Path $BuiltExe)) { throw "Avalonia 未生成预期 EXE：$BuiltExe" }

$OutDir = Join-Path $Root "release"
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$ReleaseExe = Join-Path $OutDir "老八-Windows-$Architecture.exe"
Copy-Item $BuiltExe $ReleaseExe -Force

$SourceStage = Join-Path $env:TEMP ("laoba-avalonia-source-" + $PID)
if (Test-Path $SourceStage) { Remove-Item $SourceStage -Recurse -Force }
New-Item -ItemType Directory -Path $SourceStage | Out-Null
$SourceItems = @(
    "avalonia",
    "backend_cli.py",
    "laoba",
    "assets",
    "tools",
    "tests",
    ".github",
    "build\build_avalonia.ps1",
    "build\prepare_libusb.py",
    "README.md",
    "SECURITY.md",
    "THIRD_PARTY_NOTICES.md",
    "LICENSE",
    ".gitignore"
)
foreach ($Relative in $SourceItems) {
    $Source = Join-Path $Root $Relative
    if (-not (Test-Path $Source)) { continue }
    $Destination = Join-Path $SourceStage $Relative
    $Parent = Split-Path -Parent $Destination
    if ($Parent) { New-Item -ItemType Directory -Path $Parent -Force | Out-Null }
    Copy-Item $Source $Destination -Recurse -Force
}
$SourceZip = Join-Path $OutDir "老八-对应源码-$Architecture.zip"
if (Test-Path $SourceZip) { Remove-Item $SourceZip -Force }
Compress-Archive -Path (Join-Path $SourceStage "*") -DestinationPath $SourceZip -CompressionLevel Optimal
Remove-Item $SourceStage -Recurse -Force

Write-Host "构建完成：" -ForegroundColor Green
Write-Host "  $ReleaseExe"
Write-Host "  文件大小: $([math]::Round((Get-Item $ReleaseExe).Length / 1MB, 2)) MiB"
Write-Host "  SHA-256: $((Get-FileHash $ReleaseExe -Algorithm SHA256).Hash.ToLower())"
Write-Host "  $SourceZip"