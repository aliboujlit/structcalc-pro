using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using StructCalcAddin.Models;

namespace StructCalcAddin.Commands
{
    /// <summary>
    /// Application des changements reçus du noyau Python au modèle Revit.
    /// UNE seule Transaction englobante (les transactions imbriquées sont
    /// interdites en Revit : FindOrCreateFamilySymbol s'exécute DANS la
    /// transaction appelante).

    /// Écritures implémentées : type de section (FamilySymbol) sur barres.
    /// Écritures refusées explicitement (motif dans les notes) : armatures
    /// complexes (enrobage non fourni = donnée manquante, jamais inventée),
    /// appuis (conditions aux limites Revit exigent hôte + référence exacts).
    /// </summary>
    public static class ChangesApplier
    {
        /// <summary>Tolérance d'appariement de diamètre d'armature : 0,5 mm.</summary>
        private const double DiameterToleranceFt = 0.5 / 304.8;

        public static ApplyResultDto Apply(Document doc, ApplyChangesRequest changes)
        {
            var result = new ApplyResultDto
            {
                BarsUpdated = 0,
                NodesProcessed = 0,
                RebarsCreated = 0,
                Notes = new List<string>()
            };

            var barChanges = changes?.BarChanges ?? new List<BarChangeDto>();
            var nodeChanges = changes?.NodeChanges ?? new List<NodeChangeDto>();

            if (barChanges.Count == 0 && nodeChanges.Count == 0)
            {
                result.Notes.Add("Aucun changement fourni (listes vides) — rien appliqué.");
                return result;
            }

            using (var tx = new Transaction(doc, "STRUCTCALC : appliquer les changements"))
            {
                tx.Start();
                try
                {
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

        // ------------------------------------------------------------------

        private static void ApplyBarChange(Document doc, BarChangeDto change, ApplyResultDto result)
        {
            if (change == null) return;

            var elem = doc.GetElement(new ElementId(change.ElementId)) as FamilyInstance;
            if (elem == null)
            {
                result.Notes.Add($"Élément Revit {change.ElementId} introuvable (supprimé ou non de cadre) — ignoré.");
                return;
            }

            // --- Section ---
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

            // --- Armatures ---
            var rebars = change.Rebars ?? new List<RebarDto>();
            foreach (var rb in rebars)
            {
                result.RebarsCreated += ApplyRebar(doc, elem, rb, result);
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

        /// <summary>
        /// Trouve un FamilySymbol de poutre par nom ; s'il n'existe pas, le
        /// duplique depuis un type disponible et applique les dimensions
        /// (mètres -> pieds). Aucune transaction imbriquée.
        /// </summary>
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

            var created = source.Duplicate(name) as FamilySymbol;   // ElementType.Duplicate(String)
            if (created == null)
            {
                result.Notes.Add($"Duplication du type '{name}' échouée — section non appliquée.");
                return null;
            }
            result.Notes.Add($"Type '{name}' créé par duplication de '{source.Name}'.");
            ApplySectionParams(created, section, result);
            return created;
        }

        /// <summary>Applique b/h/diamètre (mètres) aux paramètres du type (pieds).</summary>
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

        /// <summary>
        /// Armature : barre droite le long de l'axe de la poutre (API réelle
        /// Rebar.CreateFromCurves, signature 2027 à 9 paramètres). L'enrobage
        /// et la répartition latérale ne sont PAS fournis par le pivot :
        /// le positionnement transversal reste donc à ajuster manuellement
        /// (dit explicitement dans les notes, jamais simulé).
        /// </summary>
        private static int ApplyRebar(Document doc, FamilyInstance beam, RebarDto rb,
            ApplyResultDto result)
        {
            if (rb == null || rb.DiameterMm <= 0) return 0;

            var lc = beam.Location as LocationCurve;
            if (lc?.Curve == null)
            {
                result.Notes.Add($"Élément {beam.Id.Value} sans courbe — armature Ø{rb.DiameterMm} non créée.");
                return 0;
            }

            // Type d'armature existant au diamètre demandé (BarNominalDiameter, pieds)
            double targetFt = rb.DiameterMm / XchgUnits.FtToMm;
            var barType = new FilteredElementCollector(doc)
                .OfClass(typeof(RebarBarType))
                .Cast<RebarBarType>()
                .FirstOrDefault(rt => Math.Abs(rt.BarNominalDiameter - targetFt) <= DiameterToleranceFt);

            if (barType == null)
            {
                barType = RebarBarType.Create(doc);   // type par défaut du document
                result.Notes.Add(
                    $"Aucun type d'armature Ø{rb.DiameterMm} mm dans le document — type par défaut utilisé (vérifier sa taille).");
            }

            var curve = lc.Curve;
            var start = curve.GetEndPoint(0);
            var end = curve.GetEndPoint(1);
            var dir = (end - start).Normalize();

            // Plan normal à l'axe de la barre
            var normal = Math.Abs(dir.DotProduct(XYZ.BasisZ)) > 0.9 ? XYZ.BasisY : XYZ.BasisZ;
            var barCurve = Line.CreateBound(start, end);

            try
            {
                var rebar = Rebar.CreateFromCurves(
                    doc,
                    RebarStyle.Standard,
                    barType,
                    beam,                       // hôte
                    normal,
                    new List<Curve> { barCurve },
                    default(BarTerminationsData),
                    true,                       // useExistingShapeIfPossible
                    true);                      // createNewShape

                if (rebar == null)
                {
                    result.Notes.Add($"Création d'armature Ø{rb.DiameterMm} refusée par Revit (hôte ou géométrie) — ignorée.");
                    return 0;
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
    }
}
