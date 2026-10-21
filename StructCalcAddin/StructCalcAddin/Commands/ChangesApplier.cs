using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using StructCalcAddin.Models;

namespace StructCalcAddin.Commands
{
    public static class ChangesApplier
    {
        private const double DiameterToleranceFt = 0.5 / 304.8;

        public static ApplyResultDto Apply(Document doc, ApplyChangesRequest changes)
        {
            var result = new ApplyResultDto
            {
                BarsUpdated = 0,
                NodesProcessed = 0,
                RebarsCreated = 0,
                ElementsCreated = 0,
                Notes = new List<string>()
            };

            var creations = changes?.ElementCreations ?? new List<ElementCreationDto>();
            var barChanges = changes?.BarChanges ?? new List<BarChangeDto>();
            var nodeChanges = changes?.NodeChanges ?? new List<NodeChangeDto>();

            if (creations.Count == 0 && barChanges.Count == 0 && nodeChanges.Count == 0)
            {
                result.Notes.Add("Aucun changement fourni (listes vides) — rien appliqué.");
                return result;
            }

            using (var tx = new Transaction(doc, "STRUCTCALC : appliquer les changements"))
            {
                tx.Start();
                try
                {
                    foreach (var creation in creations)
                    {
                        CreateFamilyInstance(doc, creation, result);
                    }

                    foreach (var change in barChanges)
                    {
                        ApplyBarChange(doc, change, result);
                    }

                    if (nodeChanges.Count > 0)
                    {
                        result.NodesProcessed = 0;
                        result.Notes.Add(
                            $"{nodeChanges.Count} changement(s) de nœud/appui NON appliqué(s) : " +
                            "l'écriture des conditions aux limites exige un hôte et une référence exacts " +
                            "que le pivot ne fournit pas — aucune écriture à l'aveugle.");
                    }

                    tx.Commit();
                }
                catch
                {
                    tx.RollBack();
                    throw;
                }
            }

            return result;
        }

        private static void CreateFamilyInstance(Document doc, ElementCreationDto creation, ApplyResultDto result)
        {
            if (creation == null) return;

            var familySymbol = FindOrCreateFamilySymbol(doc, creation.TypeName, creation.Section, result);
            if (familySymbol == null)
            {
                result.Notes.Add($"Création {creation.ScId} : FamilySymbol '{creation.FamilyName} : {creation.TypeName}' introuvable/création impossible — ignoré.");
                return;
            }

            FamilyInstance instance = null;

            try
            {
                var level = GetDefaultLevel(doc);
                if (level == null)
                {
                    result.Notes.Add($"Création {creation.ScId} : aucun Level trouvé dans le document.");
                    return;
                }

                if (creation.ElementType == "column")
                {
                    if (creation.Location?.Start == null || creation.Location?.End == null)
                    {
                        result.Notes.Add($"Création {creation.ScId} : Location Start/End manquante pour colonne.");
                        return;
                    }
                    var curve = Line.CreateBound(
                        creation.Location.Start.ToXyzFeet(),
                        creation.Location.End.ToXyzFeet()
                    );
                    instance = doc.Create.NewFamilyInstance(curve, familySymbol, level, StructuralType.Column);
                }
                else if (creation.ElementType == "beam")
                {
                    if (creation.Location?.Start == null || creation.Location?.End == null)
                    {
                        result.Notes.Add($"Création {creation.ScId} : Location Start/End manquante pour poutre.");
                        return;
                    }
                    var curve = Line.CreateBound(
                        creation.Location.Start.ToXyzFeet(),
                        creation.Location.End.ToXyzFeet()
                    );
                    instance = doc.Create.NewFamilyInstance(curve, familySymbol, level, StructuralType.Beam);
                }
                else if (creation.ElementType == "footing_isolated" || creation.ElementType == "footing_strip")
                {
                    if (creation.Location?.Point == null)
                    {
                        result.Notes.Add($"Création {creation.ScId} : Location Point manquante pour semelle.");
                        return;
                    }
                    var point = creation.Location.Point.ToXyzFeet();
                    instance = doc.Create.NewFamilyInstance(point, familySymbol, level, StructuralType.Footing);
                }
                else
                {
                    result.Notes.Add($"Type d'élément inconnu : {creation.ElementType} — ignoré.");
                    return;
                }

                if (instance != null)
                {
                    ApplySharedParams(instance, creation.SharedParams);
                    result.ElementsCreated++;
                    result.Notes.Add($"Créé {creation.ElementType} {creation.ScId} (Type: {instance.Symbol.Name}) -> ElementId {instance.Id.Value}");
                }
            }
            catch (Exception ex)
            {
                result.Notes.Add($"Échec création {creation.ScId} ({creation.ElementType}) : {ex.Message}");
            }
        }

        private static Level GetDefaultLevel(Document doc)
        {
            return new FilteredElementCollector(doc)
                .OfClass(typeof(Level))
                .Cast<Level>()
                .OrderBy(l => l.Elevation)
                .FirstOrDefault();
        }

