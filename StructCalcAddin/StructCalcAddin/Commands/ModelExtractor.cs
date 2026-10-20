using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using StructCalcAddin.Models;

namespace StructCalcAddin.Commands
{
    /// <summary>
    /// Extraction du modèle structural Revit vers le DTO d'échange.
    /// Utilisé à la fois par la commande ruban "Lire modèle" (thread Revit
    /// direct) et par le RevitApiDispatcher (via le Named Pipe).

    /// API 2027 réelles (vérifiées) :
    ///   - BoundaryConditions (Element) : Point (XYZ), Preset, HostElementId ;
    ///     fixités = paramètres BOUNDARY_{X,Y,Z}_{TRANSLATION,ROTATION}_FIXED
    ///     (1 = fixé, lu par get_Parameter ; paramètre absent = inconnu).
    ///   - LoadCase : Number, NatureId -> LoadNature.Name.
    ///   - ElementId.Value (long) — IntegerValue n'existe plus en 2027.
    ///   - Material.GetMaterialPropertyByName N'EXISTE PAS : les propriétés
    ///     physiques restent null (inconnues), JAMAIS 0-présenté-comme-donnée.
    /// Unités : Revit = pieds -> DTO en mètres (m, m², m⁴).
    /// </summary>
    public static class ModelExtractor
    {
        /// <summary>Tolérance d'appariement nœud/appui : 5 mm (en pieds).</summary>
        private const double MatchToleranceFt = 0.0164; // 5 mm

        public static StructuralModelDto Extract(Document doc)
        {
            var model = new StructuralModelDto
            {
                ProjectName = doc.Title,
                RevitVersion = doc.Application.VersionName,
                ExportTime = DateTime.UtcNow,
                Nodes = new List<NodeDto>(),
                Bars = new List<BarDto>(),
                LoadCases = new List<LoadCaseDto>(),
                Notes = new List<string>()
            };

            // Index nœuds : position arrondie (1 mm) -> Id synthétique
            var nodeIndex = new Dictionary<string, long>();
            long nextNodeId = 1;

            // --- Barres (cadres structuraux : poutres et poteaux) ---
            var framing = new FilteredElementCollector(doc)
                .OfClass(typeof(FamilyInstance))
                .OfCategory(BuiltInCategory.OST_StructuralFraming)
                .Cast<FamilyInstance>()
                .Where(fi => fi.StructuralType == StructuralType.Beam
                          || fi.StructuralType == StructuralType.Column)
                .ToList();

            foreach (var fi in framing)
            {
                var lc = fi.Location as LocationCurve;
                if (lc?.Curve == null) continue;   // pas de courbe -> pas de barre (rien d'inventé)

                var curve = lc.Curve;
                var start = curve.GetEndPoint(0);
                var end = curve.GetEndPoint(1);

                long startId = GetOrCreateNodeId(start, ref nextNodeId, nodeIndex, model);
                long endId = GetOrCreateNodeId(end, ref nextNodeId, nodeIndex, model);

                var symbol = fi.Symbol;   // FamilySymbol direct
                model.Bars.Add(new BarDto
                {
                    Id = fi.Id.Value,              // ElementId long : identifiant d'écriture
                    StartNodeId = startId,
                    EndNodeId = endId,
                    Name = SafeName(fi),
                    StructuralType = fi.StructuralType.ToString(),  // "Beam" / "Column"
                    Section = ExtractSection(symbol),
                    Material = ExtractMaterial(fi),
                    Loads = new List<LoadDto>()    // charges non extraites (note ci-dessous)
                });
            }

            // --- Appuis (BoundaryConditions) ---
            int supportsSeen = 0;
            var supports = new FilteredElementCollector(doc)
                .OfClass(typeof(BoundaryConditions))
                .Cast<BoundaryConditions>()
                .ToList();

            foreach (var bc in supports)
            {
                var point = bc.Point;    // XYZ (null si appui linéaire/aire)
                if (point == null) continue;

                supportsSeen++;
                long nid = GetOrCreateNodeId(point, ref nextNodeId, nodeIndex, model);
                var node = model.Nodes.FirstOrDefault(n => n.Id == nid);
                if (node == null) continue;

                node.IsSupport = true;
                node.Support = ExtractSupport(doc, bc);
            }

            // --- Cas de charge ---
            var loadCases = new FilteredElementCollector(doc)
                .OfClass(typeof(LoadCase))
                .Cast<LoadCase>()
                .ToList();

            foreach (var lc2 in loadCases)
            {
                string nature = null;
                try
                {
                    var natElem = doc.GetElement(lc2.NatureId) as LoadNature;
                    nature = natElem?.Name;
                }
                catch { /* nature illisible -> laissée absente */ }

                model.LoadCases.Add(new LoadCaseDto
                {
                    Name = SafeName(lc2),
                    Type = nature,               // null si non résoluble (jamais deviné)
                    Number = lc2.Number
                });
            }

            // --- Notes de périmètre : ce qui n'est PAS extrait est dit explicitement ---
            if (framing.Count == 0)
                model.Notes.Add("Aucun élément de cadre structural (poutre/poteau) trouvé dans le document.");
            if (supportsSeen > 0)
                model.Notes.Add($"{supportsSeen} appui(x) ponctuel(s) importé(s) : fixités lues paramètre par paramètre (1 = fixé) ; paramètre absent = inconnu.");
            model.Notes.Add("Sections : largeur/hauteur/diamètre lus si le type les expose (b/Width, h/Height, Diameter) — pieds convertis en mètres ; inerties non lues = absentes.");
            model.Notes.Add("Matériaux : nom et classe seulement — Revit 2027 n'expose aucune API vérifiée de propriété physique (Fc/Fy/E) : valeur absente = inconnue, jamais 0.");
            model.Notes.Add("Charges d'éléments et appuis non ponctuels (linéaires/aires) non extraits dans cette version.");
            model.Notes.Add("Le champ structuralType (Beam/Column) est transmis : les poteaux sont importés comme poteaux dans le pivot.");

            return model;
        }

