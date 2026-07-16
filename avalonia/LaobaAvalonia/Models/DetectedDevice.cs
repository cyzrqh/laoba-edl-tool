using System.Text.Json.Serialization;

namespace LaobaAvalonia.Models;

public sealed class DetectedDevice
{
    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("pnp_device_id")]
    public string PnpDeviceId { get; init; } = string.Empty;
}
