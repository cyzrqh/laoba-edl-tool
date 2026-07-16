using System.Diagnostics;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Laoba.App;

public sealed record EdlPortInfo(string Name, string PnpDeviceId, string Port)
{
    public string PortLabel
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(Port))
            {
                return Port.Trim().ToUpperInvariant();
            }

            var match = Regex.Match(
                PnpDeviceId ?? string.Empty,
                @"VID_([0-9A-F]{4})&PID_([0-9A-F]{4})",
                RegexOptions.IgnoreCase);
            return match.Success
                ? $"USB {match.Groups[1].Value.ToUpperInvariant()}:{match.Groups[2].Value.ToUpperInvariant()}"
                : "USB 9008";
        }
    }
}

public static class EdlPortDetector
{
    public static async Task<IReadOnlyList<EdlPortInfo>> DetectAsync(
        CancellationToken cancellationToken = default)
    {
        if (!OperatingSystem.IsWindows())
        {
            return Array.Empty<EdlPortInfo>();
        }

        const string script = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); "
            + "$items=Get-CimInstance Win32_PnPEntity | Where-Object { "
            + "$_.PNPDeviceID -match 'VID_05C6&PID_9008' -or $_.Name -match 'QHSUSB|QDLoader 9008|Qualcomm.*9008' }; "
            + "$result=@($items | ForEach-Object { "
            + "$port=''; if ($_.Name -match '\\((COM[0-9]+)\\)') { $port=$Matches[1] }; "
            + "[PSCustomObject]@{ Name=[string]$_.Name; PNPDeviceID=[string]$_.PNPDeviceID; Port=[string]$port } }); "
            + "ConvertTo-Json -InputObject $result -Compress";

        var startInfo = new ProcessStartInfo
        {
            FileName = "powershell.exe",
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
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
            return Array.Empty<EdlPortInfo>();
        }

        var outputTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var errorTask = process.StandardError.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        var output = await outputTask;
        var error = await errorTask;

        if (process.ExitCode != 0)
        {
            throw new InvalidOperationException(
                string.IsNullOrWhiteSpace(error) ? "无法查询9008端口。" : error.Trim());
        }

        if (string.IsNullOrWhiteSpace(output) || output.Trim() is "null" or "[]")
        {
            return Array.Empty<EdlPortInfo>();
        }

        using var document = JsonDocument.Parse(output);
        var devices = new List<EdlPortInfo>();
        if (document.RootElement.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in document.RootElement.EnumerateArray())
            {
                devices.Add(ParseDevice(item));
            }
        }
        else if (document.RootElement.ValueKind == JsonValueKind.Object)
        {
            devices.Add(ParseDevice(document.RootElement));
        }

        return devices;
    }

    private static EdlPortInfo ParseDevice(JsonElement item)
    {
        static string Read(JsonElement source, string property)
        {
            return source.TryGetProperty(property, out var value) && value.ValueKind != JsonValueKind.Null
                ? value.ToString()
                : string.Empty;
        }

        return new EdlPortInfo(
            Read(item, "Name"),
            Read(item, "PNPDeviceID"),
            Read(item, "Port"));
    }
}