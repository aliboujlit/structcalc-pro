using System;
using System.IO;
using System.Linq;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using StructCalcAddin.Models;

namespace StructCalcAddin.Commands
{
    /// <summary>
    /// Commande ruban "Écrire modèle" : applique les changements reçus du
    /// noyau Python. Deux sources, dans l'ordre :
    ///   1. fichier StructCalc_Changes_*.json récent (chemin de secours) ;
    ///   2. sinon : message explicite — les changements arrivent par le
    ///      Named Pipe via APPLY_CHANGES (aucun appel sortant ici : sur ce
    ///      thread, appeler le dispatcher provoquerait un interblocage).
    /// L'application se fait via <see cref="ChangesApplier"/> (transaction unique).
    /// </summary>
    [Transaction(TransactionMode.Manual)]
    public class WriteModelCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            var doc = commandData.Application?.ActiveUIDocument?.Document;
            if (doc == null)
            {
                message = "Aucun document Revit actif.";
                return Result.Failed;
            }

            try
            {
                string changesJson = null;

                // 1. Chemin de secours : fichier de changements récent
                var files = Directory.GetFiles(
                    Environment.GetFolderPath(Environment.SpecialFolder.Desktop),
                    "StructCalc_Changes_*.json");
                if (files.Length > 0)
                {
                    Array.Sort(files);
                    changesJson = File.ReadAllText(files[files.Length - 1]);
                }

                if (string.IsNullOrWhiteSpace(changesJson))
                {
                    bool pipeUp = StructCalcAddin._pipeServer?.IsListening == true;
                    TaskDialog.Show("STRUCTCALC - Écriture",
                        "Aucun changement local à appliquer (fichier StructCalc_Changes_*.json absent).\n\n" +
                        (pipeUp
                            ? "Le pipe structcalc_revit est actif : envoyez les changements depuis STRUCTCALC PRO (write_model) — ils seront appliqués automatiquement."
                            : "Le pipe structcalc_revit est inactif : redémarrez l'add-in ou relancez STRUCTCALC PRO."));
                    return Result.Succeeded;
                }

                ApplyChangesRequest changes;
                try
                {
                    changes = DtoJson.Deserialize<ApplyChangesRequest>(changesJson);
                }
                catch (Exception ex)
                {
                    message = "Fichier de changements illisible : " + ex.Message;
                    return Result.Failed;
                }

                if (changes == null ||
                    ((changes.BarChanges == null || changes.BarChanges.Count == 0) &&
                     (changes.NodeChanges == null || changes.NodeChanges.Count == 0)))
                {
                    TaskDialog.Show("STRUCTCALC - Écriture", "Aucun changement valide à appliquer (listes vides).");
                    return Result.Succeeded;
                }

                ApplyResultDto result = ChangesApplier.Apply(doc, changes);

                var dialog = new TaskDialog("STRUCTCALC - Écriture")
                {
                    MainInstruction = "Changements STRUCTCALC appliqués",
                    MainContent =
                        $"Barres modifiées : {result.BarsUpdated}\n" +
                        $"Nœuds/appuis appliqués : {result.NodesProcessed}\n" +
                        $"Armatures créées : {result.RebarsCreated}",
                    CommonButtons = TaskDialogCommonButtons.Close,
                    DefaultButton = TaskDialogResult.Close
                };
                if (result.Notes != null && result.Notes.Count > 0)
                    dialog.ExpandedContent = "Détail et limites :\n- " + string.Join("\n- ", result.Notes);
                dialog.Show();

                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = ex.ToString();
                return Result.Failed;
            }
        }
    }
}