        private static void ApplySharedParams(Element elem, Dictionary<string, string> sharedParams)
        {
            if (sharedParams == null) return;
            foreach (var kvp in sharedParams)
            {
                var param = elem.LookupParameter(kvp.Key);
                if (param != null && !param.IsReadOnly)
                {
                    try
                    {
                        if (param.StorageType == StorageType.String)
                            param.Set(kvp.Value);
                        else if (param.StorageType == StorageType.Double && double.TryParse(kvp.Value, out double d))
                            param.Set(d);
                        else if (param.StorageType == StorageType.Integer && int.TryParse(kvp.Value, out int i))
                            param.Set(i);
                    }
                    catch { }
                }
            }
        }

        private static void ApplyBarChange(Document doc, BarChangeDto change, ApplyResultDto result)
        {
            if (change == null) return;

            var elem = doc.GetElement(new ElementId(change.ElementId)) as FamilyInstance;
            if (elem == null)
            {
                result.Notes.Add($"Élément Revit {change.ElementId} introuvable (supprimé ou non de cadre) — ignoré.");
                return;
            }

            bool hasSection = (change.NewSection != null &&
                               (change.NewSection.Width.HasValue || change.NewSection.Height.HasValue
                                || change.NewSection.Diameter.HasValue))
                              || !string.IsNullOrEmpty(change.NewSectionName);

            if (hasSection)
            {
                string typeName = string.IsNullOrEmpty(change.NewSectionName)
                    ? BuildFallbackName(change.NewSection)
                    : change.NewSectionName;

                var newType = FindOrCreateFamilySymbol(doc, typeName, change.NewSection, result);
                if (newType != null && elem.Symbol.Id != newType.Id)
                {
                    elem.Symbol = newType;
                    result.BarsUpdated++;
                }
                else if (newType != null)
                {
                    result.Notes.Add($"Élément {change.ElementId} déjà sur le type '{typeName}' — inchangé.");
                }
            }

            var rebars = change.Rebars ?? new List<RebarDto>();
            foreach (var rb in rebars)
            {
                result.RebarsCreated += ApplyRebar(doc, elem, rb, result);
            }
        }

        private static int ApplyRebar(Document doc, FamilyInstance beam, RebarDto rb,
            ApplyResultDto result)
        {
            if (rb == null || rb.DiameterMm <= 0) return 0;

            var locCurve = beam.Location as LocationCurve;
            if (locCurve?.Curve == null)
            {
                result.Notes.Add($"Élément {beam.Id.Value} sans courbe — armature Ø{rb.DiameterMm} non créée.");
                return 0;
            }

            double targetFt = rb.DiameterMm / XchgUnits.FtToMm;
            var barType = new FilteredElementCollector(doc)
                .OfClass(typeof(RebarBarType))
                .Cast<RebarBarType>()
                .FirstOrDefault(rt => Math.Abs(rt.BarNominalDiameter - targetFt) <= DiameterToleranceFt);

            if (barType == null)
            {
                barType = RebarBarType.Create(doc);
                result.Notes.Add(
                    $"Aucun type d'armature Ø{rb.DiameterMm} mm dans le document — type par défaut utilisé (vérifier sa taille).");
            }

            List<Curve> curves = new List<Curve>();
            if (rb.Curves != null && rb.Curves.Count > 0)
            {
                foreach (var c in rb.Curves)
                {
                    try
                    {
                        if (c.IsArc && c.Center != null)
                        {
                            var arc = Arc.Create(c.Start.ToXyzFeet(), c.End.ToXyzFeet(), c.Center.ToXyzFeet());
                            curves.Add(arc);
                        }
                        else
                        {
                            var line = Line.CreateBound(c.Start.ToXyzFeet(), c.End.ToXyzFeet());
                            curves.Add(line);
                        }
                    }
                    catch (Exception ex)
                    {
                        result.Notes.Add($"Courbe armature Ø{rb.DiameterMm} ignorée : {ex.Message}");
                    }
                }
            }
            else
            {
                if (locCurve?.Curve != null)
                {
                    var start = locCurve.Curve.GetEndPoint(0);
                    var end = locCurve.Curve.GetEndPoint(1);
                    curves.Add(Line.CreateBound(start, end));
                }
            }

            if (curves.Count == 0)
            {
                result.Notes.Add($"Armature Ø{rb.DiameterMm} : aucune courbe valide — ignorée.");
                return 0;
            }

            if (rb.StirrupSpacing != null && rb.Layer == "Stirrups")
            {
                result.Notes.Add($"StirrupSpacing détecté (Zone={rb.StirrupSpacing.Zone}mm, Field={rb.StirrupSpacing.Field}mm, Attente={rb.StirrupSpacing.AttenteLength}mm) — répartition multiple non implémentée, un seul cadre créé.");
            }

            try
            {
                Curve firstCurve = curves[0];
                var curveDir = (firstCurve.GetEndPoint(1) - firstCurve.GetEndPoint(0)).Normalize();
                var normal = Math.Abs(curveDir.DotProduct(XYZ.BasisZ)) > 0.9 ? XYZ.BasisY : XYZ.BasisZ;

                var rebar = Rebar.CreateFromCurves(
                    doc,
                    RebarStyle.Standard,
                    barType,
                    beam,
                    normal,
                    curves,
                    default(BarTerminationsData),
                    true,
                    true);

                if (rebar == null)
                {
                    result.Notes.Add($"Création d'armature Ø{rb.DiameterMm} refusée par Revit (hôte ou géométrie) — ignorée.");
                    return 0;
                }

                if (rb.SharedParams != null && rb.SharedParams.Count > 0)
                {
                    foreach (var kvp in rb.SharedParams)
                    {
                        var param = rebar.LookupParameter(kvp.Key);
                        if (param != null && !param.IsReadOnly)
                        {
                            try
                            {
                                if (param.StorageType == StorageType.String)
                                    param.Set(kvp.Value);
                                else if (param.StorageType == StorageType.Double && double.TryParse(kvp.Value, out double d))
                                    param.Set(d);
                                else if (param.StorageType == StorageType.Integer && int.TryParse(kvp.Value, out int i))
                                    param.Set(i);
                            }
                            catch { }
                        }
                    }
                }

                if (rb.Count > 1)
                    result.Notes.Add(
                        $"Armature Ø{rb.DiameterMm} créée en 1 barre (Count={rb.Count} non appliqué : " +
                        "répartition latérale impossible sans enrobage — donnée manquante).");
                result.Notes.Add(
                    $"Armature Ø{rb.DiameterMm} placée à l'AXE de la poutre : enrobage non fourni — positionnement transversal à ajuster manuellement.");

                return 1;
            }
            catch (Exception ex)
            {
                result.Notes.Add($"Armature Ø{rb.DiameterMm} : échec Rebar.CreateFromCurves ({ex.Message}).");
                return 0;
            }
        }

