using System.Collections.ObjectModel;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Media;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using LaobaAvalonia.Models;
using LaobaAvalonia.Services;

namespace LaobaAvalonia;

public sealed partial class MainWindow : Window
{
    private readonly EngineService _engine;
    private readonly ObservableCollection<PartitionRow> _partitions = new();
    private readonly ObservableCollection<PartitionRow> _visiblePartitions = new();
    private IReadOnlyList<LoaderOption> _loaders = Array.Empty<LoaderOption>();
    private string? _patchXmlPath;
    private bool _busy;

    public MainWindow()
    {
        InitializeComponent();
        _engine = new EngineService();
        PartitionGrid.ItemsSource = _visiblePartitions;
        Opened += async (_, _) => await LoadBuiltInLoadersAsync();
    }

    private async Task LoadBuiltInLoadersAsync()
    {
        try
        {
            SetStatus("正在读取内置引导…", false);
            _loaders = await _engine.ListLoadersAsync();
            LoaderComboBox.ItemsSource = _loaders;
            if (_loaders.Count > 0)
            {
                LoaderComboBox.SelectedIndex = 0;
            }
            SetStatus(_loaders.Count > 0 ? $"已加载 {_loaders.Count} 个内置引导" : "未找到内置引导", _loaders.Count > 0);
        }
        catch (Exception exc)
        {
            SetStatus("内置引导加载失败", false);
            await ShowMessageAsync("内置引导加载失败", exc.Message);
        }
    }

    private LoaderOption? SelectedLoader => LoaderComboBox.SelectedItem as LoaderOption;

    private IEnumerable<string> CommonEngineArguments(string operation)
    {
        var loader = SelectedLoader ?? throw new InvalidOperationException("请选择内置引导");
        var arguments = new List<string>
        {
            "run",
            "--profile-index",
            loader.Index.ToString(),
        };

        switch (PortComboBox.SelectedIndex)
        {
            case 1:
                arguments.AddRange(new[] { "--transport", "serial" });
                break;
            case 2:
                arguments.AddRange(new[] { "--transport", "port" });
                break;
            default:
                arguments.AddRange(new[] { "--transport", "usb" });
                break;
        }

        arguments.Add(operation);
        return arguments;
    }

    private async Task RunEngineAsync(IEnumerable<string> arguments, string taskName)
    {
        if (_busy)
        {
            await ShowMessageAsync("任务正在运行", "请等待当前任务完成后再执行其他操作。");
            return;
        }

        _busy = true;
        SetStatus($"正在执行：{taskName}", false);
        AppendLog($"[{DateTime.Now:HH:mm:ss}] {taskName}\r\n");
        try
        {
            var exitCode = await _engine.RunStreamingAsync(arguments, AppendLog);
            if (exitCode == 0)
            {
                AppendLog($"[{DateTime.Now:HH:mm:ss}] 操作完成\r\n");
                SetStatus("任务完成", true);
            }
            else
            {
                AppendLog($"[{DateTime.Now:HH:mm:ss}] 操作失败，代码 {exitCode}\r\n");
                SetStatus($"任务失败（{exitCode}）", false);
            }
        }
        catch (Exception exc)
        {
            AppendLog(exc.Message + Environment.NewLine);
            SetStatus("任务失败", false);
            await ShowMessageAsync("无法执行", exc.Message);
        }
        finally
        {
            _busy = false;
        }
    }

    private void AppendLog(string text)
    {
        Dispatcher.UIThread.Post(() =>
        {
            LogTextBox.Text = (LogTextBox.Text ?? string.Empty) + text;
            LogTextBox.CaretIndex = LogTextBox.Text?.Length ?? 0;
        });
    }

    private void SetStatus(string text, bool success)
    {
        StatusText.Text = text;
        StatusDot.Fill = new SolidColorBrush(Color.Parse(success ? "#20B26B" : "#F0A020"));
    }

    private async void DetectDevice_OnClick(object? sender, RoutedEventArgs e)
    {
        try
        {
            SetStatus("正在检测设备…", false);
            var devices = await _engine.DetectAsync();
            if (devices.Count == 0)
            {
                SetStatus("未检测到 Qualcomm 9008 设备", false);
                AppendLog("未检测到 Qualcomm 9008 设备。\r\n");
                return;
            }

            SetStatus($"已连接 {devices.Count} 台 9008 设备", true);
            foreach (var device in devices)
            {
                AppendLog($"{device.Name} | {device.PnpDeviceId}\r\n");
            }
        }
        catch (Exception exc)
        {
            SetStatus("设备检测失败", false);
            await ShowMessageAsync("设备检测失败", exc.Message);
        }
    }

