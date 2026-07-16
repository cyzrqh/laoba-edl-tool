namespace LaobaAvalonia.Models;

public sealed class PartitionRow
{
    public int Lun { get; init; }
    public int Number { get; init; }
    public string Name { get; init; } = string.Empty;
    public string StartSector { get; init; } = string.Empty;
    public string Size { get; init; } = string.Empty;
    public string File { get; set; } = string.Empty;
}