        private static string BuildFallbackName(SectionDto section)
        {
            if (section == null) return "Section STRUCTCALC";
            if (section.Diameter.HasValue && section.Diameter.Value > 0)
                return $"SC Ø{Math.Round(section.Diameter.Value * 100)}";
            if (section.Width.HasValue && section.Height.HasValue)
                return $"SC {Math.Round(section.Width.Value * 100)}x{Math.Round(section.Height.Value * 100)}";
            return "Section STRUCTCALC";
        }

        private static FamilySymbol FindOrCreateFamilySymbol(Document doc, string name,
            SectionDto section, ApplyResultDto result)
        {
            var framingSymbols = new FilteredElementCollector(doc)
                .OfClass(typeof(FamilySymbol))
                .OfCategory(BuiltInCategory.OST_StructuralFraming)
                .Cast<FamilySymbol>()
                .ToList();

            var existing = framingSymbols.FirstOrDefault(fs => fs.Name == name);
            if (existing != null)
            {
                ApplySectionParams(existing, section, result);
                return existing;
            }

            var source = framingSymbols.FirstOrDefault();
            if (source == null)
            {
                result.Notes.Add($"Aucun type de poutre disponible pour créer '{name}' — section non appliquée.");
                return null;
            }

            var created = source.Duplicate(name) as FamilySymbol;
            if (created == null)
            {
                result.Notes.Add($"Duplication du type '{name}' échouée — section non appliquée.");
                return null;
            }
            result.Notes.Add($"Type '{name}' créé par duplication de '{source.Name}'.");
            ApplySectionParams(created, section, result);
            return created;
        }

        private static void ApplySectionParams(FamilySymbol symbol, SectionDto section,
            ApplyResultDto result)
        {
            if (section == null) return;

            bool any = false;
            any |= TrySetLength(symbol, section.Width, "b", "Width", "Largeur");
            any |= TrySetLength(symbol, section.Height, "h", "Height", "Hauteur");
            any |= TrySetLength(symbol, section.Diameter, "Diameter", "Ø");

            if (!any && (section.Width.HasValue || section.Height.HasValue || section.Diameter.HasValue))
                result.Notes.Add(
                    $"Type '{symbol.Name}' : aucun paramètre de dimension modifiable (b/Width/h/Height/Diameter) — dimensions non appliquées.");
        }

        private static bool TrySetLength(Element elem, double? valueMeters, params string[] names)
        {
            if (!valueMeters.HasValue || valueMeters.Value <= 0) return false;
            double ft = valueMeters.Value * XchgUnits.MToFt;

            foreach (var n in names)
            {
                var p = elem.LookupParameter(n);
                if (p != null && !p.IsReadOnly && p.StorageType == StorageType.Double)
                {
                    p.Set(ft);
                    return true;
                }
            }
            return false;
        }
    }
}