using System.Text;
using System.Text.RegularExpressions;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Markup.Xaml;
using Avalonia.Platform.Storage;
using Avalonia.Threading;

namespace Laoba.App;

public sealed partial class MainWindow : Window
{
    private readonly ResourceCatalog _catalog = new();
    private readonly BackendRunner _backend = new();
    private readonly CancellationTokenSource _closing = new();

    private readonly ComboBox _portComboBox;
    private readonly ComboBox _loaderComboBox;
    private readonly TextBox _xmlPathTextBox;
    private readonly TextBox _partitionSearchTextBox;
    private readonly TextBox _logTextBox;
    private readonly ListBox _partitionListBox;
    private readonly StackPanel _emptyPartitionPanel;
    private readonly TextBlock _statusTextBlock;
    private readonly ProgressBar _busyProgressBar;
    private readonly RadioButton _useXmlRadio;

    public MainWindow()
    {
        AvaloniaXamlLoader.Load(this);

        _portComboBox = this.FindControl<ComboBox>("PortComboBox")!;
        _loaderComboBox = this.FindControl<ComboBox>("LoaderComboBox")!;
        _xmlPathTextBox = this.FindControl<TextBox>("XmlPathTextBox")!;
        _partitionSearchTextBox = this.FindControl<TextBox>("PartitionSearchTextBox")!;
        _logTextBox = this.FindControl<TextBox>("LogTextBox")!;
        _partitionListBox = this.FindControl<ListBox>("PartitionListBox")!;
        _emptyPartitionPanel = this.FindControl<StackPanel>("EmptyPartitionPanel")!;
        _statusTextBlock = this.FindControl<TextBlock>("StatusTextBlock")!;
        _busyProgressBar = this.FindControl<ProgressBar>("BusyProgressBar")!;
        _useXmlRadio = this.FindControl<RadioButton>("UseXmlRadio")!;

        // 日志区按要求保持完全空白，不写启动提示、版本或资源包说明。
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
            _statusTextBlock.Text = "内置引导加载失败";
            _ = ShowInfoAsync("资源包错误", exception.Message);
        }

