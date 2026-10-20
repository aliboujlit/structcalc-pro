using System;
using System.IO;
using System.Reflection;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.UI;
using StructCalcAddin.Server;
using StructCalcAddin.Commands;

namespace StructCalcAddin
{
    /// <summary>
    /// Add-in STRUCTCALC PRO pour Revit 2027 (.NET 10).
    /// Expose des commandes "Lire modèle" / "Écrire modèle" et un serveur
    /// Named Pipe (mode octet, NDJSON) pour la communication bidirectionnelle
    /// avec le noyau Python STRUCTCALC PRO.

    /// Démarrage SILENCIEUX : aucun TaskDialog bloquant. Les commandes
    /// ruban font le travail directement (elles s'exécutent déjà sur le
    /// thread principal de Revit) — jamais en appelant le dispatcher,
    /// ce qui provoquerait un interblocage (attente d'ExternalEvent depuis
    /// le thread principal).
    /// </summary>
    [Transaction(TransactionMode.Manual)]
    [Regeneration(RegenerationOption.Manual)]
    public class StructCalcAddin : IExternalApplication
    {
        // internal : accessible aux classes de commandes du même assemblage
        internal static NamedPipeServer _pipeServer;
        internal static RevitApiDispatcher _dispatcher;

        private const string AddinName = "STRUCTCALC PRO";
        internal const string PipeName = "structcalc_revit";
        internal const string TabName = "STRUCTCALC";

        public Result OnStartup(UIControlledApplication application)
        {
            try
            {
                // --- Pont thread pipe -> thread Revit ---
                _dispatcher = new RevitApiDispatcher();
                var externalEvent = ExternalEvent.Create(_dispatcher);
                _dispatcher.Attach(externalEvent);

                // --- Serveur Named Pipe ---
                _pipeServer = new NamedPipeServer(PipeName)
                {
                    OnReadModel = (payload, requestId) =>
                        _dispatcher.Dispatch("READ_MODEL", payload, requestId),
                    OnApplyChanges = (payload, requestId) =>
                        _dispatcher.Dispatch("APPLY_CHANGES", payload, requestId),
                    OnWriteModel = (payload, requestId) =>
                        _dispatcher.Dispatch("WRITE_MODEL", payload, requestId)
                };
                _pipeServer.Start();

                // --- Ruban (sans images : aucun asset PNG dans le projet) ---
                CreateRibbon(application);

                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                TaskDialog.Show("Erreur " + AddinName, "Échec du démarrage de l'add-in : " + ex.Message);
                return Result.Failed;
            }
        }

        public Result OnShutdown(UIControlledApplication application)
        {
            try { _pipeServer?.Stop(); } catch { /* best effort */ }
            try { _dispatcher?.Dispose(); } catch { /* best effort */ }
            return Result.Succeeded;
        }

        private static void CreateRibbon(UIControlledApplication application)
        {
            // Un seul onglet par session : si déjà présent (rechargement), on réutilise
            try
            {
                application.CreateRibbonTab(TabName);
            }
            catch
            {
                // l'onglet existe déjà
            }

            var panel = default(RibbonPanel);
            foreach (var p in application.GetRibbonPanels(TabName))
            {
                if (p.Name == "STRUCTCALC") { panel = p; break; }
            }
            if (panel == null) panel = application.CreateRibbonPanel(TabName, "STRUCTCALC");

            string assemblyPath = Assembly.GetExecutingAssembly().Location;

            var read = new PushButtonData("StructCalcRead", "Lire modèle",
                assemblyPath, "StructCalcAddin.Commands.ReadModelCommand")
            {
                ToolTip = "Extraire le modèle structural Revit (nœuds, barres, sections, appuis, cas de charge) vers un fichier JSON STRUCTCALC."
            };
            panel.AddItem(read);

            var write = new PushButtonData("StructCalcWrite", "Écrire modèle",
                assemblyPath, "StructCalcAddin.Commands.WriteModelCommand")
            {
                ToolTip = "Appliquer les changements STRUCTCALC (sections, armatures) au modèle Revit actif."
            };
            panel.AddItem(write);

            var status = new PushButtonData("StructCalcPipe", "Statut pipe",
                assemblyPath, "StructCalcAddin.Commands.PipeStatusCommand")
            {
                ToolTip = "Afficher l'état du Named Pipe structcalc_revit et du compte de clients."
            };
            panel.AddItem(status);

            var stop = new PushButtonData("StructCalcStop", "Arrêter pipe",
                assemblyPath, "StructCalcAddin.Commands.StopPipeCommand")
            {
                ToolTip = "Arrêter le serveur Named Pipe (la communication Python <-> Revit sera refusée)."
            };
            panel.AddItem(stop);
        }
    }
}
