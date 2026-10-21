using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;

namespace StructCalcAddin.Models
{
    public static class XchgUnits
    {
        public const double FtToM = 0.3048;
        public const double MToFt = 1.0 / 0.3048;
        public const double Ft2ToM2 = 0.09290304;
        public const double Ft4ToM4 = 0.008630974;
        public const double FtToMm = 304.8;
        public const double MmToFt = 1.0 / 304.8;

        public static double? FtToMeters(double? v) => v.HasValue ? v.Value * FtToM : (double?)null;
        public static double? MetersToFt(double? v) => v.HasValue ? v.Value * MToFt : (double?)null;
        public static double? Ft2ToSquareMeters(double? v) => v.HasValue ? v.Value * Ft2ToM2 : (double?)null;
        public static double? Ft4ToMeters4(double? v) => v.HasValue ? v.Value * Ft4ToM4 : (double?)null;
    }

    public class XyzDto
    {
        public double X { get; set; }
        public double Y { get; set; }
        public double Z { get; set; }

        public static XyzDto FromXyzFeet(XYZ p) =>
            p == null ? null : new XyzDto { X = p.X * XchgUnits.FtToM, Y = p.Y * XchgUnits.FtToM, Z = p.Z * XchgUnits.FtToM };

        public XYZ ToXyzFeet() => new XYZ(X * XchgUnits.MToFt, Y * XchgUnits.MToFt, Z * XchgUnits.MToFt);
    }

    public class NodeDto
    {
        public long Id { get; set; }
        public XyzDto Position { get; set; }
        public string Name { get; set; }
        public bool? IsSupport { get; set; }
        public SupportDto Support { get; set; }
    }

    public class SupportDto
    {
        public string Preset { get; set; }
        public bool? FixedX { get; set; }
        public bool? FixedY { get; set; }
        public bool? FixedZ { get; set; }
        public bool? FixedRx { get; set; }
        public bool? FixedRy { get; set; }
        public bool? FixedRz { get; set; }
    }

    public class BarDto
    {
        public long Id { get; set; }
        public long StartNodeId { get; set; }
        public long EndNodeId { get; set; }
        public string Name { get; set; }
        public string StructuralType { get; set; }
        public SectionDto Section { get; set; }
        public MaterialDto Material { get; set; }
        public List<LoadDto> Loads { get; set; } = new List<LoadDto>();
    }

    public class SectionDto
    {
        public string Name { get; set; }
        public string Shape { get; set; }
        public double? Width { get; set; }
        public double? Height { get; set; }
        public double? Diameter { get; set; }
        public double? Area { get; set; }
        public double? Iy { get; set; }
        public double? Iz { get; set; }
        public double? J { get; set; }
    }

    public class MaterialDto
    {
        public string Name { get; set; }
        public string Type { get; set; }
        public double? Fc { get; set; }
        public double? Fy { get; set; }
        public double? E { get; set; }
        public double? Nu { get; set; }
        public double? Rho { get; set; }
    }

    public class LoadDto
    {
        public string Type { get; set; }
        public XyzDto Force { get; set; }
        public XyzDto Moment { get; set; }
        public double? StartDist { get; set; }
        public double? EndDist { get; set; }
        public string LoadCase { get; set; }
    }

    public class StructuralModelDto
    {
        public string ProjectName { get; set; }
        public string RevitVersion { get; set; }
        public DateTime ExportTime { get; set; } = DateTime.UtcNow;
        public List<NodeDto> Nodes { get; set; } = new List<NodeDto>();
        public List<BarDto> Bars { get; set; } = new List<BarDto>();
        public List<LoadCaseDto> LoadCases { get; set; } = new List<LoadCaseDto>();
        public List<string> Notes { get; set; } = new List<string>();
    }

    public class LoadCaseDto
    {
        public string Name { get; set; }
        public string Type { get; set; }
        public int? Number { get; set; }
    }

