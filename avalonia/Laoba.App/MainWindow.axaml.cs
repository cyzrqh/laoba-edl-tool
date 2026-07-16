using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using Avalonia.Controls;
using Avalonia.Controls.Shapes;
using Avalonia.Input;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;

namespace Laoba.App;

public sealed partial class MainWindow : Window
{
    private const uint MbOk = 0x00000000;
    private const uint MbOkCancel = 0x00000001;
    private const uint MbIconWarning = 0x00000030;
    private const uint MbIconError = 0x00000010;
    private const int IdOk = 1;

    private static readonly IBrush ConnectedBrush = new SolidColorBrush(Color.Parse("#18B566"));
    private static readonly IBrush DisconnectedBrush = new SolidColorBrush(Color.Parse("#AAB2BD"));
    private static readonly IBrush WaitingBrush = new SolidColorBrush(Color.Parse("#F2A100"));

    private readonly ResourceCatalog _catalog = new();
    private readonly BackendRunner _backend = new();
    private readonly CancellationTokenSource _closing = new();
    private readonly SemaphoreSlim _operationLock = new(1, 1);
    private readonly SemaphoreSlim _deviceRefreshLock = new(1, 1);

    private readonly ComboBox _loaderComboBox;
    private readonly TextBox _xmlPathTextBox;
    private readonly TextBox _partitionSearchTextBox;
    private readonly TextBox _logTextBox;
    private readonly ListBox _partitionListBox;
    private readonly StackPanel _emptyPartitionPanel;
    private readonly TextBlock _statusTextBlock;
    private readonly Ellipse _statusDot;
    private readonly ProgressBar _busyProgressBar;

    private bool _operationActive;
    private string _lastDeviceStatus = "未检测到9008设备";

    public MainWindow()
    {
        AvaloniaXamlLoader.Load(this);

        _loaderComboBox = this.FindControl<ComboBox>("LoaderComboBox")!;
        _xmlPathTextBox = this.FindControl<TextBox>("XmlPathTextBox")!;
        _partitionSearchTextBox = this.FindControl<TextBox>("PartitionSearchTextBox")!;
        _logTextBox = this.FindControl<TextBox>("LogTextBox")!;
        _partitionListBox = this.FindControl<ListBox>("PartitionListBox")!;
        _emptyPartitionPanel = this.FindControl<StackPanel>("EmptyPartitionPanel")!;
        _statusTextBlock = this.FindControl<TextBlock>("StatusTextBlock")!;
        _statusDot = this.FindControl<Ellipse>("StatusDot")!;
        _busyProgressBar = this.FindControl<ProgressBar>("BusyProgressBar")!;

        _logTextBox.Text = string.Empty;

        try
        {
            var profiles = _catalog.LoadProfiles();
            _loaderComboBox.ItemsSource = profiles;
            if (profiles.Count > 0)
            {
                _loaderComboBox.SelectedIndex = 0;
            }
        }
        catch (Exception exception)
        {
            SetStatus("内置引导加载失败", DeviceState.Disconnected);
            ShowError("资源包错误", exception.Message);
        }

        Closing += (_, _) => _closing.Cancel();
        _ = MonitorDeviceStatusAsync(_closing.Token);
    }

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    private static extern int MessageBoxW(IntPtr hWnd, string text, string caption, uint type);

    private static bool Confirm(string title, string message) =>
        MessageBoxW(IntPtr.Zero, message, title, MbOkCancel | MbIconWarning) == IdOk;

    private static void ShowError(string title, string message) =>
        MessageBoxW(IntPtr.Zero, message, title, MbOk | MbIconError);

    private async void BrowseXml_Click(object? sender, RoutedEventArgs e) => await BrowseXmlAsync();

    private async void BrowseXml_DoubleTapped(object? sender, TappedEventArgs e)
    {
        e.Handled = true;
        await BrowseXmlAsync();
    }