    private async void ChooseXml_OnClick(object? sender, RoutedEventArgs e)
    {
        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = "选择 rawprogram XML",
            AllowMultiple = false,
            FileTypeFilter = new[]
            {
                new FilePickerFileType("XML 文件") { Patterns = new[] { "*.xml" } },
            },
        });
        if (files.Count == 0)
        {
            return;
        }

        var rawprogram = files[0].Path.LocalPath;
        XmlPathTextBox.Text = rawprogram;
        var directory = Path.GetDirectoryName(rawprogram);
        _patchXmlPath = directory is null
            ? null
            : Directory.EnumerateFiles(directory, "patch*.xml", SearchOption.TopDirectoryOnly).FirstOrDefault();
    }

    private void LoaderComboBox_OnSelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (SelectedLoader is { } loader)
        {
            ToolTip.SetTip(LoaderComboBox, $"{loader.Brand} / {loader.Series} / {loader.Name}\n存储：{loader.Storage}  授权：{loader.Auth}");
        }
    }

    private async void FlashSelected_OnClick(object? sender, RoutedEventArgs e)
    {
        if (!string.IsNullOrWhiteSpace(XmlPathTextBox.Text))
        {
            if (string.IsNullOrWhiteSpace(_patchXmlPath))
            {
                await ShowMessageAsync("缺少 patch XML", "rawprogram.xml 同目录中没有找到 patch*.xml。");
                return;
            }
            var imageDirectory = Path.GetDirectoryName(XmlPathTextBox.Text!)!;
            var args = CommonEngineArguments("qfil").Concat(new[]
            {
                "--rawprogram", XmlPathTextBox.Text!,
                "--patch", _patchXmlPath,
                "--image-dir", imageDirectory,
            });
            await RunEngineAsync(args, "QFIL XML 刷入");
            return;
        }

        var partition = GetSingleSelectedPartition();
        if (partition is null)
        {
            await ShowMessageAsync("请选择分区", "请先在分区表中选择一个分区，或在上方选择 XML 文件。");
            return;
        }

        var files = await StorageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
        {
            Title = $"选择写入 {partition.Name} 的镜像",
            AllowMultiple = false,
            FileTypeFilter = new[]
            {
                new FilePickerFileType("镜像文件") { Patterns = new[] { "*.img", "*.bin", "*.mbn" } },
                FilePickerFileTypes.All,
            },
        });
        if (files.Count == 0)
        {
            return;
        }

        if (!await ConfirmAsync("写入分区确认", $"即将把镜像写入分区“{partition.Name}”。错误镜像可能导致设备无法启动。\n\n确定继续？"))
        {
            return;
        }

        var args = CommonEngineArguments("write").Concat(new[]
        {
            "--partition", partition.Name,
            "--image", files[0].Path.LocalPath,
        });
        await RunEngineAsync(args, $"写入分区 {partition.Name}");
    }

    private async void FlashFolder_OnClick(object? sender, RoutedEventArgs e)
    {
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = "选择镜像目录",
            AllowMultiple = false,
        });
        if (folders.Count == 0)
        {
            return;
        }
        if (!await ConfirmAsync("目录刷入确认", "将按目录中的分区镜像批量写入，请确保固件与设备完全匹配。\n\n确定继续？"))
        {
            return;
        }
        var args = CommonEngineArguments("flash-folder").Concat(new[] { "--image-dir", folders[0].Path.LocalPath });
        await RunEngineAsync(args, "刷入指定目录全部文件");
    }

    private async void BackupAll_OnClick(object? sender, RoutedEventArgs e)
    {
        var folders = await StorageProvider.OpenFolderPickerAsync(new FolderPickerOpenOptions
        {
            Title = "选择整机备份目录",
            AllowMultiple = false,
        });
        if (folders.Count == 0)
        {
            return;
        }
        var args = CommonEngineArguments("backup").Concat(new[]
        {
            "--output-dir", folders[0].Path.LocalPath,
            "--skip", "userdata",
        });
        await RunEngineAsync(args, "整机分区备份");
    }

    private async void ReadSelected_OnClick(object? sender, RoutedEventArgs e)
    {
        var partition = GetSingleSelectedPartition();
        if (partition is null)
        {
            await ShowMessageAsync("请选择分区", "请先在分区表中选择一个分区。");
            return;
        }
        var file = await StorageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
        {
            Title = $"保存 {partition.Name} 分区镜像",
            SuggestedFileName = partition.Name + ".img",
            DefaultExtension = "img",
        });
        if (file is null)
        {
            return;
        }
        var args = CommonEngineArguments("read").Concat(new[]
        {
            "--partition", partition.Name,
            "--output", file.Path.LocalPath,
        });
        await RunEngineAsync(args, $"回读分区 {partition.Name}");
    }

    private async void EraseSelected_OnClick(object? sender, RoutedEventArgs e)
    {
        var partition = GetSingleSelectedPartition();
        if (partition is null)
        {
            await ShowMessageAsync("请选择分区", "请先在分区表中选择一个分区。");
            return;
        }
        if (!await ConfirmAsync("擦除分区确认", $"将永久擦除分区“{partition.Name}”，该操作不可撤销。\n\n确定继续？"))
        {
            return;
        }
        var args = CommonEngineArguments("erase").Concat(new[] { "--partition", partition.Name });
        await RunEngineAsync(args, $"擦除分区 {partition.Name}");
    }

    private async void FactoryReset_OnClick(object? sender, RoutedEventArgs e)
    {
        if (!await ConfirmAsync("恢复出厂设置", "将擦除 userdata 分区，所有用户数据会永久丢失。\n\n确定继续？"))
        {
            return;
        }
        var args = CommonEngineArguments("erase").Concat(new[] { "--partition", "userdata" });
        await RunEngineAsync(args, "恢复出厂设置");
    }

    private async void ResetDevice_OnClick(object? sender, RoutedEventArgs e) =>
        await RunEngineAsync(CommonEngineArguments("reset"), "重启设备");

    private async void MoreFeatures_OnClick(object? sender, RoutedEventArgs e) =>
        await RunEngineAsync(CommonEngineArguments("printgpt"), "读取设备分区表");

    private void ClearLog_OnClick(object? sender, RoutedEventArgs e) => LogTextBox.Text = string.Empty;

    private void PartitionGrid_OnSelectionChanged(object? sender, SelectionChangedEventArgs e)
    {
        SelectedCountText.Text = PartitionGrid.SelectedItems.Count.ToString();
    }

    private void SelectAll_OnChecked(object? sender, RoutedEventArgs e) => PartitionGrid.SelectAll();

    private void SelectAll_OnUnchecked(object? sender, RoutedEventArgs e) => PartitionGrid.SelectedItems.Clear();

    private void PartitionSearch_OnTextChanged(object? sender, TextChangedEventArgs e)
    {
        var query = PartitionSearchTextBox.Text?.Trim() ?? string.Empty;
        _visiblePartitions.Clear();
        foreach (var partition in _partitions.Where(item => string.IsNullOrEmpty(query) || item.Name.Contains(query, StringComparison.OrdinalIgnoreCase)))
        {
            _visiblePartitions.Add(partition);
        }
        EmptyPartitionPanel.IsVisible = _visiblePartitions.Count == 0;
    }

    private PartitionRow? GetSingleSelectedPartition() => PartitionGrid.SelectedItem as PartitionRow;

    private async Task ShowMessageAsync(string title, string message)
    {
        var dialog = BuildDialog(title, message, false);
        await dialog.ShowDialog(this);
    }

    private async Task<bool> ConfirmAsync(string title, string message)
    {
        var dialog = BuildDialog(title, message, true);
        return await dialog.ShowDialog<bool>(this);
    }

    private static Window BuildDialog(string title, string message, bool confirmation)
    {
        var dialog = new Window
        {
            Title = title,
            Width = 460,
            Height = 230,
            CanResize = false,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Background = Brushes.White,
            FontFamily = new FontFamily("Microsoft YaHei UI, Segoe UI"),
        };

        var grid = new Grid
        {
            RowDefinitions = new RowDefinitions("*,64"),
            Margin = new Thickness(24),
        };
        grid.Children.Add(new TextBlock
        {
            Text = message,
            TextWrapping = TextWrapping.Wrap,
            FontSize = 15,
            VerticalAlignment = Avalonia.Layout.VerticalAlignment.Center,
        });

        var buttons = new StackPanel
        {
            Orientation = Avalonia.Layout.Orientation.Horizontal,
            HorizontalAlignment = Avalonia.Layout.HorizontalAlignment.Right,
            Spacing = 10,
        };
        Grid.SetRow(buttons, 1);
        if (confirmation)
        {
            var cancel = new Button { Content = "取消", Width = 92 };
            cancel.Click += (_, _) => dialog.Close(false);
            buttons.Children.Add(cancel);
            var confirm = new Button { Content = "继续", Width = 92, Background = new SolidColorBrush(Color.Parse("#0B6CFF")), Foreground = Brushes.White };
            confirm.Click += (_, _) => dialog.Close(true);
            buttons.Children.Add(confirm);
        }
        else
        {
            var close = new Button { Content = "确定", Width = 92 };
            close.Click += (_, _) => dialog.Close();
            buttons.Children.Add(close);
        }
        grid.Children.Add(buttons);
        dialog.Content = grid;
        return dialog;
    }
}
