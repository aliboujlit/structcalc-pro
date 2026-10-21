using System;
using System.Collections.Generic;
using Autodesk.Revit.DB;
using Newtonsoft.Json;
using Newtonsoft.Json.Serialization;

namespace StructCalcAddin.Models
{
    /// <summary>
    /// Unités du protocole (contrat avec le noyau Python) :
    ///   longueurs en mètres, aires en m², inerties en m⁴, diamètres d'armature en mm.
    /// Revit travaille en pieds (unité interne) : conversions via <see cref="Units"/>.
    /// </summary>
    public static class XchgUnits
    {
        public const double FtToM = 0.3048;
        public const double MToFt = 1.0 / 0.3048;
        public const double Ft2ToM2 = 0.09290304;      // 0.3048^2
        public const double Ft4ToM4 = 0.008630974;     // 0.3048^4
        public const double FtToMm = 304.8;
        public const double MmToFt = 1.0 / 304.8;

        public static double? FtToMeters(double? v) => v.HasValue ? v.Value * FtToM : (double?)null;
        public static double? MetersToFt(double? v) => v.HasValue ? v.Value * MToFt : (double?)null;
        public static double? Ft2ToSquareMeters(double? v) => v.HasValue ? v.Value * Ft2ToM2 : (double?)null;
        public static double? Ft4ToMeters4(double? v) => v.HasValue ? v.Value * Ft4ToM4 : (double?)null;
    }

    // ========== Géométrie (mètres) ==========
    public class XyzDto
    {
        public double X { get; set; }
        public double Y { get; set; }
        public double Z { get; set; }

        /// <summary>Depuis un point Revit (pieds) -> mètres.</summary>
        public static XyzDto FromXyzFeet(XYZ p) =>
            p == null ? null : new XyzDto { X = p.X * XchgUnits.FtToM, Y = p.Y * XchgUnits.FtToM, Z = p.Z * XchgUnits.FtToM };

        /// <summary>Vers un point Revit (pieds) depuis des mètres.</summary>
        public XYZ ToXyzFeet() => new XYZ(X * XchgUnits.MToFt, Y * XchgUnits.MToFt, Z * XchgUnits.MToFt);
    }

    // ========== Éléments structuraux ==========
    public class NodeDto
    {
        public long Id { get; set; }
        public XyzDto Position { get; set; }
        public string Name { get; set; }
        /// <summary>null = inconnu (jamais false silencieux).</summary>
        public bool? IsSupport { get; set; }
        /// <summary>null = appui détecté mais fixités indéterminables (jamais inventées).</summary>
        public SupportDto Support { get; set; }
    }

    public class SupportDto
    {
        /// <summary>Preset Revit : Fixed / Pinned / Roller / User.</summary>
        public string Preset { get; set; }
        /// <summary>null = non déterminable (paramètre absent).</summary>
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
        /// <summary>StructuralType Revit : "Beam" | "Column" | autre.</summary>
        public string StructuralType { get; set; }
        public SectionDto Section { get; set; }
        public MaterialDto Material { get; set; }
        public List<LoadDto> Loads { get; set; } = new List<LoadDto>();
    }

    public class SectionDto
    {
        public string Name { get; set; }
        /// <summary>"Rectangular" | "Circular" | null (inconnue, jamais devinée).</summary>
        public string Shape { get; set; }
        public double? Width { get; set; }      // m
        public double? Height { get; set; }     // m
        public double? Diameter { get; set; }   // m (si circulaire)
        public double? Area { get; set; }       // m²
        public double? Iy { get; set; }         // m⁴
        public double? Iz { get; set; }         // m⁴
        public double? J { get; set; }          // m⁴ (torsion)
    }

    public class MaterialDto
    {
        public string Name { get; set; }
        /// <summary>StructuralMaterialType / MaterialClass Revit ("Concrete", "Steel"...).</summary>
        public string Type { get; set; }
        // null = non extrait : Revit 2027 n'expose AUCUNE API vérifiée de propriété
        // physique de matériau (GetMaterialPropertyByName inexistant) — jamais de 0-présenté-comme-donnée.
        public double? Fc { get; set; }       // Pa (béton)
        public double? Fy { get; set; }       // Pa (acier)
        public double? E { get; set; }        // Pa
        public double? Nu { get; set; }       // Poisson
        public double? Rho { get; set; }      // kg/m³
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

    // ========== Modèle complet ==========
    public class StructuralModelDto
    {
        public string ProjectName { get; set; }
        public string RevitVersion { get; set; }
        public DateTime ExportTime { get; set; } = DateTime.UtcNow;
        public List<NodeDto> Nodes { get; set; } = new List<NodeDto>();
        public List<BarDto> Bars { get; set; } = new List<BarDto>();
        public List<LoadCaseDto> LoadCases { get; set; } = new List<LoadCaseDto>();
        /// <summary>Limites explicites de l'extraction (jamais de couverture silencieuse).</summary>
        public List<string> Notes { get; set; } = new List<string>();
    }