        // ------------------------------------------------------------------

        private static string SafeName(Element e)
        {
            try { return e.Name; }
            catch { return ""; }   // Name peut lever pour certains éléments
        }

        private static long GetOrCreateNodeId(XYZ point, ref long nextId,
            Dictionary<string, long> index, StructuralModelDto model)
        {
            // Clé d'appariement : position arrondie au mm (pieds)
            string key = $"{Math.Round(point.X, 3):F3}|{Math.Round(point.Y, 3):F3}|{Math.Round(point.Z, 3):F3}";
            if (index.TryGetValue(key, out long existing)) return existing;

            long id = nextId++;
            index[key] = id;
            model.Nodes.Add(new NodeDto
            {
                Id = id,
                Position = XyzDto.FromXyzFeet(point),
                Name = $"N{id}",
                IsSupport = null    // inconnu tant qu'aucun appui n'y est attaché
            });
            return id;
        }

        private static SectionDto ExtractSection(FamilySymbol symbol)
        {
            if (symbol == null) return null;

            double? width = ReadLengthParamFt(symbol, "b", "Width", "Largeur");
            double? height = ReadLengthParamFt(symbol, "h", "Height", "Hauteur");
            double? dia = ReadLengthParamFt(symbol, "Diameter", "Ø");

            // Aires/inerties : lues seulement si le type les expose
            double? areaFt2 = ReadDoubleParam(symbol, "Area", "A");
            double? iyFt4 = ReadDoubleParam(symbol, "Iy");
            double? izFt4 = ReadDoubleParam(symbol, "Iz");
            double? jFt4 = ReadDoubleParam(symbol, "J");

            string shape = null;
            if (dia.HasValue && dia.Value > 0) shape = "Circular";
            else if (width.HasValue && height.HasValue && width.Value > 0 && height.Value > 0)
                shape = "Rectangular";
            // sinon : forme inconnue -> null (jamais devinée d'après le nom de famille)

            return new SectionDto
            {
                Name = symbol.FamilyName + " : " + symbol.Name,
                Shape = shape,
                Width = XchgUnits.FtToMeters(width),
                Height = XchgUnits.FtToMeters(height),
                Diameter = XchgUnits.FtToMeters(dia),
                Area = XchgUnits.Ft2ToSquareMeters(areaFt2),
                Iy = XchgUnits.Ft4ToMeters4(iyFt4),
                Iz = XchgUnits.Ft4ToMeters4(izFt4),
                J = XchgUnits.Ft4ToMeters4(jFt4)
            };
        }

