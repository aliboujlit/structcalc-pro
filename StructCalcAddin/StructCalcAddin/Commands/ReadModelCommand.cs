using System;
using System.IO;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using StructCalcAddin.Models;

namespace StructCalcAddin.Commands
{
    /// <summary>
    /// Commande ruban "Lire modèle" : extraction DIRECTE via
    /// <see cref="ModelExtractor"/> (elle s'exécute déjà sur le thread
    /// principal de Revit — jamais via le dispatcher, ce qui provoquerait
    /// un interblocage d'ExternalEvent).
    /// Le résultat est sauvegardé en fichier JSON ; le transfert vers le
    /// noyau Python se fait par READ_MODEL reçu sur le Named Pipe.
    /// </summary>
    [Transaction(TransactionMode.ReadOnly)]
    public class ReadModelCommand : IExternalCommand
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
                StructuralModelDto model = ModelExtractor.Extract(doc);
                string json = DtoJson.Serialize(model);

                string path = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.Desktop),
                    $"StructCalc_Model_{DateTime.Now:yyyyMMdd_HHmmss}.json");
                File.WriteAllText(path, json);

                bool pipeUp = StructCalcAddin._pipeServer?.IsListening == true;

                var dialog = new TaskDialog("STRUCTCALC - Modèle lu")
                {
                    MainInstruction = "Extraction du modèle structural terminée",
                    MainContent =
                        $"Nœuds : {model.Nodes.Count}\n" +
                        $"Barres : {model.Bars.Count}\n" +
                        $"Cas de charge : {model.LoadCases.Count}\n" +
                        $"Fichier : {path}\n" +
                        $"Pipe structcalc_revit : {(pipeUp ? "actif (lecture Python possible)" : "inactif")}",
                    CommonButtons = TaskDialogCommonButtons.Close,
                    DefaultButton = TaskDialogResult.Close
                };
                if (model.Notes != null && model.Notes.Count > 0)
                    dialog.ExpandedContent = "Périmètre :\n- " + string.Join("\n- ", model.Notes);
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
