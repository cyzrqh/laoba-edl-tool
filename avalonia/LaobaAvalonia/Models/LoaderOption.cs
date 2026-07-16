using System.Text.Json.Serialization;

namespace LaobaAvalonia.Models;

public sealed class LoaderOption
{
    [JsonPropertyName("index")]
    public int Index { get; init; }

    [JsonPropertyName("brand")]
    public string Brand { get; init; } = string.Empty;

    [JsonPropertyName("series")]
    public string Series { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("storage")]
    public string Storage { get; init; } = "AUTO";

    [JsonPropertyName("auth")]
    public string Auth { get; init; } = "None";

    [JsonPropertyName("loader")]
    public string Loader { get; init; } = string.Empty;

    public override string ToString() => Loader;
}
