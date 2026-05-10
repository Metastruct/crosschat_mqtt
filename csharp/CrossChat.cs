using System.Text.Json;
using System.Text.Json.Nodes;
using MQTTnet;
using MQTTnet.Formatter;
using MQTTnet.Protocol;
using System.Text;

namespace CrossChat;

static class ConfigHelper
{
    public static string? GetString(Dictionary<string, object> dict, string key)
    {
        if (!dict.TryGetValue(key, out var val)) return null;
        if (val is string s) return s;
        if (val is JsonElement je && je.ValueKind == JsonValueKind.String) return je.GetString();
        return null;
    }

    public static int? GetInt(Dictionary<string, object> dict, string key)
    {
        if (!dict.TryGetValue(key, out var val)) return null;
        if (val is int i) return i;
        if (val is long l) return (int)l;
        if (val is JsonElement je)
        {
            if (je.ValueKind == JsonValueKind.Number) return je.GetInt32();
            if (je.ValueKind == JsonValueKind.String && int.TryParse(je.GetString(), out var parsed)) return parsed;
        }
        return null;
    }

    public static Dictionary<string, object>? GetObject(Dictionary<string, object> dict, string key)
    {
        if (!dict.TryGetValue(key, out var val)) return null;
        if (val is Dictionary<string, object> d) return d;
        if (val is JsonElement je && je.ValueKind == JsonValueKind.Object)
        {
            var result = new Dictionary<string, object>();
            foreach (var prop in je.EnumerateObject())
                result[prop.Name] = prop.Value.Clone();
            return result;
        }
        return null;
    }

    public static object? GetRaw(Dictionary<string, object> dict, string key)
    {
        if (!dict.TryGetValue(key, out var val)) return null;
        return val;
    }
}

public class CrossChatHost
{
    public CrossChatState State { get; }
    public CancellationTokenSource Shutdown { get; } = new();

    private Dictionary<string, object> _config = [];
    private long _started;
    private ICrossChatHandler? _handler;
    private bool _initialized;
    private string _sid = string.Empty;
    private string _prefix = "crosschat/";

    public CrossChatHost(
        Dictionary<string, object>? config = null,
        string? host = null,
        int? port = null,
        string? serverId = null,
        ICrossChatHandler? handler = null)
    {
        State = new CrossChatState();
        _started = DateTimeOffset.UtcNow.ToUnixTimeSeconds();
        _handler = handler;

        if (config != null)
            _config = config;

        if (host != null || port != null)
        {
            var mqtt = ConfigHelper.GetObject(_config, "mqtt") ?? [];
            if (host != null) mqtt["host"] = host;
            if (port != null) mqtt["port"] = port;
            _config["mqtt"] = mqtt;
        }
        if (serverId != null)
            _config["server_id"] = serverId;

        var sid = ConfigHelper.GetString(_config, "server_id") ?? "";
        if (!string.IsNullOrEmpty(sid))
            State.SetOwnId(sid);
    }

    public static CrossChatHost FromConfigFile(string path)
    {
        var json = File.ReadAllText(path);
        var config = JsonSerializer.Deserialize<Dictionary<string, object>>(json) ?? [];
        return new CrossChatHost(config);
    }

