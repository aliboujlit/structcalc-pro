using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Threading.Tasks;
using Autodesk.Revit.UI;
using StructCalcAddin.Commands;
using StructCalcAddin.Models;

namespace StructCalcAddin.Server
{
    /// <summary>
    /// Pont entre le thread du Named Pipe et le thread principal de Revit.

    /// Revit n'autorise l'accès à son API qu' depuis le thread principal :
    /// le thread pipe enfile les requêtes ici, l'ExternalEvent les déclenche,
    /// et un TaskCompletionSource renvoie la réponse enveloppée.

    /// Règle absolue : aucune requête pipe n'est traitée "à la sauvageette" ;
    /// tout passe par Execute() exécuté par Revit lui-même.
    /// </summary>
    public class RevitApiDispatcher : IExternalEventHandler, IDisposable
    {
        private sealed class PendingRequest
        {
            public string Command;
            public string Payload;
            public string RequestId;
            public TaskCompletionSource<string> Completion;
        }

        private readonly ConcurrentQueue<PendingRequest> _queue = new ConcurrentQueue<PendingRequest>();
        private ExternalEvent _event;

        /// <summary>Délai maximal d'attente du thread principal de Revit.</summary>
        public int TimeoutMs { get; set; } = 15000;

        public void Attach(ExternalEvent evt)
        {
            _event = evt;
        }

        public string GetName() => "STRUCTCALC Revit API Dispatcher";

        /// <summary>
        /// Appelé depuis le thread pipe. Sérialise la requête sur le thread
        /// Revit et attend la réponse (enveloppe JSON complète).
        /// </summary>
        public string Dispatch(string command, string payload, string requestId)
        {
            if (_event == null)
                return PipeEnvelope.Fail("Dispatcher non initialisé (ExternalEvent absent) — add-in mal chargé", requestId);

            var request = new PendingRequest
            {
                Command = command,
                Payload = payload ?? "",
                RequestId = requestId ?? "",
                Completion = new TaskCompletionSource<string>(TaskCreationOptions.RunContinuationsAsynchronously)
            };
            _queue.Enqueue(request);

            var raiseStatus = _event.Raise();
            if (raiseStatus != ExternalEventRequest.Accepted)
                return PipeEnvelope.Fail(
                    $"ExternalEvent refusé ({raiseStatus}) — Revit occupé (dialogue modal oufermeture en cours)", requestId);

            if (!request.Completion.Task.Wait(TimeoutMs))
                return PipeEnvelope.Fail(
                    $"Délai dépassé ({TimeoutMs} ms) : le thread principal de Revit n'a pas traité la requête {command}", requestId);

            return request.Completion.Task.Result;
        }

        /// <summary>Exécuté par Revit sur son thread principal.</summary>
        public void Execute(UIApplication app)
        {
            while (_queue.TryDequeue(out var request))
            {
                try
                {
                    string envelope = Handle(app, request.Command, request.Payload, request.RequestId);
                    request.Completion.TrySetResult(envelope);
                }
                catch (Exception ex)
                {
                    request.Completion.TrySetResult(
                        PipeEnvelope.Fail($"Erreur API Revit sur {request.Command}: {ex.Message}", request.RequestId));
                }
            }
        }

        /// <summary>
        /// Libère les requêtes en attente : toute requête non traitée reçoit
        /// une erreur honnête (jamais d'attente infinie côté Python).
        /// </summary>
        public void Dispose()
        {
            _event = null;
            while (_queue.TryDequeue(out var pending))
                pending.Completion.TrySetResult(
                    PipeEnvelope.Fail("Add-in en cours d'arrêt : requête non exécutée", pending.RequestId));
        }

        private static string Handle(UIApplication app, string command, string payload, string requestId)
        {
            switch (command)
            {
                case "READ_MODEL":
                {
                    var doc = app.ActiveUIDocument?.Document;
                    if (doc == null)
                        return PipeEnvelope.Fail(
                            "Aucun document Revit actif — ouvrez un modèle (.rvt) puis relancez la lecture", requestId);
                    var model = ModelExtractor.Extract(doc);
                    return PipeEnvelope.Ok(model, requestId);
                }

                case "APPLY_CHANGES":
                case "WRITE_MODEL":
                {
                    var doc = app.ActiveUIDocument?.Document;
                    if (doc == null)
                        return PipeEnvelope.Fail(
                            "Aucun document Revit actif — ouvrez un modèle (.rvt) puis relancez l'écriture", requestId);
                    ApplyChangesRequest changes;
                    try
                    {
                        changes = string.IsNullOrWhiteSpace(payload)
                            ? new ApplyChangesRequest()
                            : DtoJson.Deserialize<ApplyChangesRequest>(payload);
                    }
                    catch (Exception ex)
                    {
                        return PipeEnvelope.Fail($"Charge utile illisible (JSON invalide): {ex.Message}", requestId);
                    }
                    if (changes == null) changes = new ApplyChangesRequest();
                    var result = ChangesApplier.Apply(doc, changes);
                    return PipeEnvelope.Ok(result, requestId);
                }

                default:
                    return PipeEnvelope.Fail($"Commande non implémentée côté add-in: {command}", requestId);
            }
        }
    }
}