        Closing += (_, _) => _closing.Cancel();
    }

    private async void BrowseXml_Click(object? sender, RoutedEventArgs e)
    {
        var storage = StorageProvider;
        var result = await storage.OpenFilePickerAsync(new FilePickerOpenOptions
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
        }
    }

    private async void DetectDevice_Click(object? sender, RoutedEventArgs e)
    {
        SetBusy(true, "正在检测 9008 设备…");
        try
        {
            var count = await DeviceDetector.DetectAsync(_closing.Token);
            _statusTextBlock.Text = count > 0 ? $"已连接 {count} 台 9008 设备" : "未检测到 9008 设备";
        }
        catch (Exception exception)
        {
            _statusTextBlock.Text = "设备检测失败";
            await ShowInfoAsync("检测失败", exception.Message);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private void ClearLog_Click(object? sender, RoutedEventArgs e) => _logTextBox.Text = string.Empty;

    private async void FlashSelected_Click(object? sender, RoutedEventArgs e)
    {
        if (_useXmlRadio.IsChecked == true && !string.IsNullOrWhiteSpace(_xmlPathTextBox.Text))
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

        if (!await ConfirmAsync("写入分区", $"即将把镜像写入分区“{partition}”。错误镜像可能导致设备无法启动。\n\n确定继续？"))
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
            await ShowInfoAsync("缺少 XML", "请先选择有效的 rawprogram XML 文件。");
            return;
        }

        var directory = Path.GetDirectoryName(rawprogram)!;
        var patch = Directory.EnumerateFiles(directory, "patch*.xml", SearchOption.TopDirectoryOnly)
            .FirstOrDefault();
        if (patch is null)
        {
            await ShowInfoAsync("缺少 patch XML", "rawprogram XML 所在目录中没有找到 patch*.xml。");
            return;
        }

        if (!await ConfirmAsync("XML 刷写", "将执行多分区 XML 刷写。请确认 XML、镜像目录和所选内置引导完全匹配设备。\n\n确定继续？"))
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

        if (!await ConfirmAsync("目录刷写", "将按目录内的分区镜像进行批量写入。请确认固件与设备完全匹配。\n\n确定继续？"))
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

        if (await ConfirmAsync("擦除分区", $"分区“{partition}”中的数据将永久丢失。\n\n确定继续？"))
        {
            await RunEdlAsync(["e", partition], $"擦除 {partition}");
        }
    }

    private async void FactoryReset_Click(object? sender, RoutedEventArgs e)
    {
        if (await ConfirmAsync("恢复出厂设置", "将擦除 userdata 分区，用户数据会永久丢失。\n\n确定继续？"))
        {
            await RunEdlAsync(["e", "userdata"], "恢复出厂设置");
        }
    }

    private async void ResetDevice_Click(object? sender, RoutedEventArgs e) =>
        await RunEdlAsync(["reset"], "重启设备");

    private async Task<int> RunEdlAsync(
        IReadOnlyList<string> commandArguments,
        string status,
        Action<string>? capture = null)
    {
        LoaderProfile? profile;
        try
        {
            profile = _loaderComboBox.SelectedItem as LoaderProfile;
            if (profile is null)
            {
                throw new InvalidOperationException("内置资源包中没有可用引导。");
            }

            if (!string.Equals(profile.Auth, "None", StringComparison.OrdinalIgnoreCase)
                && !string.IsNullOrWhiteSpace(profile.Auth))
            {
                var accepted = await ConfirmAsync(
                    "机型需要授权",
                    $"当前内置引导标记的授权方案为“{profile.Auth}”。本工具不会绕过厂商认证。\n\n请确认你已有合法授权。继续？");
                if (!accepted)
                {
                    return -1;
                }
            }
        }
        catch (Exception exception)
        {
            await ShowInfoAsync("无法开始", exception.Message);
            return -1;
        }

        SetBusy(true, status);
        try
        {
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
            if (_portComboBox.SelectedIndex == 2)
            {
                arguments.Add("--serial");
            }

            var exitCode = await _backend.RunAsync(
                arguments,
                text => Dispatcher.UIThread.Post(() =>
                {
                    capture?.Invoke(text);
                    AppendLog(text);
                }),
                _closing.Token);

            _statusTextBlock.Text = exitCode == 0 ? "任务完成" : $"任务失败（代码 {exitCode}）";
            return exitCode;
        }
        catch (OperationCanceledException)
        {
            _statusTextBlock.Text = "任务已取消";
            return -1;
        }
        catch (Exception exception)
        {
            _statusTextBlock.Text = "任务失败";
            AppendLog(exception + Environment.NewLine);
            await ShowInfoAsync("任务失败", exception.Message);
            return -1;
        }
        finally
        {
            SetBusy(false);
        }
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

        _ = ShowInfoAsync("请选择分区", "请在分区表中选择一项，或在“搜索分区”框中输入准确的分区名。");
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

    private void AppendLog(string text)
    {
        _logTextBox.Text = (_logTextBox.Text ?? string.Empty) + text;
        _logTextBox.CaretIndex = _logTextBox.Text.Length;
    }

    private void SetBusy(bool busy, string? text = null)
    {
        _busyProgressBar.IsVisible = busy;
        if (!string.IsNullOrWhiteSpace(text))
        {
            _statusTextBlock.Text = text;
        }
    }

    private async Task<bool> ConfirmAsync(string title, string message)
    {
        var accepted = false;
        var dialog = new Window
        {
            Title = title,
            Width = 470,
            Height = 230,
            CanResize = false,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
        };
        var confirm = new Button { Content = "继续", Classes = { "primary" }, MinWidth = 90 };
        var cancel = new Button { Content = "取消", MinWidth = 90 };
        confirm.Click += (_, _) => { accepted = true; dialog.Close(); };
        cancel.Click += (_, _) => dialog.Close();
        dialog.Content = new Grid
        {
            RowDefinitions = new RowDefinitions("*,Auto"),
            Margin = new Avalonia.Thickness(22),
            Children =
            {
                new TextBlock { Text = message, TextWrapping = Avalonia.Media.TextWrapping.Wrap, FontSize = 14 },
                new StackPanel
                {
                    GridRow = 1,
                    Orientation = Avalonia.Layout.Orientation.Horizontal,
                    HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Right,
                    Spacing = 10,
                    Children = { cancel, confirm },
                },
            },
        };
        await dialog.ShowDialog(this);
        return accepted;
    }

    private async Task ShowInfoAsync(string title, string message)
    {
        var dialog = new Window
        {
            Title = title,
            Width = 450,
            Height = 210,
            CanResize = false,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
        };
        var close = new Button { Content = "确定", Classes = { "primary" }, MinWidth = 90 };
        close.Click += (_, _) => dialog.Close();
        dialog.Content = new Grid
        {
            RowDefinitions = new RowDefinitions("*,Auto"),
            Margin = new Avalonia.Thickness(22),
            Children =
            {
                new TextBlock { Text = message, TextWrapping = Avalonia.Media.TextWrapping.Wrap, FontSize = 14 },
                new StackPanel
                {
                    GridRow = 1,
                    HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Right,
                    Children = { close },
                },
            },
        };
        await dialog.ShowDialog(this);
    }
}
