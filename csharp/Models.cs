using System.Text.Json;
using System.Text.Json.Nodes;

namespace CrossChat;

public static class Protocol
{
    public const int Version = 1;
}

public class CrossChatUser
{
    public string Name { get; set; } = string.Empty;
    public DateTime FirstSeen { get; set; } = DateTime.UtcNow;
    public required CrossChatServer Server { get; set; }
    public int Id { get; set; }
    public Dictionary<string, object> Extra { get; set; } = [];

    public JsonObject Serialize()
    {
        var result = new JsonObject
        {
            ["id"] = Id,
            ["name"] = Name,
            ["first_seen"] = new DateTimeOffset(FirstSeen).ToUnixTimeSeconds(),
            ["server"] = Server.Id,
        };
        foreach (var (k, v) in Extra)
            result[k] = JsonSerializer.SerializeToNode(v);
        return result;
    }
}

public enum BurstFlag
{
    None = 0,
    Startend = 1,
    Start = 2,
    End = 3,
    Active = 4,
}

public static class BurstFlagExtensions
{
    public static JsonNode Serialize(this BurstFlag flag) => flag switch
    {
        BurstFlag.None => JsonValue.Create(false)!,
        BurstFlag.Startend => JsonValue.Create("startend")!,
        BurstFlag.Start => JsonValue.Create("start")!,
        BurstFlag.End => JsonValue.Create("end")!,
        BurstFlag.Active => JsonValue.Create(true)!,
        _ => JsonValue.Create(false)!,
    };

    public static object SerializeRaw(this BurstFlag flag) => flag switch
    {
        BurstFlag.None => false,
        BurstFlag.Startend => "startend",
        BurstFlag.Start => "start",
        BurstFlag.End => "end",
        BurstFlag.Active => true,
        _ => false,
    };

    public static BurstFlag Deserialize(JsonElement? value)
    {
        if (value is null) return BurstFlag.None;
        return value.Value.ValueKind switch
        {
            JsonValueKind.False => BurstFlag.None,
            JsonValueKind.True => BurstFlag.Active,
            JsonValueKind.String => value.Value.GetString() switch
            {
                "startend" => BurstFlag.Startend,
                "start" => BurstFlag.Start,
                "end" => BurstFlag.End,
                "true" => BurstFlag.Active,
                _ => BurstFlag.None,
            },
            _ => BurstFlag.None,
        };
    }

    public static BurstFlag Deserialize(JsonElement value) => Deserialize((JsonElement?)value);

    public static BurstFlag Deserialize(JsonNode? node)
    {
        if (node is null) return BurstFlag.None;
        if (node is JsonValue jv)
        {
            if (jv.TryGetValue<bool>(out var b))
                return b ? BurstFlag.Active : BurstFlag.None;
            if (jv.TryGetValue<string>(out var s))
            {
                return s switch
                {
                    "startend" => BurstFlag.Startend,
                    "start" => BurstFlag.Start,
                    "end" => BurstFlag.End,
                    "true" => BurstFlag.Active,
                    _ => BurstFlag.None,
                };
            }
        }
        return BurstFlag.None;
    }
}

public static class UserCommand
{
    public const string Add = "join";
    public const string Remove = "leave";
    public const string Update = "update";
}

public interface ICrossChatHandler
{
    Task OnUser(CrossChatUser user, string cmd, BurstFlag burst = BurstFlag.None, string reason = "");
    Task OnSay(CrossChatUser user, string say);
    Task OnPm(CrossChatUser sender, string targetServerId, int targetUserId, string say);
    Task OnServerAdd(CrossChatServer server);
    Task OnServerDel(CrossChatServer server);
    Task OnServerStatus(CrossChatServer server);
}

public class CrossChatServer
{
    public string Id { get; set; } = string.Empty;
    public bool Online { get; set; }
    public long Started { get; set; }
    public bool Bursting { get; set; }
    public Dictionary<int, CrossChatUser> Users { get; set; } = [];
    public Dictionary<string, string> States { get; set; } = [];
    public Dictionary<string, object> Meta { get; set; } = [];
    internal CrossChatState? State { get; set; }

    public CrossChatServer() { }

    public CrossChatServer(string id, CrossChatState? state = null)
    {
        Id = id;
        State = state;
    }

    public async Task SendOoc(string oocName, object payload)
    {
        if (State != null)
            await State.SendOoc(Id, oocName, payload);
    }

    public CrossChatUser? GetUser(int id, bool create = false, bool ensure = false)
    {
        if (Users.TryGetValue(id, out var user))
            return user;
        if (create || ensure)
        {
            user = new CrossChatUser
            {
                Name = $"UnknownUser{id}",
                Server = this,
                Id = id,
                FirstSeen = DateTime.UtcNow,
            };
            Users[id] = user;
        }
        return user;
    }

    public async Task<int> AddUser(string name, Dictionary<string, object>? extra = null)
    {
        var state = State ?? throw new InvalidOperationException("CrossChatServer has no state reference");
        var userId = state.NextSeq;
        var user = new CrossChatUser
        {
            Name = name,
            FirstSeen = DateTime.UtcNow,
            Server = this,
            Id = userId,
            Extra = extra ?? [],
        };
        state.NextSeq++;
        Users[userId] = user;

        if (state.Client != null)
        {
            var userData = user.Serialize();
            userData["cmd"] = "join";
            userData["burst"] = BurstFlag.None.Serialize();
            var payload = userData.ToJsonString();

            foreach (var kv in state.Servers)
            {
                if (kv.Key != state.OwnId && kv.Value.Online)
                    await state.Publish($"m/{state.OwnId}/{kv.Key}/user", payload);
            }
        }
        return userId;
    }

    public async Task<CrossChatUser?> DelUser(int userId, string reason = "")
    {
        var state = State;
        if (!Users.Remove(userId, out var user))
            return null;

        if (state?.Client != null)
        {
            var payload = new JsonObject
            {
                ["id"] = userId,
                ["cmd"] = "leave",
                ["reason"] = reason,
            }.ToJsonString();

            foreach (var kv in state.Servers)
            {
                if (kv.Key != state.OwnId && kv.Value.Online)
                    await state.Publish($"m/{state.OwnId}/{kv.Key}/user", payload);
            }
        }
        return user;
    }
}