    public async Task RunAsync()
    {
        _sid = State.OwnId;
        if (string.IsNullOrEmpty(_sid))
        {
            _sid = ConfigHelper.GetString(_config, "server_id") ?? "";
            State.SetOwnId(_sid);
        }

        _prefix = ConfigHelper.GetString(_config, "topic_prefix") ?? "crosschat/";
        var mqtt = ConfigHelper.GetObject(_config, "mqtt") ?? [];
        var host = ConfigHelper.GetString(mqtt, "host") ?? "localhost";
        var port = ConfigHelper.GetInt(mqtt, "port") ?? 1883;

        var factory = new MqttClientFactory();
        var client = factory.CreateMqttClient();

        var willPayload = JsonSerializer.Serialize(new Dictionary<string, object> { ["started"] = 0, ["version"] = Protocol.Version });

        var options = new MqttClientOptionsBuilder()
            .WithTcpServer(host, port)
            .WithProtocolVersion(MqttProtocolVersion.V500)
            .WithCleanStart()
            .WithSessionExpiryInterval(9)
            .WithKeepAlivePeriod(TimeSpan.FromSeconds(4))
            .WithWillTopic($"{_prefix}state/{_sid}/status")
            .WithWillPayload(willPayload)
            .WithWillRetain(true)
            .WithWillQualityOfServiceLevel(MqttQualityOfServiceLevel.AtLeastOnce)
            .WithClientId(_sid)
            .Build();

        client.ApplicationMessageReceivedAsync += async args =>
        {
            var topic = args.ApplicationMessage.Topic;
            var payload = Encoding.UTF8.GetString(args.ApplicationMessage.Payload);
            await HandleMessage(topic, payload);
        };

        Console.WriteLine($"Connecting to {host}:{port} as {_sid}...");
        var connectResult = await client.ConnectAsync(options);
        Console.WriteLine($"Connected: {connectResult.ResultCode}");

        State.SetClient(client, _prefix);
        await InitAsync(client);

        foreach (var level in new[] { "debug", "warning", "info" })
        {
            var captured = level;
            State.SubscribeOoc(level, (server, payload, name) =>
            {
                Console.WriteLine($"[ooc:{captured}] {server.Id}: {payload}");
                return Task.CompletedTask;
            });
        }

        Console.CancelKeyPress += (_, e) =>
        {
            e.Cancel = true;
            Console.WriteLine("\nCtrl+C pressed, shutting down...");
            Shutdown.Cancel();
        };

        Console.WriteLine("\nConsole REPL. Type 'help' for commands.\n");
        await RunConsoleLoop();

        Console.WriteLine("Disconnecting with will message...");
        try
        {
            await client.DisconnectAsync(new MqttClientDisconnectOptions
            {
                Reason = MqttClientDisconnectOptionsReason.DisconnectWithWillMessage
            });
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Disconnect error: {ex.Message}");
        }

        Console.WriteLine("Shutdown complete.");
    }

    private async Task InitAsync(IMqttClient client)
    {
        if (_initialized) return;
        _initialized = true;

        await client.SubscribeAsync(new MqttClientSubscribeOptionsBuilder()
            .WithTopicFilter($"{_prefix}state/+/#", MqttQualityOfServiceLevel.AtMostOnce)
            .WithTopicFilter($"{_prefix}m/+/{_sid}/#", MqttQualityOfServiceLevel.AtMostOnce)
            .Build());

        var statusPayload = JsonSerializer.Serialize(new Dictionary<string, object> { ["started"] = _started, ["version"] = Protocol.Version });
        State.SetStatus(_sid, _started);
        await State.Publish($"state/{_sid}/status", statusPayload, retain: true);
        Console.WriteLine($"Published state/{_sid}/status: started={_started}");

        var metaRaw = ConfigHelper.GetRaw(_config, "meta");
        if (metaRaw is JsonElement metaJe)
            metaRaw = JsonSerializer.Deserialize<Dictionary<string, object>>(metaJe.GetRawText());
        var metaPayload = metaRaw != null ? JsonSerializer.Serialize(metaRaw) : "{}";
        await State.Publish($"state/{_sid}/meta", metaPayload, retain: true);

        State.SetMeta(metaRaw as Dictionary<string, object> ?? []);
    }

    private async Task HandleMessage(string topic, string payload)
    {
        var parts = topic.Split('/');
        if (parts.Length < 2 || parts[0] != "crosschat") return;

        try
        {
            if (parts[1] == "state" && parts.Length >= 4)
                await HandleStateMessage(parts, payload);
            else if (parts[1] == "m" && parts.Length >= 5 && parts[3] == State.OwnId)
                await HandleMmessage(parts, payload);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Error handling message {topic}: {ex.Message}");
        }
    }

