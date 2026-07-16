using System.Diagnostics;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Xml.Linq;

namespace Laoba.App;

public sealed record LoaderProfile(
    string Brand,
    string Series,
    string Name,
    string Storage,
    string Auth,
    string Loader,
    string Description)
{
    public string DisplayName
    {
        get
        {
            var file = Path.GetFileName(Loader.Replace('\\', '/'));
            return $"{file}  ·  {Brand} / {Series} / {Name}";
        }
    }
}

public sealed class ResourceCatalog
{
    private const string ResourceName = "Laoba.ResourcePack.zip";
    private readonly Assembly _assembly = Assembly.GetExecutingAssembly();

    public IReadOnlyList<LoaderProfile> LoadProfiles()
    {
        using var stream = OpenResource();
        using var archive = new ZipArchive(stream, ZipArchiveMode.Read, false);
        var config = archive.Entries.SingleOrDefault(entry =>
            entry.FullName.Replace('\\', '/').EndsWith("Config.xml", StringComparison.OrdinalIgnoreCase));
        if (config is null)
        {
            throw new InvalidDataException("内置资源包中没有 Config.xml。 ");
        }

        using var configStream = config.Open();
        var document = XDocument.Load(configStream);
        var root = document.Root ?? throw new InvalidDataException("Config.xml 没有根节点。");
        var profiles = new List<LoaderProfile>();

        foreach (var brandNode in root.Elements("Brand"))
        {
            var brand = (string?)brandNode.Attribute("Name") ?? "未命名品牌";
            foreach (var seriesNode in brandNode.Elements("Series"))
            {
                var series = (string?)seriesNode.Attribute("Name") ?? "未命名系列";
                foreach (var modelNode in seriesNode.Elements("Model"))
                {
                    var loader = (string?)modelNode.Attribute("Loader") ?? string.Empty;
                    if (string.IsNullOrWhiteSpace(loader))
                    {
                        continue;
                    }

                    profiles.Add(new LoaderProfile(
                        brand,
                        series,
                        (string?)modelNode.Attribute("Name") ?? "未命名机型",
                        ((string?)modelNode.Attribute("Storage") ?? "AUTO").ToUpperInvariant(),
                        (string?)modelNode.Attribute("Auth") ?? "None",
                        loader,
                        (string?)modelNode.Attribute("Description") ?? string.Empty));
                }
            }
        }

        return profiles
            .OrderBy(profile => Path.GetFileName(profile.Loader), StringComparer.OrdinalIgnoreCase)
            .ThenBy(profile => profile.Brand, StringComparer.CurrentCulture)
            .ToArray();
    }

    public async Task<string> ExtractLoaderAsync(LoaderProfile profile, CancellationToken cancellationToken = default)
    {
        using var stream = OpenResource();
        using var archive = new ZipArchive(stream, ZipArchiveMode.Read, false);
        var requested = Normalize(profile.Loader);
        var entry = archive.Entries.FirstOrDefault(item =>
                        StripRoot(item.FullName).Equals(requested, StringComparison.OrdinalIgnoreCase))
                    ?? archive.Entries.FirstOrDefault(item =>
                        Path.GetFileName(StripRoot(item.FullName)).Equals(
                            Path.GetFileName(requested), StringComparison.OrdinalIgnoreCase));

        if (entry is null)
        {
            throw new FileNotFoundException($"内置资源包中找不到引导：{profile.Loader}");
        }

        await using var input = entry.Open();
        using var memory = new MemoryStream();
        await input.CopyToAsync(memory, cancellationToken);
        var payload = memory.ToArray();
        var hash = Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant();
        var directory = Path.Combine(RuntimeDirectory(), "loaders", hash[..16]);
        Directory.CreateDirectory(directory);
        var output = Path.Combine(directory, Path.GetFileName(requested));

        if (!File.Exists(output) || new FileInfo(output).Length != payload.Length)
        {
            await File.WriteAllBytesAsync(output, payload, cancellationToken);
        }

        return output;
    }

    private Stream OpenResource() =>
        _assembly.GetManifestResourceStream(ResourceName)
        ?? throw new InvalidDataException("程序中没有内置高通资源包。");

    private static string Normalize(string value) => value.Replace('\\', '/').TrimStart('/');

    private static string StripRoot(string value)
    {
        var normalized = Normalize(value);
        var slash = normalized.IndexOf('/');
        return slash >= 0 ? normalized[(slash + 1)..] : normalized;
    }

