using System.Diagnostics;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using LaobaAvalonia.Models;

namespace LaobaAvalonia.Services;

public sealed class EngineService
{
    private const string ResourceName = "LaobaAvalonia.Resources.LaobaEngine.exe";
    private readonly string _enginePath;

    public EngineService()
    {
        _enginePath = ExtractEngine();
    }

    public Task<IReadOnlyList<LoaderOption>> ListLoadersAsync(CancellationToken cancellationToken = default) =>
        RunJsonAsync<LoaderOption>(new[] { "list-loaders" }, cancellationToken);

    public Task<IReadOnlyList<DetectedDevice>> DetectAsync(CancellationToken cancellationToken = default) =>
        RunJsonAsync<DetectedDevice>(new[] { "detect" }, cancellationToken);

    public async Task<int> RunStreamingAsync(
        IEnumerable<string> arguments,
        Action<string> onLine,
        CancellationToken cancellationToken = default)
    {
        using var process = CreateProcess(arguments);
        process.OutputDataReceived += (_, eventArgs) =>
        {
            if (eventArgs.Data is not null)
            {
                onLine(eventArgs.Data + Environment.NewLine);
            }
        };
        process.ErrorDataReceived += (_, eventArgs) =>
        {
            if (eventArgs.Data is not null)
            {
                onLine(eventArgs.Data + Environment.NewLine);
            }
        };

        if (!process.Start())
        {
            throw new InvalidOperationException("无法启动内置刷机核心");
        }

        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        await process.WaitForExitAsync(cancellationToken);
        return process.ExitCode;
    }

    private async Task<IReadOnlyList<T>> RunJsonAsync<T>(
        IEnumerable<string> arguments,
        CancellationToken cancellationToken)
    {
        using var process = CreateProcess(arguments);
        if (!process.Start())
        {
            throw new InvalidOperationException("无法启动内置刷机核心");
        }

        var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        var stdout = await stdoutTask;
        var stderr = await stderrTask;

        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException(string.IsNullOrWhiteSpace(stderr) ? "内置核心执行失败" : stderr.Trim());
        }

        return JsonSerializer.Deserialize<List<T>>(stdout, new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
        }) ?? new List<T>();
    }

    private Process CreateProcess(IEnumerable<string> arguments)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = _enginePath,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            WorkingDirectory = Environment.GetFolderPath(Environment.SpecialFolder.MyDocuments),
        };
        foreach (var argument in arguments)
        {
            startInfo.ArgumentList.Add(argument);
        }
        return new Process { StartInfo = startInfo, EnableRaisingEvents = true };
    }

    private static string ExtractEngine()
    {
        var assembly = Assembly.GetExecutingAssembly();
        using var stream = assembly.GetManifestResourceStream(ResourceName)
            ?? throw new InvalidOperationException("程序中缺少内置刷机核心");

        using var memory = new MemoryStream();
        stream.CopyTo(memory);
        var bytes = memory.ToArray();
        var hash = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()[..16];
        var directory = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "老八刷机工具",
            "runtime",
            hash);
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, "老八核心.exe");
        if (!File.Exists(path) || new FileInfo(path).Length != bytes.Length)
        {
            File.WriteAllBytes(path, bytes);
        }
        return path;
    }
}
