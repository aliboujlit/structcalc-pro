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
        /// Crée un planning (Schedule/Quantities) Revit avec les données de nomenclature.
        /// Nécessite que les éléments/armatures existent déjà avec paramètres partagés SC_*.
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
                // 1. Vérifier que la catégorie Structural Framing a les paramètres partagés SC_*
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

                // 3. Ajouter les champs (champs de base + paramètres partagés SC_*)
                var fieldIds = new List<ScheduleFieldId>();

                // Champs de base
                AddScheduleField(schedule, fieldIds, ScheduleFieldType.Instance, "Type");
                AddScheduleField(schedule, fieldIds, ScheduleFieldType.Instance, "Family");
                AddScheduleField(schedule, fieldIds, ScheduleFieldType.Instance, "Type Name");

                // Paramètres partagés SC_* (ajoutés en champs)
                AddSharedParamField(schedule, fieldIds, "SC_Status");
                AddSharedParamField(schedule, fieldIds, "SC_Rebar_Layer");
                AddSharedParamField(schedule, fieldIds, "SC_Rebar_Status");
                AddSharedParamField(schedule, fieldIds, "SC_Rebar_Position");
                AddSharedParamField(schedule, fieldIds, "SC_Rebar_Count");
                AddSharedParamField(schedule, fieldIds, "SC_Enrobage_mm");
                AddSharedParamField(schedule, fieldIds, "SC_Recouvrement_mm");
                AddSharedParamField(schedule, fieldIds, "SC_Attente_mm");
                AddSharedParamField(schedule, fieldIds, "SC_Classe_Acier");
                AddSharedParamField(schedule, fieldIds, "SC_Classe_Beton");
                AddSharedParamField(schedule, fieldIds, "SC_Gamme_Barres");

                // Quantités calculées (champs calculés ou paramètres de type)
                AddSharedParamField(schedule, fieldIds, "SC_Quantite_Longueur_m");
                AddSharedParamField(schedule, fieldIds, "SC_Quantite_Masse_kg");
                AddSharedParamField(schedule, fieldIds, "SC_Note_Honnetete");

                // 4. Trier et grouper
                try
                {
                    var sortField = schedule.Definition.GetFieldOrder().FirstOrDefault();
                    if (sortField != null)
                    {
                        schedule.Definition.AddSortGroup(new ScheduleSortGroupField(sortField, ScheduleSortOrder.Ascending));
                    }
                }
                catch { }

                // 5. Filtrer : seulement éléments avec SC_Status = "A_VALIDER" ou "GÉNÉRÉE"
                try
                {
                    var filter = new ScheduleFilter(
                        schedule.Definition.GetFieldOrder().FirstOrDefault(f => 
                            schedule.Definition.GetField(f).GetName() == "SC_Status"),
                        ScheduleFilterType.Equal,
                        "A_VALIDER");
                    schedule.Definition.AddFilter(filter);
                }
                catch { }

                // 6. Afficher les totaux
                schedule.Definition.ShowTotals = true;
                schedule.Definition.ShowGrandTotal = true;
                schedule.Definition.ShowGrandTotalCount = true;
                schedule.Definition.ShowGrandTotalTitle = true;
                schedule.Definition.GrandTotalTitle = "TOTAL GÉNÉRAL";

                // 7. Mettre à jour le planning
                doc.Regenerate();

                return new CreateScheduleResult
                {
                    Success = true,
                    ScheduleId = schedule.Id.Value.ToString(),
                    Message = $"Planning créé : {schedule.Name} (Id: {schedule.Id.Value})"
                };
            }
            catch (Exception ex)
            {
                return new CreateScheduleResult { Success = false, Message = $"Erreur création planning : {ex.Message}" };
            }
        }

        private static void AddScheduleField(ViewSchedule schedule, List<ScheduleFieldId> fieldIds, 
            ScheduleFieldType type, string paramName)
        {
            try
            {
                var fieldId = schedule.Definition.AddField(new ScheduleFieldId(type, paramName));
                if (fieldId != ScheduleFieldId.Invalid)
                    fieldIds.Add(fieldId);
            }
            catch { }
        }

        private static void AddSharedParamField(ViewSchedule schedule, List<ScheduleFieldId> fieldIds, string paramName)
        {
            try
            {
                var binding = new FilteredElementCollector(schedule.Document)
                    .OfClass(typeof(SharedParameterElement))
                    .Cast<SharedParameterElement>()
                    .FirstOrDefault(sp => sp.Name == paramName);

                if (binding != null)
                {
                    var fieldId = schedule.Definition.AddField(new ScheduleFieldId(binding.Id));
                    if (fieldId != ScheduleFieldId.Invalid)
                        return;
                }
            }
            catch { }
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