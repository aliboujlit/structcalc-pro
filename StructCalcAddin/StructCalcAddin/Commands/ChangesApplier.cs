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

                    var barChanges = changes?.BarChanges ?? new List<BarChangeDto>();
                    foreach (var change in barChanges)
                    {
                        ApplyBarChange(doc, change, result);
                    }

                    var nodeChanges = changes?.NodeChanges ?? new List<NodeChangeDto>();
                    if (nodeChanges.Count > 0)
                    {
                        result.NodesProcessed = 0;
                        result.Notes.Add(
                            $"{nodeChanges.Count} changement(s) de n\u00E9ud/appui NON appliqu\u00E9(s) : " +
                            "l\u0027\u00E9criture des conditions aux limites exige un h\u00F4te et une r\u00E9f\u00E9rence exacts " +
                            "que le pivot ne fournit pas \u2014 aucune \u00E9criture \u00E0 l\u0027aveugle.");
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

            var familySymbol = FindOrCreateFamilySymbol(doc, creation.FamilyName, creation.TypeName, creation.Section, result);
            if (familySymbol == null)
            {
                result.Notes.Add($"Cr\u00E9ation {creation.ScId} : FamilySymbol \u0027{creation.FamilyName} : {creation.TypeName}\u0027 introuvable/cr\u00E9ation impossible \u2014 ignor\u00E9.");
                return;
            }

            FamilyInstance instance = null;

            try
            {
                if (creation.ElementType == "column")
                {
                    if (creation.Location?.Start == null || creation.Location?.End == null)
                    {
                        result.Notes.Add($"Cr\u00E9ation {creation.ScId} : Location Start/End manquante pour colonne.");
                        return;
                    }
                    var curve = Line.CreateBound(
                        creation.Location.Start.ToXyzFeet(),
                        creation.Location.End.ToXyzFeet()
                    );
                    instance = doc.Create.NewFamilyInstance(curve, familySymbol, StructuralType.Column);
                }
                else if (creation.ElementType == "beam")
                {
                    if (creation.Location?.Start == null || creation.Location?.End == null)
                    {
                        result.Notes.Add($"Cr\u00E9ation {creation.ScId} : Location Start/End manquante pour poutre.");
                        return;
                    }
                    var curve = Line.CreateBound(
                        creation.Location.Start.ToXyzFeet(),
                        creation.Location.End.ToXyzFeet()
                    );
                    instance = doc.Create.NewFamilyInstance(curve, familySymbol, StructuralType.Beam);
                }
                else if (creation.ElementType == "footing_isolated" || creation.ElementType == "footing_strip")
                {
                    if (creation.Location?.Point == null)
                    {
                        result.Notes.Add($"Cr\u00E9ation {creation.ScId} : Location Point manquante pour semelle.");
                        return;
                    }
                    var point = creation.Location.Point.ToXyzFeet();
                    instance = doc.Create.NewFamilyInstance(point, familySymbol, StructuralType.Footing);
                }
                else
                {
                    result.Notes.Add($"Type d\u0027\u00E9l\u00E9ment inconnu : {creation.ElementType} \u2014 ignor\u00E9.");
                    return;
                }

                if (instance != null)
                {
                    ApplySharedParams(instance, creation.SharedParams);
                    result.ElementsCreated++;
                    result.Notes.Add($"Cr\u00E9\u00E9 {creation.ElementType} {creation.ScId} (Type: {instance.Symbol.Name}) -> ElementId {instance.Id.Value}");
                }
            }
            catch (Exception ex)
            {
                result.Notes.Add($"\u00C9chec cr\u00E9ation {creation.ScId} ({creation.ElementType}) : {ex.Message}");
            }
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
                result.Notes.Add($"Él\u00E9ment Revit {change.ElementId} introuvable (supprim\u00E9 ou non de cadre) \u2014 ignor\u00E9.");
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
                    result.Notes.Add($"Él\u00E9ment {change.ElementId} d\u00E9j\u00E0 sur le type \u0027{typeName}\u0027 \u2014 inchang\u00E9.");
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

            var lc = beam.Location as LocationCurve;
            if (lc?.Curve == null)
            {
                result.Notes.Add($"Él\u00E9ment {beam.Id.Value} sans courbe \u2014 armature Ø{rb.DiameterMm} non cr\u00E9\u00E9e.");
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
                    $"Aucun type d\u0027armature Ø{rb.DiameterMm} mm dans le document \u2014 type par d\u00E9faut utilis\u00E9 (v\u00E9rifier sa taille).");
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
                        result.Notes.Add($"Courbe armature Ø{rb.DiameterMm} ignor\u00E9e : {ex.Message}");
                    }
                }
            }
            else
            {
                var lc = beam.Location as LocationCurve;
                if (lc?.Curve != null)
                {
                    var start = lc.Curve.GetEndPoint(0);
                    var end = lc.Curve.GetEndPoint(1);
                    curves.Add(Line.CreateBound(start, end));
                }
            }

            if (curves.Count == 0)
            {
                result.Notes.Add($"Armature Ø{rb.DiameterMm} : aucune courbe valide \u2014 ignor\u00E9e.");
                return 0;
            }

            List<RebarHookData> hooksData = new List<RebarHookData>();
            if (rb.Hooks != null && rb.Hooks.Count > 0)
            {
                foreach (var hookType in rb.Hooks)
                {
                    if (hookType == "Standard" || hookType == "90deg" || string.IsNullOrEmpty(hookType))
                        hooksData.Add(new RebarHookData(RebarHookType.Standard, 0));
                    else if (hookType == "90deg" || hookType == "NinetyDegrees")
                        hooksData.Add(new RebarHookData(RebarHookType.NinetyDegrees, 0));
                    else if (hookType == "135deg")
                        hooksData.Add(new RebarHookData(RebarHookType.OneThirtyFiveDegrees, 0));
                    else if (hookType == "180deg")
                        hooksData.Add(new RebarHookData(RebarHookType.OneEightyDegrees, 0));
                }
            }

            Curve firstCurve = curves[0];
            var curveDir = (firstCurve.GetEndPoint(1) - firstCurve.GetEndPoint(0)).Normalize();
            var normal = Math.Abs(curveDir.DotProduct(XYZ.BasisZ)) > 0.9 ? XYZ.BasisY : XYZ.BasisZ;

            if (rb.StirrupSpacing != null && rb.Layer == "Stirrups")
            {
                result.Notes.Add($"StirrupSpacing d\u00E9tect\u00E9 (Zone={rb.StirrupSpacing.Zone}mm, Field={rb.StirrupSpacing.Field}mm, Attente={rb.StirrupSpacing.AttenteLength}mm) \u2014 r\u00E9partition multiple non impl\u00E9ment\u00E9e, un seul cadre cr\u00E9\u00E9.");
            }

            try
            {
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
                    result.Notes.Add($"Cr\u00E9ation d\u0027armature Ø{rb.DiameterMm} refus\u00E9e par Revit (h\u00F4te ou g\u00E9om\u00E9trie) \u2014 ignor\u00E9e.");
                    return 0;
                }

                if (rb.Hooks != null && rb.Hooks.Count > 0)
                {
                    var hooksData = new List<RebarHookData>();
                    foreach (var hookType in rb.Hooks)
                    {
                        if (hookType == "Standard" || hookType == "90deg" || string.IsNullOrEmpty(hookType))
                            hooksData.Add(new RebarHookData(RebarHookType.Standard, 0));
                        else if (hookType == "90deg" || hookType == "NinetyDegrees")
                            hooksData.Add(new RebarHookData(RebarHookType.NinetyDegrees, 0));
                        else if (hookType == "135deg")
                            hooksData.Add(new RebarHookData(RebarHookType.OneThirtyFiveDegrees, 0));
                        else if (hookType == "180deg")
                            hooksData.Add(new RebarHookData(RebarHookType.OneEightyDegrees, 0));
                    }

                    try
                    {
                        for (int i = 0; i < hooksData.Count && i < 2; i++)
                        {
                            rebar.SetHookTypeId(i, hooksData[i].HookTypeId);
                        }
                    }
                    catch { }
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
                        $"Armature Ø{rb.DiameterMm} cr\u00E9\u00E9e en 1 barre (Count={rb.Count} non appliqu\u00E9 : " +
                        "r\u00E9partition lat\u00E9rale impossible sans enrobage \u2014 donn\u00E9e manquante).");
                result.Notes.Add(
                    $"Armature Ø{rb.DiameterMm} plac\u00E9e \u00E0 l\u0027AXE de la poutre : enrobage non fourni \u2014 positionnement transversal \u00E0 ajuster manuellement.");

                return 1;
            }
            catch (Exception ex)
            {
                result.Notes.Add($"Armature Ø{rb.DiameterMm} : \u00E9chec Rebar.CreateFromCurves ({ex.Message}).");
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
                result.Notes.Add($"Aucun type de poutre disponible pour cr\u00E9er \u0027{name}\u0027 \u2014 section non appliqu\u00E9e.");
                return null;
            }

            var created = source.Duplicate(name) as FamilySymbol;
            if (created == null)
            {
                result.Notes.Add($"Duplication du type \u0027{name}\u0027 \u00E9chou\u00E9e \u2014 section non appliqu\u00E9e.");
                return null;
            }
            result.Notes.Add($"Type \u0027{name}\u0027 cr\u00E9\u00E9 par duplication de \u0027{source.Name}\u0027.");
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
                    $"Type \u0027{symbol.Name}\u0027 : aucun param\u00E8tre de dimension modifiable (b/Width/h/Height/Diameter) \u2014 dimensions non appliqu\u00E9es.");
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
