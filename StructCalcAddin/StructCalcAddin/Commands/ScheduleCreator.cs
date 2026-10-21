using System;
using System.Collections.Generic;
using System.Linq;
using Autodesk.Revit.DB;
using Autodesk.Revit.DB.Structure;
using StructCalcAddin.Models;

namespace StructCalcAddin.Commands
{
    /// <summary>
    /// Création de plannings (Schedules) Revit pour nomenclatures d'acier.
    /// Appelé via commande CREATE_SCHEDULE du Named Pipe.
    /// </summary>
    public static class ScheduleCreator
    {
        public class ScheduleData
        {
            public List<ScheduleRow> Rows { get; set; } = new List<ScheduleRow>();
            public double TotalMassKg { get; set; }
            public string ScheduleName { get; set; } = "STRUCTCALC_Nomenclature_Acier";
        }

        public class ScheduleRow
        {
            public string Repere { get; set; }
            public string Type { get; set; }
            public double DiametreMm { get; set; }
            public int Nombre { get; set; }
            public double LongueurM { get; set; }
            public double MasseKg { get; set; }
        }

        public class CreateScheduleResult
        {
            public bool Success { get; set; }
            public string ScheduleId { get; set; }
            public string Message { get; set; }
        }

        /// <summary>
        /// Crée un planning (Schedule/Quantities) Revit basique.
        /// Les champs détaillés sont ajoutés manuellement ou via l'UI Revit.
        /// </summary>
        public static CreateScheduleResult CreateSchedule(Document doc, ScheduleData data)
        {
            var result = new CreateScheduleResult { Success = false };

            if (doc == null)
            {
                return new CreateScheduleResult { Success = false, Message = "Document null" };
            }

            if (data?.Rows == null || data.Rows.Count == 0)
            {
                return new CreateScheduleResult { Success = false, Message = "Aucune ligne de données pour le planning" };
            }

            try
            {
                // 1. Vérifier que la catégorie Structural Framing existe
                var cat = doc.Settings.Categories.get_Item(BuiltInCategory.OST_StructuralFraming);
                if (cat == null)
                {
                    return new CreateScheduleResult { Success = false, Message = "Catégorie Structural Framing introuvable" };
                }

                // 2. Créer le ViewSchedule (Schedule/Quantities)
                var schedule = ViewSchedule.CreateSchedule(doc, new ElementId(BuiltInCategory.OST_StructuralFraming));
                if (schedule == null)
                {
                    return new CreateScheduleResult { Success = false, Message = "Échec création ViewSchedule" };
                }

                schedule.Name = data.ScheduleName ?? "STRUCTCALC_Nomenclature_Acier";

                // 3. Le planning est créé avec les champs par défaut de Revit
                // Les champs supplémentaires (paramètres partagés SC_*) doivent être ajoutés manuellement dans l'UI Revit
                // ou via une API plus spécifique selon la version.

                // 4. Mettre à jour le planning
                doc.Regenerate();

                return new CreateScheduleResult
                {
                    Success = true,
                    ScheduleId = schedule.Id.Value.ToString(),
                    Message = $"Planning créé : {schedule.Name} (Id: {schedule.Id.Value}) - Champs à compléter manuellement dans Revit"
                };
            }
            catch (Exception ex)
            {
                return new CreateScheduleResult { Success = false, Message = $"Erreur création planning : {ex.Message}" };
            }
        }

        /// <summary>
        /// Méthode statique appelée depuis NamedPipeServer pour CREATE_SCHEDULE.
        /// </summary>
        public static string CreateScheduleFromJson(Document doc, string jsonData, string requestId)
        {
            try
            {
                var data = Newtonsoft.Json.JsonConvert.DeserializeObject<ScheduleData>(jsonData);
                var result = CreateSchedule(doc, data);
                
                return PipeEnvelope.Ok(new
                {
                    success = result.Success,
                    scheduleId = result.ScheduleId,
                    message = result.Message
                }, requestId);
            }
            catch (Exception ex)
            {
                return PipeEnvelope.Fail($"CreateSchedule: {ex.Message}", requestId);
            }
        }
    }
}