    public class LoadCaseDto
    {
        public string Name { get; set; }
        /// <summary>Nature du cas de charge (LoadNature) : "Dead", "Live"... si résoluble.</summary>
        public string Type { get; set; }
        public int? Number { get; set; }
    }

    // ========== Commandes d'écriture (Python -> Revit) ==========
    public class ApplyChangesRequest
    {
        public List<ElementCreationDto> ElementCreations { get; set; } = new List<ElementCreationDto>();
        public List<BarChangeDto> BarChanges { get; set; } = new List<BarChangeDto>();
        public List<NodeChangeDto> NodeChanges { get; set; } = new List<NodeChangeDto>();
    }

    public class ElementCreationDto
    {
        public string ElementType { get; set; }           // "column" | "beam" | "footing_isolated" | "footing_strip"
        public string FamilyName { get; set; }
        public string TypeName { get; set; }
        public SectionDto Section { get; set; }
        public LocationDto Location { get; set; }
        public string ScId { get; set; }
        public Dictionary<string, string> SharedParams { get; set; } = new Dictionary<string, string>();
    }

    public class LocationDto
    {
        public XyzDto Start { get; set; }      // pour column/beam
        public XyzDto End { get; set; }
        public XyzDto Point { get; set; }      // pour footing
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
        public double? Position { get; set; } // 0..1 le long de la barre
        public string Layer { get; set; }     // "Longitudinal" | "Stirrups"

        // NOUVEAUX (depuis Python writer v1.5)
        public List<string> Hooks { get; set; } = new List<string>();
        public List<CurveDto> Curves { get; set; } = new List<CurveDto>();
        public StirrupSpacingDto StirrupSpacing { get; set; }
        public Dictionary<string, string> SharedParams { get; set; } = new Dictionary<string, string>();
    }

    public class StirrupSpacingDto
    {
        public double Zone { get; set; }        // mm
        public double Field { get; set; }       // mm
        public double AttenteLength { get; set; } // mm
    }

    public class CurveDto
    {
        public XyzDto Start { get; set; }
        public XyzDto End { get; set; }
        public bool IsArc { get; set; }
        public XyzDto Center { get; set; }      // si arc
    }

    public class ElementCreationDto
    {
        public string ElementType { get; set; }           // "column" | "beam" | "footing_isolated" | "footing_strip"
        public string FamilyName { get; set; }
        public string TypeName { get; set; }
        public SectionDto Section { get; set; }
        public LocationDto Location { get; set; }
        public string ScId { get; set; }
        public Dictionary<string, string> SharedParams { get; set; } = new Dictionary<string, string>();
    }

    // ========== Résultat d'application ==========
    public class ApplyResultDto
    {
        public int BarsUpdated { get; set; }
        public int NodesProcessed { get; set; }
        public int RebarsCreated { get; set; }
        public int ElementsCreated { get; set; }
        public List<string> Notes { get; set; } = new List<string>();
    }

    // ========== Enveloppe du protocole (exactement 4 clés, contrat Python strict) ==========
    public class PipeEnvelope
    {
        [JsonProperty("success")] public bool Success { get; set; }
        [JsonProperty("data")] public object Data { get; set; }
        [JsonProperty("error")] public string Error { get; set; }
        [JsonProperty("request_id")] public string RequestId { get; set; }

        public static string Ok(object data, string requestId) =>
            JsonConvert.SerializeObject(new PipeEnvelope { Success = true, Data = data, Error = "", RequestId = requestId ?? "" }, DtoJson.Settings);

        public static string Fail(string error, string requestId) =>
            JsonConvert.SerializeObject(new PipeEnvelope { Success = false, Data = null, Error = error ?? "", RequestId = requestId ?? "" }, DtoJson.Settings);
    }

    // ========== Helpers de sérialisation (camelCase pour les DTO) ==========
    public static class DtoJson
    {
        public static readonly JsonSerializerSettings Settings = new JsonSerializerSettings
        {
            ContractResolver = new CamelCasePropertyNamesContractResolver(),
            NullValueHandling = NullValueHandling.Ignore,
            Formatting = Formatting.None,
            ReferenceLoopHandling = ReferenceLoopHandling.Ignore,
            MissingMemberHandling = MissingMemberHandling.Ignore
        };

        public static string Serialize(object obj) => JsonConvert.SerializeObject(obj, Settings);
        public static T Deserialize<T>(string json) => JsonConvert.DeserializeObject<T>(json, Settings);
    }
}