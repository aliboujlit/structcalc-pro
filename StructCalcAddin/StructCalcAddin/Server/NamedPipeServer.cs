using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Pipes;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using StructCalcAddin.Models;
using StructCalcAddin.Commands;

namespace StructCalcAddin.Server
{
    /// <summary>
    /// Serveur Named Pipe (mode OCTET, NDJSON) pour Python <-> Revit.

    /// Protocole : chaque message est une ligne JSON UTF-8 terminée par "\n".
    /// TOUTE réponse est une enveloppe à EXACTEMENT 4 clés :
    ///   {"success": bool, "data": object|null, "error": string, "request_id": string}
    /// (contrat strict côté Python : ApiResponse(**reponse)).

    /// Commandes : PING (répondu inline, sans contexte Revit),
    /// READ_MODEL / APPLY_CHANGES / WRITE_MODEL (déléguées au RevitApiDispatcher),
    /// GET_ELEMENTS et toute autre commande : refus explicite motivé.
    /// </summary>
    public class NamedPipeServer : IDisposable
    {
        private readonly string _pipeName;
        private Thread _listenThread;
        private volatile bool _running;
        private readonly object _lock = new object();
        private readonly HashSet<NamedPipeServerStream> _instances = new HashSet<NamedPipeServerStream>();
        private int _clientCount;

        // Callbacks : (payload, requestId) -> enveloppe JSON complète
        public Func<string, string, string> OnReadModel { get; set; }
        public Func<string, string, string> OnApplyChanges { get; set; }
        public Func<string, string, string> OnWriteModel { get; set; }

        public string PipeName => _pipeName;
        public int ClientCount => _clientCount;

        /// <summary>Vrai dès que le serveur écoute (pas besoin d'un client connecté).</summary>
        public bool IsListening => _running;

        public NamedPipeServer(string pipeName = "structcalc_revit")
        {
            _pipeName = pipeName;
        }

        public void Start()
        {
            lock (_lock)
            {
                if (_running) return;
                _running = true;
                _listenThread = new Thread(ListenLoop) { IsBackground = true, Name = "StructCalcPipeListener" };
                _listenThread.Start();
            }
        }

        public void Stop()
        {
            List<NamedPipeServerStream> toDispose;
            lock (_lock)
            {
                _running = false;
                toDispose = new List<NamedPipeServerStream>(_instances);
                _instances.Clear();
            }
            foreach (var s in toDispose)
            {
                try { s.Dispose(); } catch { }
            }
            if (_listenThread != null && _listenThread.IsAlive)
                _listenThread.Join(TimeSpan.FromSeconds(3));
        }

        private void ListenLoop()
        {
            while (_running)
            {
                NamedPipeServerStream server = null;
                try
                {
                    server = new NamedPipeServerStream(
                        _pipeName,
                        PipeDirection.InOut,
                        NamedPipeServerStream.MaxAllowedServerInstances,
                        PipeTransmissionMode.Byte,
                        PipeOptions.Asynchronous);
                    lock (_lock) { if (!_running) { server.Dispose(); return; } _instances.Add(server); }

                    var waitTask = server.WaitForConnectionAsync();
                    while (!waitTask.Wait(200))
                    {
                        if (!_running)
                        {
                            try { server.Dispose(); } catch { }
                            return;
                        }
                    }
                    // Propager une éventuelle erreur de connexion
                    waitTask.GetAwaiter().GetResult();

                    var client = server;
                    lock (_lock) { _instances.Remove(client); } // le gestionnaire en devient responsable
                    Interlocked.Increment(ref _clientCount);
                    Task.Run(() => HandleClient(client));
                }
                catch (ObjectDisposedException)
                {
                    try { server?.Dispose(); } catch { }
                    if (!_running) return;
                }
                catch (Exception ex)
                {
                    System.Diagnostics.Debug.WriteLine($"[StructCalcPipe] ListenLoop: {ex.Message}");
                    try { server?.Dispose(); } catch { }
                    Thread.Sleep(300);
                }
            }
        }

