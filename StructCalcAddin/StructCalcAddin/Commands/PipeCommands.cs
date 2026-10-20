using System;
using Autodesk.Revit.Attributes;
using Autodesk.Revit.DB;
using Autodesk.Revit.UI;
using StructCalcAddin.Server;

namespace StructCalcAddin.Commands
{
    /// <summary>
    /// Commande ruban "Statut pipe" : état réel du serveur Named Pipe.
    /// </summary>
    [Transaction(TransactionMode.ReadOnly)]
    public class PipeStatusCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            NamedPipeServer server = StructCalcAddin._pipeServer;
            if (server == null)
            {
                TaskDialog.Show("STRUCTCALC - Pipe",
                    "Le serveur Named Pipe n'a pas été créé (démarrage de l'add-in échoué ?).");
                return Result.Failed;
            }

            TaskDialog.Show("STRUCTCALC - Statut pipe",
                $"Pipe : \\\\.\\pipe\\{server.PipeName}\n" +
                $"État : {(server.IsListening ? "EN ÉCOUTE" : "ARRÊTÉ")}\n" +
                $"Clients connectés : {server.ClientCount}\n\n" +
                "Protocole : NDJSON mode octet, enveloppe {{success, data, error, request_id}}.\n" +
                "Commandes : PING, READ_MODEL, APPLY_CHANGES, WRITE_MODEL.");
            return Result.Succeeded;
        }
    }

    /// <summary>
    /// Commande ruban "Arrêter pipe" : coupe la communication Python <-> Revit.
    /// </summary>
    [Transaction(TransactionMode.ReadOnly)]
    public class StopPipeCommand : IExternalCommand
    {
        public Result Execute(ExternalCommandData commandData, ref string message, ElementSet elements)
        {
            NamedPipeServer server = StructCalcAddin._pipeServer;
            if (server == null)
            {
                TaskDialog.Show("STRUCTCALC - Pipe", "Aucun serveur pipe à arrêter.");
                return Result.Succeeded;
            }

            try
            {
                server.Stop();
                TaskDialog.Show("STRUCTCALC - Pipe",
                    "Serveur Named Pipe arrêté : toute requête Python sera refusée " +
                    "(pipe introuvable) jusqu'au redémarrage de Revit.");
                return Result.Succeeded;
            }
            catch (Exception ex)
            {
                message = "Arrêt impossible : " + ex.Message;
                return Result.Failed;
            }
        }
    }
}