    private async Task HandleStateMessage(string[] parts, string payload)
    {
        var sid = parts[2];
        if (sid == State.OwnId)
            return;

        var key = parts[3];
        if (key == "status")
        {
            var prev = State.Servers.GetValueOrDefault(sid);
            var prevStarted = prev?.Started ?? 0;

            long started = 0;
            try
            {
                using var doc = JsonDocument.Parse(payload);
                started = doc.RootElement.TryGetProperty("started", out var s) ? s.GetInt64() : 0;
            }
            catch
            {
                Console.Error.WriteLine($"Invalid status payload from {sid}");
            }

            State.EnsureServer(sid);
            State.SetStatus(sid, started);
            var server = State.Servers.GetValueOrDefault(sid);

            if (started != prevStarted && server != null)
            {
                if (_handler != null)
                {
                    if (started > 0 && prevStarted == 0)
                        await _handler.OnServerAdd(server);
                    else if (started == 0)
                        await _handler.OnServerDel(server);
                    await _handler.OnServerStatus(server);
                }

                Console.WriteLine($"Server {sid} state changed: started={started}");

                if (started > 0)
                {
                    var ownServer = State.Servers.GetValueOrDefault(State.OwnId);
                    if (ownServer != null)
                    {
                        var users = ownServer.Users.Values.ToList();
                        var userCount = users.Count;
                        for (int i = 0; i < userCount; i++)
                        {
                            var user = users[i];
                            var serialized = user.Serialize();
                            serialized["cmd"] = "add";

                            var flag = userCount == 1 ? BurstFlag.Startend
                                : i == 0 ? BurstFlag.Start
                                : i == userCount - 1 ? BurstFlag.End
                                : BurstFlag.Active;

                            serialized["burst"] = flag.Serialize();
                            await State.Publish($"m/{State.OwnId}/{sid}/user", serialized.ToJsonString());
                        }
                        Console.WriteLine($"Burst sent {userCount} user(s) to {sid}");
                    }
                }
            }
        }
        else if (key == "meta" && parts.Length == 4)
        {
            try
            {
                using var doc = JsonDocument.Parse(payload);
                var server = State.EnsureServer(sid);
                var metaDict = new Dictionary<string, object>();
                foreach (var prop in doc.RootElement.EnumerateObject())
                    metaDict[prop.Name] = prop.Value.ToString();
                server.Meta = metaDict;
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"Invalid meta payload from {sid}: {ex.Message}");
            }
        }
        else
        {
            var server = State.EnsureServer(sid);
            server.States[key] = payload;
            State.Notify(server, key, payload);
        }
    }

    static object? JsonElementToValue(JsonElement el)
    {
        return el.ValueKind switch
        {
            JsonValueKind.String => el.GetString() ?? "",
            JsonValueKind.Number => el.TryGetInt64(out var l) ? (object)l : el.GetDouble(),
            JsonValueKind.True => true,
            JsonValueKind.False => false,
            JsonValueKind.Null => null,
            _ => el.GetRawText(),
        };
    }

    static int JsonToInt(JsonElement root, string key)
    {
        if (!root.TryGetProperty(key, out var el)) return 0;
        if (el.ValueKind == JsonValueKind.Number) return el.GetInt32();
        if (el.ValueKind == JsonValueKind.String && int.TryParse(el.GetString(), out var n)) return n;
        return 0;
    }

    static DateTime JsonToDateTime(JsonElement root, string key)
    {
        if (!root.TryGetProperty(key, out var el)) return DateTime.UtcNow;
        long ts = 0;
        if (el.ValueKind == JsonValueKind.Number)
            ts = el.GetInt64();
        else if (el.ValueKind == JsonValueKind.String && long.TryParse(el.GetString(), out var p))
            ts = p;
        if (ts > 0)
            return DateTimeOffset.FromUnixTimeSeconds(ts).UtcDateTime;
        return DateTime.UtcNow;
    }

    private async Task HandleMmessage(string[] parts, string payload)
    {
        var fromSid = parts[2];
        var endpoint = parts[4];

        switch (endpoint)
        {
            case "user":
                await HandleUserMessage(fromSid, payload);
                break;
            case "say" when parts.Length == 6:
                await HandleSayMessage(fromSid, parts, payload);
                break;
            case "ooc" when parts.Length == 6:
                await HandleOocMessage(fromSid, parts, payload);
                break;
            case "pm" when parts.Length == 7:
                await HandlePmMessage(fromSid, parts, payload);
                break;
            default:
                Console.WriteLine($"Unknown endpoint: {endpoint}");
                break;
        }
    }

    private async Task HandleUserMessage(string fromSid, string payload)
    {
        if (string.IsNullOrEmpty(fromSid) || fromSid == State.OwnId) return;

        try
        {
            using var doc = JsonDocument.Parse(payload);
            var root = doc.RootElement;

            var userId = root.TryGetProperty("id", out var idEl) && idEl.ValueKind == JsonValueKind.Number
                ? idEl.GetInt32() : -1;
            if (userId < 0)
            {
                Console.Error.WriteLine($"Invalid user id in message from {fromSid}");
                return;
            }

            var cmd = root.TryGetProperty("cmd", out var cmdEl) ? cmdEl.GetString() ?? "" : "";
            if (cmd is not ("add" or "del" or "update"))
            {
                Console.Error.WriteLine($"Unknown user cmd '{cmd}' from {fromSid}");
                return;
            }

            CrossChatUser? user = null;
            var server = State.EnsureServer(fromSid);

            if (cmd == "del")
            {
                if (server.Users.Remove(userId, out user))
                    Console.WriteLine($"User {userId} removed from {fromSid}");
            }
            else
            {
                var firstSeen = JsonToDateTime(root, "first_seen");

                var known = new HashSet<string> { "name", "first_seen", "server", "burst", "cmd", "id" };
                var extra = new Dictionary<string, object>();
                foreach (var prop in root.EnumerateObject())
                {
                    if (!known.Contains(prop.Name))
                        extra[prop.Name] = JsonElementToValue(prop.Value)!;
                }

                user = new CrossChatUser
                {
                    Name = root.TryGetProperty("name", out var nameEl) ? nameEl.GetString() ?? "" : "",
                    Id = userId,
                    FirstSeen = firstSeen,
                    Server = server,
                    Extra = extra,
                };
                server.Users[userId] = user;
                Console.WriteLine($"User {userId} ({user.Name}) added/updated on {fromSid}");
            }

            var burst = root.TryGetProperty("burst", out var burstEl)
                ? BurstFlagExtensions.Deserialize(burstEl)
                : BurstFlag.None;

            if (cmd == "add" && fromSid != State.OwnId)
            {
                if (burst is BurstFlag.Start or BurstFlag.Startend)
                    server.Bursting = true;
                if (burst is BurstFlag.End or BurstFlag.Startend)
                    server.Bursting = false;
            }

            if (_handler != null && user != null && cmd is "add" or "del" or "update")
                await _handler.OnUser(user, cmd, burst);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Error handling user message from {fromSid}: {ex}");
        }
    }

    private async Task HandleSayMessage(string fromSid, string[] parts, string payload)
    {
        try
        {
            var senderId = int.Parse(parts[5]);
            using var doc = JsonDocument.Parse(payload);
            var sayText = doc.RootElement.TryGetProperty("say", out var sayEl) ? sayEl.GetString() ?? "" : "";

            var server = State.EnsureServer(fromSid);
            var user = server.GetUser(senderId, ensure: true);
            if (user != null && _handler != null)
                await _handler.OnSay(user, sayText);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Error handling say: {ex.Message}");
        }
    }

    private async Task HandleOocMessage(string fromSid, string[] parts, string payload)
    {
        var oocName = parts[5];
        var server = State.EnsureServer(fromSid);
        await State.NotifyOoc(server, oocName, payload);
    }

    private Task HandlePmMessage(string fromSid, string[] parts, string payload)
    {
        try
        {
            var fromUserId = int.Parse(parts[5]);
            var toUserId = int.Parse(parts[6]);
            using var doc = JsonDocument.Parse(payload);
            var sayText = doc.RootElement.TryGetProperty("say", out var sayEl) ? sayEl.GetString() ?? "" : "";

            var senderServer = State.Servers.GetValueOrDefault(fromSid);
            var senderUser = senderServer?.Users.GetValueOrDefault(fromUserId);
            var receiverServer = State.Servers.GetValueOrDefault(State.OwnId);
            var receiverUser = receiverServer?.Users.GetValueOrDefault(toUserId);

            Console.WriteLine($"PM from {fromSid}/{fromUserId} ({senderUser?.Name ?? "?"}) " +
                            $"to {State.OwnId}/{toUserId} ({receiverUser?.Name ?? "?"}): {sayText}");
            Console.WriteLine("PM not fully implemented");
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Error handling PM: {ex.Message}");
        }
        return Task.CompletedTask;
    }

    private async Task RunConsoleLoop()
    {
        while (!Shutdown.Token.IsCancellationRequested)
        {
            Console.Write("> ");
            var line = await Console.In.ReadLineAsync();
            if (line == null) break;
            line = line.Trim();
            if (string.IsNullOrEmpty(line)) continue;

            var args = line.Split(' ', StringSplitOptions.RemoveEmptyEntries);
            var cmd = args[0].ToLower();

            try
            {
                switch (cmd)
                {
                    case "help":
                        Console.WriteLine("Commands:");
                        Console.WriteLine("  status              Show known servers and users");
                        Console.WriteLine("  add <name>          Add a local user and broadcast");
                        Console.WriteLine("  del <id>            Remove a local user");
                        Console.WriteLine("  say <uid> <msg>     Send chat message from user");
                        Console.WriteLine("  pm <from> <sid> <to> <msg>  Send PM");
                        Console.WriteLine("  exit / quit         Shutdown");
                        break;

                    case "status":
                        Console.WriteLine(State.FormatStatus());
                        break;

                    case "add":
                        if (args.Length < 2)
                            Console.WriteLine("Usage: add <name>");
                        else
                        {
                            var name = string.Join(" ", args.Skip(1));
                            var uid = await State.AddUser(name);
                            if (_handler != null && State.Me().Users.TryGetValue(uid, out var user))
                                await _handler.OnUser(user, "add");
                            Console.WriteLine($"User {uid} ({name}) added");
                        }
                        break;

                    case "del":
                        if (args.Length < 2)
                            Console.WriteLine("Usage: del <id>");
                        else if (int.TryParse(args[1], out var delId))
                        {
                            var server = State.Me();
                            if (server.Users.TryGetValue(delId, out var delUser))
                            {
                                await State.DelUser(delId);
                                Console.WriteLine($"User {delId} ({delUser.Name}) removed");
                            }
                            else
                                Console.WriteLine($"User {delId} not found");
                        }
                        break;

                    case "say":
                        if (args.Length < 3)
                            Console.WriteLine("Usage: say <uid> <message>");
                        else if (int.TryParse(args[1], out var sayId))
                        {
                            var msg = string.Join(" ", args.Skip(2));
                            var ownServer = State.Me();
                            if (ownServer.Users.TryGetValue(sayId, out var sayUser))
                            {
                                var payload = JsonSerializer.Serialize(new { say = msg });
                                var targets = 0;
                                foreach (var kv in State.Servers)
                                {
                                    if (kv.Key != State.OwnId && kv.Value.Online)
                                    {
                                        targets++;
                                        await State.Publish($"m/{State.OwnId}/{kv.Key}/say/{sayId}", payload);
                                    }
                                }
                                if (_handler != null)
                                    await _handler.OnSay(sayUser, msg);
                                Console.WriteLine($"Message sent to {sayId} ({sayUser.Name}) on {targets} online server(s)");
                            }
                            else
                                Console.WriteLine($"User {sayId} not found");
                        }
                        break;

                    case "pm":
                        if (args.Length < 5)
                            Console.WriteLine("Usage: pm <from_uid> <sid> <to_uid> <message>");
                        else if (int.TryParse(args[1], out var pmFrom) && int.TryParse(args[3], out var pmTo))
                        {
                            var targetSid = args[2];
                            var msg = string.Join(" ", args.Skip(4));
                            var payload = JsonSerializer.Serialize(new { say = msg });
                            await State.Publish($"m/{State.OwnId}/{targetSid}/pm/{pmFrom}/{pmTo}", payload);
                            Console.WriteLine($"PM sent from {pmFrom} to {targetSid}/{pmTo}");
                        }
                        break;

                    case "exit":
                    case "quit":
                        Console.WriteLine("Shutting down...");
                        Shutdown.Cancel();
                        return;

                    default:
                        Console.WriteLine($"Unknown command: {cmd}. Type 'help' for commands.");
                        break;
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"Error: {ex.Message}");
            }
        }
    }
}