        private void HandleClient(NamedPipeServerStream pipe)
        {
            var readBuffer = new byte[65536];
            var pending = new List<byte>();   // octets non encore aboutis à une ligne complète
            try
            {
                while (_running && pipe.IsConnected)
                {
                    int n;
                    try { n = pipe.Read(readBuffer, 0, readBuffer.Length); }
                    catch (IOException) { break; }   // client déconnecté
                    if (n <= 0) break;

                    for (int i = 0; i < n; i++) pending.Add(readBuffer[i]);

                    // Découper toutes les lignes complètes ("\n" = fin de message NDJSON)
                    int start = 0;
                    while (true)
                    {
                        int idx = pending.IndexOf((byte)'\n', start);
                        if (idx < 0) break;
                        string line = Encoding.UTF8.GetString(pending.ToArray(), start, idx - start)
                            .Trim('\r', ' ', '\t');
                        start = idx + 1;
                        if (line.Length == 0) continue;

                        string response = ProcessMessage(line);
                        byte[] bytes = Encoding.UTF8.GetBytes(response + "\n");
                        pipe.Write(bytes, 0, bytes.Length);
                        pipe.Flush();
                    }
                    if (start > 0) pending.RemoveRange(0, start);
                }
            }
            catch (Exception ex)
            {
                System.Diagnostics.Debug.WriteLine($"[StructCalcPipe] HandleClient: {ex.Message}");
            }
            finally
            {
                Interlocked.Decrement(ref _clientCount);
                try { if (pipe.IsConnected) pipe.Disconnect(); } catch { }
                try { pipe.Dispose(); } catch { }
            }
        }

        private string ProcessMessage(string jsonLine)
        {
            string requestId = "";
            try
            {
                var msg = JsonConvert.DeserializeObject<PipeMessage>(jsonLine);
                if (msg == null)
                    return PipeEnvelope.Fail("Message vide ou illisible (JSON invalide)", requestId);

                requestId = msg.RequestId ?? "";
                switch ((msg.Command ?? "").ToUpperInvariant())
                {
                    case "PING":
                        return PipeEnvelope.Ok(new
                        {
                            status = "ok",
                            server = "structcalc_revit",
                            time = DateTime.UtcNow.ToString("o")
                        }, requestId);

                    case "READ_MODEL":
                        if (OnReadModel != null) return OnReadModel(msg.Payload, requestId);
                        return PipeEnvelope.Fail("READ_MODEL non câblé côté add-in (dispatcher absent)", requestId);

                    case "APPLY_CHANGES":
                        if (OnApplyChanges != null) return OnApplyChanges(msg.Payload, requestId);
                        return PipeEnvelope.Fail("APPLY_CHANGES non câblé côté add-in (dispatcher absent)", requestId);

                    case "WRITE_MODEL":
                        if (OnWriteModel != null) return OnWriteModel(msg.Payload, requestId);
                        return PipeEnvelope.Fail("WRITE_MODEL non câblé côté add-in (dispatcher absent)", requestId);

                    case "CREATE_SCHEDULE":
                        // Payload JSON pour ScheduleCreator.CreateScheduleFromJson
                        if (msg.Payload != null)
                        {
                            try
                            {
                                return ScheduleCreator.CreateScheduleFromJson(
                                    _uiApp?.ActiveUIDocument?.Document, msg.Payload, requestId);
                            }
                            catch (Exception ex)
                            {
                                return PipeEnvelope.Fail($"CREATE_SCHEDULE: {ex.Message}", requestId);
                            }
                        }
                        return PipeEnvelope.Fail("CREATE_SCHEDULE: payload manquant", requestId);

                    case "GET_ELEMENTS":
                        return PipeEnvelope.Fail(
                            "GET_ELEMENTS non implémenté côté add-in : utilisez READ_MODEL (modèle complet)", requestId);

                    default:
                        return PipeEnvelope.Fail(
                            $"Commande inconnue: {msg.Command} (implémentées: PING, READ_MODEL, APPLY_CHANGES, WRITE_MODEL, CREATE_SCHEDULE)",
                            requestId);
                }
            }
            catch (Exception ex)
            {
                return PipeEnvelope.Fail($"Erreur traitement message: {ex.Message}", requestId);
            }
        }

        public void Dispose() => Stop();

        private class PipeMessage
        {
            [JsonProperty("command")] public string Command { get; set; }
            [JsonProperty("payload")] public string Payload { get; set; }
            [JsonProperty("request_id")] public string RequestId { get; set; }
        }
    }
}