        private static double? ReadLengthParamFt(Element e, params string[] names)
        {
            foreach (var n in names)
            {
                var p = e.LookupParameter(n);
                if (p != null && !p.IsReadOnly && p.StorageType == StorageType.Double)
                {
                    double v = p.AsDouble();     // pieds (unité interne Revit)
                    if (v > 0) return v;
                }
            }
            return null;
        }

        private static double? ReadDoubleParam(Element e, params string[] names)
        {
            foreach (var n in names)
            {
                var p = e.LookupParameter(n);
                if (p != null && !p.IsReadOnly && p.StorageType == StorageType.Double)
                    return p.AsDouble();
            }
            return null;
        }

        private static MaterialDto ExtractMaterial(FamilyInstance fi)
        {
            var dto = new MaterialDto
            {
                Name = null,
                Type = fi.StructuralMaterialType.ToString()   // Steel/Concrete/Wood/...
            };
            try
            {
                var matId = fi.GetMaterialIds(false).FirstOrDefault();
                if (matId != null && matId != ElementId.InvalidElementId)
                {
                    var mat = fi.Document.GetElement(matId) as Material;
                    if (mat != null)
                    {
                        dto.Name = mat.Name;
                        try { dto.Type = mat.MaterialClass; } catch { /* classe inexistante -> type par défaut */ }
                    }
                }
            }
            catch { /* matériau non résolu -> nom/classe seuls */ }

            // Fc / Fy / E / Nu / Rho : laissés null (API inexistante en 2027).
            return dto;
        }

        private static SupportDto ExtractSupport(Document doc, BoundaryConditions bc)
        {
            var dto = new SupportDto
            {
                Preset = bc.Preset.ToString()   // Fixed / Pinned / Roller / User
            };

            dto.FixedX = ReadFixed(doc, bc, BuiltInParameter.BOUNDARY_X_TRANSLATION_FIXED);
            dto.FixedY = ReadFixed(doc, bc, BuiltInParameter.BOUNDARY_Y_TRANSLATION_FIXED);
            dto.FixedZ = ReadFixed(doc, bc, BuiltInParameter.BOUNDARY_Z_TRANSLATION_FIXED);
            dto.FixedRx = ReadFixed(doc, bc, BuiltInParameter.BOUNDARY_X_ROTATION_FIXED);
            dto.FixedRy = ReadFixed(doc, bc, BuiltInParameter.BOUNDARY_Y_ROTATION_FIXED);
            dto.FixedRz = ReadFixed(doc, bc, BuiltInParameter.BOUNDARY_Z_ROTATION_FIXED);

            return dto;
        }

        /// <summary>Lit un drapeau de fixation : 1 = fixé, 0 = libre, paramètre absent = null.</summary>
        private static bool? ReadFixed(Document doc, BoundaryConditions bc, BuiltInParameter bip)
        {
            try
            {
                var p = bc.get_Parameter(bip);
                if (p == null || p.StorageType != StorageType.Integer) return null;
                return p.AsInteger() == 1;
            }
            catch
            {
                return null;
            }
        }
    }
}