    private async Task BrowseXmlAsync()
    {
        var result = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "选择 rawprogram XML",
            AllowMultiple = false,
            FileTypeFilter =
            [
                new FilePickerFileType("XML 文件") { Patterns = ["*.xml"] },
                FilePickerFileTypes.All,
            ],
        });
        var path = result.FirstOrDefault()?.TryGetLocalPath();
        if (!string.IsNullOrWhiteSpace(path))
        {
            _xmlPathTextBox.Text = path;
            AppendLog($"[{DateTime.Now:HH:mm:ss}] 已选择 XML：{path}{Environment.NewLine}");
        }
    }

    private async void DetectDevice_Click(object? sender, RoutedEventArgs e)
    {
        SetBusy(true);
        SetStatus("正在检测9008设备…", DeviceState.Waiting);
        try
        {
            await RefreshDeviceStatusAsync(force: true, _closing.Token);
        }
        catch (OperationCanceledException)
        {
        }
        catch (Exception exception)
        {
            SetStatus("9008设备检测失败", DeviceState.Disconnected);
            ShowError("检测失败", exception.Message);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void ViewSlot_Click(object? sender, RoutedEventArgs e)
    {
        var captured = new StringBuilder();
        var exitCode = await RunEdlAsync(["getactiveslot"], "查看当前槽位", text => captured.Append(text));
        if (exitCode != 0)
        {
            return;
        }

        var match = Regex.Match(captured.ToString(), @"Current active slot:\s*([ab])", RegexOptions.IgnoreCase);
        if (match.Success)
        {
            var slot = match.Groups[1].Value.ToUpperInvariant();
            SetStatus($"{_lastDeviceStatus} · 当前槽位：{slot}", DeviceState.Connected);
            AppendLog($"[{DateTime.Now:HH:mm:ss}] 当前活动槽位：{slot}{Environment.NewLine}");
        }
        else
        {
            SetStatus($"{_lastDeviceStatus} · 未能识别当前槽位", DeviceState.Connected);
        }
    }

    private void ClearLog_Click(object? sender, RoutedEventArgs e) => _logTextBox.Text = string.Empty;

    private async void ExportLog_Click(object? sender, RoutedEventArgs e)
    {
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = "导出运行日志",
            SuggestedFileName = $"老八-运行日志-{DateTime.Now:yyyyMMdd-HHmmss}.txt",
            DefaultExtension = "txt",
            FileTypeChoices =
            [
                new FilePickerFileType("文本文件") { Patterns = ["*.txt"] },
                FilePickerFileTypes.All,
            ],
        });
        var path = file?.TryGetLocalPath();
        if (!string.IsNullOrWhiteSpace(path))
        {
            await File.WriteAllTextAsync(
                path,
                _logTextBox.Text ?? string.Empty,
                new UTF8Encoding(false),
                _closing.Token);
            AppendLog($"[{DateTime.Now:HH:mm:ss}] 日志已导出：{path}{Environment.NewLine}");
        }
    }

    private void OpenWorkDirectory_Click(object? sender, RoutedEventArgs e)
    {
        try
        {
            var directory = GetWorkDirectory();
            Process.Start(new ProcessStartInfo
            {
                FileName = directory,
                UseShellExecute = true,
            });
        }
        catch (Exception exception)
        {
            ShowError("无法打开目录", exception.Message);
        }
    }

    private async void FlashSelected_Click(object? sender, RoutedEventArgs e)
    {
        if (!string.IsNullOrWhiteSpace(_xmlPathTextBox.Text))
        {
            await RunXmlFlashAsync();
            return;
        }

        var partition = GetPartitionName();
        if (partition is null)
        {
            return;
        }

        var result = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = $"选择要写入 {partition} 的镜像",
            AllowMultiple = false,
            FileTypeFilter =
            [
                new FilePickerFileType("镜像文件") { Patterns = ["*.img", "*.bin"] },
                FilePickerFileTypes.All,
            ],
        });
        var image = result.FirstOrDefault()?.TryGetLocalPath();
        if (string.IsNullOrWhiteSpace(image))
        {
            return;
        }

        if (!Confirm("写入分区", $"即将把镜像写入分区“{partition}”。错误镜像可能导致设备无法启动。\n\n确定继续？"))
        {
            return;
        }

        await RunEdlAsync(["w", partition, image], $"写入 {partition}");
    }

    private async Task RunXmlFlashAsync()
    {
        var rawprogram = _xmlPathTextBox.Text?.Trim();
        if (string.IsNullOrWhiteSpace(rawprogram) || !File.Exists(rawprogram))
        {
            ShowError("缺少 XML", "请先选择有效的 rawprogram XML 文件。");
            return;
        }

        var directory = Path.GetDirectoryName(rawprogram)!;
        var patch = Directory.EnumerateFiles(directory, "patch*.xml", SearchOption.TopDirectoryOnly)
            .FirstOrDefault();
        if (patch is null)
        {
            ShowError("缺少 patch XML", "rawprogram XML 所在目录中没有找到 patch*.xml。");
            return;
        }

        if (!Confirm("XML 刷写", "将执行多分区 XML 刷写。请确认 XML、镜像目录和所选内置引导完全匹配设备。\n\n确定继续？"))
        {
            return;
        }

        await RunEdlAsync(["qfil", rawprogram, patch, directory], "XML 刷写");
    }

    private async void FlashFolder_Click(object? sender, RoutedEventArgs e)
    {
        var result = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = "选择镜像目录",
            AllowMultiple = false,
        });
        var folder = result.FirstOrDefault()?.TryGetLocalPath();
        if (string.IsNullOrWhiteSpace(folder))
        {
            return;
        }

        if (!Confirm("目录刷写", "将按目录内的分区镜像进行批量写入。请确认固件与设备完全匹配。\n\n确定继续？"))
        {
            return;
        }

        await RunEdlAsync(["wl", folder], "目录刷写");
    }

    private async void BackupAll_Click(object? sender, RoutedEventArgs e)
    {
        var result = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = "选择整机备份目录",
            AllowMultiple = false,
        });
        var folder = result.FirstOrDefault()?.TryGetLocalPath();
        if (!string.IsNullOrWhiteSpace(folder))
        {
            await RunEdlAsync(["rl", folder, "--skip=userdata", "--genxml"], "整机分区备份");
        }
    }

    private async void ReadSelected_Click(object? sender, RoutedEventArgs e)
    {
        var partition = GetPartitionName();
        if (partition is null)
        {
            return;
        }

        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = $"保存 {partition} 分区镜像",
            SuggestedFileName = $"{partition}.img",
            DefaultExtension = "img",
            FileTypeChoices =
            [
                new FilePickerFileType("镜像文件") { Patterns = ["*.img"] },
                FilePickerFileTypes.All,
            ],
        });
        var path = file?.TryGetLocalPath();
        if (!string.IsNullOrWhiteSpace(path))
        {
            await RunEdlAsync(["r", partition, path], $"回读 {partition}");
        }
    }

    private async void ReadPartitionTable_Click(object? sender, RoutedEventArgs e)
    {
        var captured = new StringBuilder();
        var exitCode = await RunEdlAsync(["printgpt"], "读取设备分区表", text => captured.Append(text));
        if (exitCode == 0)
        {
            var rows = ParsePartitions(captured.ToString());
            _partitionListBox.ItemsSource = rows;
            _emptyPartitionPanel.IsVisible = rows.Count == 0;
        }
    }

    private async void EraseSelected_Click(object? sender, RoutedEventArgs e)
    {
        var partition = GetPartitionName();
        if (partition is null)
        {
            return;
        }

        if (Confirm("擦除分区", $"分区“{partition}”中的数据将永久丢失。\n\n确定继续？"))
        {
            await RunEdlAsync(["e", partition], $"擦除 {partition}");
        }
    }

    private async void FactoryReset_Click(object? sender, RoutedEventArgs e)
    {
        if (Confirm("恢复出厂设置", "将擦除 userdata 分区，用户数据会永久丢失。\n\n确定继续？"))
        {
            await RunEdlAsync(["e", "userdata"], "恢复出厂设置");
        }
    }

    private async void RestartSystem_Click(object? sender, RoutedEventArgs e) =>
        await RunEdlAsync(["reset", "--resetmode=reset"], "重启到系统");

    private async void ShutdownDevice_Click(object? sender, RoutedEventArgs e) =>
        await RunEdlAsync(["reset", "--resetmode=off"], "关闭设备");

    private async void RestartEdl_Click(object? sender, RoutedEventArgs e) =>
        await RunEdlAsync(["reset", "--resetmode=edl"], "重启到9008");

    private async void RestartRecovery_Click(object? sender, RoutedEventArgs e) =>
        await RunEdlAsync(["reset", "--resetmode=recovery"], "重启到Recovery");

    private async void RestartFastbootD1_Click(object? sender, RoutedEventArgs e) =>
        await RunEdlAsync(["reset", "--resetmode=fastboot"], "重启到FastbootD（方案1）");

    private async void RestartFastbootD2_Click(object? sender, RoutedEventArgs e) =>
        await RunEdlAsync(["reset", "--resetmode=fastbootd"], "重启到FastbootD（方案2）");

    private async Task<int> RunEdlAsync(
        IReadOnlyList<string> commandArguments,
        string status,
        Action<string>? capture = null)
    {
        if (!await _operationLock.WaitAsync(0, _closing.Token))
        {
            ShowError("已有任务", "已有操作正在等待9008端口或正在执行，请等待当前任务完成。");
            return -1;
        }

        _operationActive = true;
        try
        {
            var profile = _loaderComboBox.SelectedItem as LoaderProfile;
            if (profile is null)
            {
                ShowError("无法开始", "内置资源包中没有可用引导。");
                return -1;
            }

            if (!string.Equals(profile.Auth, "None", StringComparison.OrdinalIgnoreCase)
                && !string.IsNullOrWhiteSpace(profile.Auth)
                && !Confirm(
                    "机型需要授权",
                    $"当前内置引导标记的授权方案为“{profile.Auth}”。本工具不会绕过厂商认证。\n\n请确认你已有合法授权。继续？"))
            {
                return -1;
            }

            SetBusy(true);
            SetStatus($"未检测到9008设备，正在等待：{status}", DeviceState.Waiting);
            var connectedDevice = await WaitFor9008Async(status, _closing.Token);
            SetStatus($"{FormatDeviceStatus([connectedDevice])} · 正在{status}", DeviceState.Connected);

            var loaderPath = await _catalog.ExtractLoaderAsync(profile, _closing.Token);
            var arguments = new List<string>(commandArguments)
            {
                $"--loader={loaderPath}",
            };
            if (!string.IsNullOrWhiteSpace(profile.Storage)
                && !string.Equals(profile.Storage, "AUTO", StringComparison.OrdinalIgnoreCase))
            {
                arguments.Add($"--memory={profile.Storage.ToLowerInvariant()}");
            }

            var exitCode = await _backend.RunAsync(
                arguments,
                text => Dispatcher.UIThread.Post(() =>
                {
                    capture?.Invoke(text);
                    AppendLog(text);
                }),
                _closing.Token);

            AppendLog(
                exitCode == 0
                    ? $"[{DateTime.Now:HH:mm:ss}] {status}完成。{Environment.NewLine}"
                    : $"[{DateTime.Now:HH:mm:ss}] {status}失败，退出代码：{exitCode}。{Environment.NewLine}");
            return exitCode;
        }
        catch (OperationCanceledException)
        {
            AppendLog($"[{DateTime.Now:HH:mm:ss}] 任务已取消。{Environment.NewLine}");
            return -1;
        }
        catch (Exception exception)
        {
            AppendLog(exception + Environment.NewLine);
            ShowError("任务失败", exception.Message);
            return -1;
        }
        finally
        {
            _operationActive = false;
            SetBusy(false);
            _operationLock.Release();
            _ = RefreshDeviceStatusAfterOperationAsync();
        }
    }

    private async Task<EdlPortInfo> WaitFor9008Async(string status, CancellationToken cancellationToken)
    {
        var announced = false;
        while (true)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var devices = await EdlPortDetector.DetectAsync(cancellationToken);
            if (devices.Count > 0)
            {
                _lastDeviceStatus = FormatDeviceStatus(devices);
                SetStatus($"{_lastDeviceStatus} · 准备{status}", DeviceState.Connected);
                AppendLog($"[{DateTime.Now:HH:mm:ss}] 已检测到9008端口，开始{status}。{Environment.NewLine}");
                return devices[0];
            }

            if (!announced)
            {
                AppendLog($"[{DateTime.Now:HH:mm:ss}] 正在等待设备进入 Qualcomm 9008 模式…{Environment.NewLine}");
                announced = true;
            }
            _lastDeviceStatus = "未检测到9008设备";
            SetStatus($"未检测到9008设备，正在等待：{status}", DeviceState.Waiting);
            await Task.Delay(TimeSpan.FromSeconds(2), cancellationToken);
        }
    }

    private async Task MonitorDeviceStatusAsync(CancellationToken cancellationToken)
    {
        while (!cancellationToken.IsCancellationRequested)
        {
            try
            {
                if (!_operationActive)
                {
                    await RefreshDeviceStatusAsync(force: false, cancellationToken);
                }
                await Task.Delay(TimeSpan.FromSeconds(3), cancellationToken);
            }
            catch (OperationCanceledException)
            {
                return;
            }
            catch
            {
                if (!_operationActive)
                {
                    SetStatus("9008设备检测失败", DeviceState.Disconnected);
                }
                await Task.Delay(TimeSpan.FromSeconds(5), cancellationToken);
            }
        }
    }

    private async Task RefreshDeviceStatusAfterOperationAsync()
    {
        try
        {
            await Task.Delay(350, _closing.Token);
            await RefreshDeviceStatusAsync(force: true, _closing.Token);
        }
        catch (OperationCanceledException)
        {
        }
        catch
        {
            SetStatus("9008设备检测失败", DeviceState.Disconnected);
        }
    }

    private async Task RefreshDeviceStatusAsync(bool force, CancellationToken cancellationToken)
    {
        if (!force && _operationActive)
        {
            return;
        }

        if (!await _deviceRefreshLock.WaitAsync(0, cancellationToken))
        {
            return;
        }

        try
        {
            var devices = await EdlPortDetector.DetectAsync(cancellationToken);
            if (!force && _operationActive)
            {
                return;
            }

            _lastDeviceStatus = FormatDeviceStatus(devices);
            SetStatus(
                _lastDeviceStatus,
                devices.Count > 0 ? DeviceState.Connected : DeviceState.Disconnected);
        }
        finally
        {
            _deviceRefreshLock.Release();
        }
    }

    private static string FormatDeviceStatus(IReadOnlyList<EdlPortInfo> devices)
    {
        if (devices.Count == 0)
        {
            return "未检测到9008设备";
        }

        var first = devices[0];
        var port = first.PortLabel;
        var name = string.IsNullOrWhiteSpace(first.Name) ? "Qualcomm 9008" : first.Name.Trim();
        return devices.Count == 1
            ? $"已检测到9008设备：{port} · {name}"
            : $"已检测到9008设备：{port} · {name}（共{devices.Count}台）";
    }

    private string? GetPartitionName()
    {
        if (_partitionListBox.SelectedItem is PartitionRow row && !string.IsNullOrWhiteSpace(row.Name))
        {
            return row.Name;
        }

        var value = _partitionSearchTextBox.Text?.Trim();
        if (!string.IsNullOrWhiteSpace(value)
            && Regex.IsMatch(value, "^[A-Za-z0-9_.:+-]{1,128}$"))
        {
            return value;
        }

        ShowError("请选择分区", "请在分区表中选择一项，或在“搜索分区”框中输入准确的分区名。");
        return null;
    }

    private static IReadOnlyList<PartitionRow> ParsePartitions(string output)
    {
        var rows = new List<PartitionRow>();
        var pattern = new Regex(
            @"(?im)^\s*(?<index>\d+)\s*[:|]\s*(?<name>[A-Za-z0-9_.:+-]+).*?(?<start>0x[0-9a-f]+|\d+).*?(?<size>0x[0-9a-f]+|\d+)\s*$",
            RegexOptions.Compiled);
        foreach (Match match in pattern.Matches(output))
        {
            rows.Add(new PartitionRow
            {
                Index = int.TryParse(match.Groups["index"].Value, out var index) ? index : rows.Count,
                Name = match.Groups["name"].Value,
                StartSector = match.Groups["start"].Value,
                Size = match.Groups["size"].Value,
            });
        }
        return rows;
    }

    private static string GetWorkDirectory()
    {
        var directory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
            "老八刷机工具");
        Directory.CreateDirectory(directory);
        return directory;
    }

    private void AppendLog(string text)
    {
        _logTextBox.Text = (_logTextBox.Text ?? string.Empty) + text;
        _logTextBox.CaretIndex = _logTextBox.Text.Length;
    }

    private void SetBusy(bool busy) => _busyProgressBar.IsVisible = busy;

    private void SetStatus(string text, DeviceState state)
    {
        _statusTextBlock.Text = text;
        _statusDot.Fill = state switch
        {
            DeviceState.Connected => ConnectedBrush,
            DeviceState.Waiting => WaitingBrush,
            _ => DisconnectedBrush,
        };
    }

    private enum DeviceState
    {
        Disconnected,
        Waiting,
        Connected,
    }
}