    public class ApplyChangesRequest
    {
        public List<ElementCreationDto> ElementCreations { get; set; } = new List<ElementCreationDto>();
        public List<BarChangeDto> BarChanges { get; set; } = new List<BarChangeDto>();
        public List<NodeChangeDto> NodeChanges { get; set; } = new List<NodeChangeDto>();
    }

    public class ElementCreationDto
    {
        public string ElementType { get; set; }
        public string FamilyName { get; set; }
        public string TypeName { get; set; }
        public SectionDto Section { get; set; }
        public LocationDto Location { get; set; }
        public string ScId { get; set; }
        public Dictionary<string, string> SharedParams { get; set; } = new Dictionary<string, string>();
    }

    public class LocationDto
    {
        public XyzDto Start { get; set; }
        public XyzDto End { get; set; }
        public XyzDto Point { get; set; }
    }

    public class BarChangeDto
    {
        public long ElementId { get; set; }
        public string NewSectionName { get; set; }
        public SectionDto NewSection { get; set; }
        public List<RebarDto> Rebars { get; set; }
    }

    public class NodeChangeDto
    {
        public long ElementId { get; set; }
        public SupportDto NewSupport { get; set; }
    }

    public class RebarDto
    {
        public long BarId { get; set; }
        public int DiameterMm { get; set; }
        public int Count { get; set; }
        public double? Position { get; set; }
        public string Layer { get; set; }
        public List<string> Hooks { get; set; } = new List<string>();
        public List<CurveDto> Curves { get; set; } = new List<CurveDto>();
        public StirrupSpacingDto StirrupSpacing { get; set; }
        public Dictionary<string, string> SharedParams { get; set; } = new Dictionary<string, string>();
    }

    public class StirrupSpacingDto
    {
        public double Zone { get; set; }
        public double Field { get; set; }
        public double AttenteLength { get; set; }
    }

    public class CurveDto
    {
        public XyzDto Start { get; set; }
        public XyzDto End { get; set; }
        public bool IsArc { get; set; }
        public XyzDto Center { get; set; }
    }

    public class ApplyResultDto
    {
        public int BarsUpdated { get; set; }
        public int NodesProcessed { get; set; }
        public int RebarsCreated { get; set; }
        public int ElementsCreated { get; set; }
        public List<string> Notes { get; set; } = new List<string>();
    }

    public class PipeEnvelope
    {
        [Newtonsoft.Json.JsonProperty("success")] public bool Success { get; set; }
        [Newtonsoft.Json.JsonProperty("data")] public object Data { get; set; }
        [Newtonsoft.Json.JsonProperty("error")] public string Error { get; set; }
        [Newtonsoft.Json.JsonProperty("request_id")] public string RequestId { get; set; }

        public static string Ok(object data, string requestId) =>
            Newtonsoft.Json.JsonConvert.SerializeObject(new PipeEnvelope { Success = true, Data = data, Error = "", RequestId = requestId ?? "" }, DtoJson.Settings);

        public static string Fail(string error, string requestId) =>
            Newtonsoft.Json.JsonConvert.SerializeObject(new PipeEnvelope { Success = false, Data = null, Error = error ?? "", RequestId = requestId ?? "" }, DtoJson.Settings);
    }

    public static class DtoJson
    {
        public static readonly Newtonsoft.Json.JsonSerializerSettings Settings = new Newtonsoft.Json.JsonSerializerSettings
        {
            ContractResolver = new Newtonsoft.Json.Serialization.CamelCasePropertyNamesContractResolver(),
            NullValueHandling = Newtonsoft.Json.NullValueHandling.Ignore,
            Formatting = Newtonsoft.Json.Formatting.None,
            ReferenceLoopHandling = Newtonsoft.Json.ReferenceLoopHandling.Ignore,
            MissingMemberHandling = Newtonsoft.Json.MissingMemberHandling.Ignore
        };

        public static string Serialize(object obj) => Newtonsoft.Json.JsonConvert.SerializeObject(obj, Settings);
        public static T Deserialize<T>(string json) => Newtonsoft.Json.JsonConvert.DeserializeObject<T>(json, Settings);
    }
}