    internal static string RuntimeDirectory()
    {
        var baseDirectory = Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData);
        var directory = Path.Combine(baseDirectory, "老八刷机工具", "runtime");
        Directory.CreateDirectory(directory);
        return directory;
    }
}

public sealed class BackendRunner
{
    private const string ResourceName = "Laoba.Backend.exe";
    private readonly SemaphoreSlim _lock = new(1, 1);
    private string? _backendPath;

    public async Task<int> RunAsync(
        IEnumerable<string> arguments,
        Action<string> onOutput,
        CancellationToken cancellationToken = default)
    {
        if (!await _lock.WaitAsync(0, cancellationToken))
        {
            throw new InvalidOperationException("已有任务正在运行。");
        }

        try
        {
            var backend = await ExtractBackendAsync(cancellationToken);
            var startInfo = new ProcessStartInfo
            {
                FileName = backend,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true,
                WorkingDirectory = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
                    "老八刷机工具"),
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };
            Directory.CreateDirectory(startInfo.WorkingDirectory);
            foreach (var argument in arguments)
            {
                startInfo.ArgumentList.Add(argument);
            }

            using var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
            if (!process.Start())
            {
                throw new InvalidOperationException("无法启动内置 EDL 后端。");
            }

            var stdoutTask = PumpAsync(process.StandardOutput, onOutput);
            var stderrTask = PumpAsync(process.StandardError, onOutput);
            await process.WaitForExitAsync(cancellationToken);
            await Task.WhenAll(stdoutTask, stderrTask);
            return process.ExitCode;
        }
        finally
        {
            _lock.Release();
        }
    }

    private static async Task PumpAsync(StreamReader reader, Action<string> onOutput)
    {
        while (await reader.ReadLineAsync() is { } line)
        {
            onOutput(line + Environment.NewLine);
        }
    }

    private async Task<string> ExtractBackendAsync(CancellationToken cancellationToken)
    {
        if (_backendPath is not null && File.Exists(_backendPath))
        {
            return _backendPath;
        }

        var assembly = Assembly.GetExecutingAssembly();
        await using var stream = assembly.GetManifestResourceStream(ResourceName)
            ?? throw new InvalidDataException("程序中没有内置 EDL 后端。");
        using var memory = new MemoryStream();
        await stream.CopyToAsync(memory, cancellationToken);
        var payload = memory.ToArray();
        var hash = Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant();
        var directory = Path.Combine(ResourceCatalog.RuntimeDirectory(), hash[..16]);
        Directory.CreateDirectory(directory);
        var output = Path.Combine(directory, "laoba-backend.exe");

        if (!File.Exists(output) || new FileInfo(output).Length != payload.Length)
        {
            await File.WriteAllBytesAsync(output, payload, cancellationToken);
        }

        _backendPath = output;
        return output;
    }
}

public static class DeviceDetector
{
    public static async Task<int> DetectAsync(CancellationToken cancellationToken = default)
    {
        if (!OperatingSystem.IsWindows())
        {
            return 0;
        }

        const string script = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
            + "$items=Get-CimInstance Win32_PnPEntity | Where-Object { "
            + "$_.PNPDeviceID -match 'VID_05C6&PID_9008' -or $_.Name -match 'QHSUSB|QDLoader 9008|Qualcomm.*9008' }; "
            + "$items | Select-Object Name,PNPDeviceID | ConvertTo-Json -Compress";

        var startInfo = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
        };
        startInfo.ArgumentList.Add("-NoProfile");
        startInfo.ArgumentList.Add("-NonInteractive");
        startInfo.ArgumentList.Add("-ExecutionPolicy");
        startInfo.ArgumentList.Add("Bypass");
        startInfo.ArgumentList.Add("-Command");
        startInfo.ArgumentList.Add(script);

        using var process = Process.Start(startInfo);
        if (process is null)
        {
            return 0;
        }

        var output = await process.StandardOutput.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        if (string.IsNullOrWhiteSpace(output) || output.Trim() == "null")
        {
            return 0;
        }

        using var document = JsonDocument.Parse(output);
        return document.RootElement.ValueKind switch
        {
            JsonValueKind.Array => document.RootElement.GetArrayLength(),
            JsonValueKind.Object => 1,
            _ => 0,
        };
    }
}

public sealed class PartitionRow
{
    public string Lun { get; init; } = "0";
    public int Index { get; init; }
    public string Name { get; init; } = string.Empty;
    public string StartSector { get; init; } = string.Empty;
    public string Size { get; init; } = string.Empty;
    public string File { get; init; } = string.Empty;
}
