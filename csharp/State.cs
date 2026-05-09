using System.Text.Json;
using MQTTnet;
using MQTTnet.Protocol;

namespace CrossChat;

public class CrossChatState
{
    public Dictionary<string, CrossChatServer> Servers { get; } = [];
    public string OwnId { get; private set; } = string.Empty;
    public int NextSeq { get; set; } = 1;
    public IMqttClient? Client { get; private set; }

    private string _prefix = "crosschat/";
    private Dictionary<string, List<Func<CrossChatServer, string, string, Task>>> _subscribers = [];
    private Dictionary<string, List<Func<CrossChatServer, string, string, Task>>> _oocSubscribers = [];
    private Dictionary<string, object> _ownMeta = [];

    public void SetOwnId(string sid)
    {
        OwnId = sid;
        EnsureServer(sid);
    }

    public CrossChatServer EnsureServer(string sid)
    {
        if (!Servers.TryGetValue(sid, out var server))
        {
            server = new CrossChatServer(sid, this);
            Servers[sid] = server;
        }
        return server;
    }

    public CrossChatServer Me() => Servers[OwnId];

    public void SetStatus(string sid, long started)
    {
        if (Servers.TryGetValue(sid, out var server))
        {
            server.Started = started;
            server.Online = started > 0;
        }
    }

    public void SetMeta(Dictionary<string, object> meta)
    {
        _ownMeta = meta;
        if (Servers.TryGetValue(OwnId, out var server))
            server.Meta = meta;
    }

    public Dictionary<string, object> GetMeta() => _ownMeta;

    public void SetClient(IMqttClient client, string prefix)
    {
        Client = client;
        _prefix = prefix;
    }

    public async Task Publish(string topic, string payload, int qos = 2, bool retain = false)
    {
        if (Client == null) return;
        var fullTopic = $"{_prefix}{topic}";
        try
        {
            await Client.PublishAsync(new MqttApplicationMessageBuilder()
                .WithTopic(fullTopic)
                .WithPayload(payload)
                .WithQualityOfServiceLevel((MqttQualityOfServiceLevel)qos)
                .WithRetainFlag(retain)
                .Build());
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"Publish error on {fullTopic}: {ex.Message}");
        }
    }

    public void SetState(string key, string value)
    {
        var server = Me();
        server.States[key] = value;
        if (Client != null)
        {
            Task.Run(async () =>
            {
                await Publish($"state/{OwnId}/{key}", value, retain: true);
            });
        }
        Notify(server, key, value);
    }

    public void Subscribe(string key, Func<CrossChatServer, string, string, Task> callback)
    {
        if (!_subscribers.TryGetValue(key, out var list))
        {
            list = [];
            _subscribers[key] = list;
        }
        list.Add(callback);
    }

    internal void Notify(CrossChatServer server, string key, string value)
    {
        if (_subscribers.TryGetValue(key, out var list))
        {
            foreach (var cb in list)
            {
                Task.Run(async () => await cb(server, key, value));
            }
        }
    }

    public CrossChatUser GetOrCreateUser(string serverId, int userId)
    {
        var server = EnsureServer(serverId);
        if (server.Users.TryGetValue(userId, out var user))
            return user;
        user = new CrossChatUser
        {
            Name = string.Empty,
            FirstSeen = DateTime.UtcNow,
            Server = server,
        };
        server.Users[userId] = user;
        return user;
    }

    public async Task<int> AddUser(string name, Dictionary<string, object>? extra = null)
    {
        var server = Me();
        return await server.AddUser(name, extra);
    }

    public async Task<CrossChatUser?> DelUser(int userId)
    {
        var server = Me();
        return await server.DelUser(userId);
    }

    public void SubscribeOoc(string oocName, Func<CrossChatServer, string, string, Task> callback)
    {
        if (!_oocSubscribers.TryGetValue(oocName, out var list))
        {
            list = [];
            _oocSubscribers[oocName] = list;
        }
        list.Add(callback);
    }

    public async Task SendOoc(string targetSid, string oocName, object payload)
    {
        var jsonPayload = JsonSerializer.Serialize(payload);
        await Publish($"m/{OwnId}/{targetSid}/ooc/{oocName}", jsonPayload);
    }

    internal async Task NotifyOoc(CrossChatServer server, string oocName, string payload)
    {
        if (_oocSubscribers.TryGetValue(oocName, out var list))
        {
            foreach (var cb in list)
                await cb(server, payload, oocName);
        }
    }

    public string FormatStatus()
    {
        const string GREY = "\x1b[90m";
        const string WHITE = "\x1b[97m";
        const string GREEN = "\x1b[32m";
        const string RED = "\x1b[31m";
        const string ORANGE = "\x1b[33m";
        const string LIGHTBLUE = "\x1b[36m";
        const string R = "\x1b[0m";

        var parts = new List<string>
        {
            $"{WHITE}[Own ID: {OwnId}]{R}\n"
        };

        foreach (var sid in Servers.Keys.OrderBy(k => k))
        {
            var server = Servers[sid];
            var badge = server.Online ? $"{GREEN}ONLINE{R}" : $"{RED}OFFLINE{R}";
            var marker = sid == OwnId ? $"{GREY} (self){R}" : "";

            var active = server.Users.Count;
            var countStr = $"{GREY} ({active}){R}";

            parts.Add($"  {ORANGE}{sid}{R}: {badge}{marker}{countStr}\n");

            foreach (var uid in server.Users.Keys.OrderBy(k => k))
            {
                var user = server.Users[uid];
                var nameStr = $"{WHITE}{(string.IsNullOrEmpty(user.Name) ? "?" : user.Name)}{R}";
                parts.Add($"  {GREEN}\u2611{R} {GREY}#{uid} {R}{nameStr}\n");

                if (user.Extra.Count > 0)
                {
                    var extraKeys = user.Extra.Keys.OrderBy(k => k).ToList();
                    var extras = string.Join(", ", extraKeys.Select(k => $"{LIGHTBLUE}{k}{R}"));
                    parts.Add($"    {GREY}extra: {R}{extras}\n");
                }
            }
        }

        if (Servers.Count == 0)
            parts.Add($"{GREY}  (no servers known){R}\n");

        return string.Concat(parts);
    }
}
