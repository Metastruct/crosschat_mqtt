namespace CrossChat;

public static class Aowl
{
    private static int _seq;

    private static int NextId() => ++_seq;

    public static async Task Kick(CrossChatState state, string steamid64, string reason)
    {
        var id = NextId();
        var payload = new { id, steamid64, reason, extra = new Dictionary<string, object>() };
        await Broadcast(state, "aowl_kick", payload, reason);
    }

    public static async Task Ban(CrossChatState state, string steamid64, string reason)
    {
        var id = NextId();
        var payload = new { id, steamid64, reason, extra = new Dictionary<string, object>() };
        await Broadcast(state, "aowl_ban", payload, reason);
    }

    public static async Task Slap(CrossChatState state, string steamid64, string reason)
    {
        var id = NextId();
        var payload = new { id, steamid64, reason, extra = new Dictionary<string, object>() };
        await Broadcast(state, "aowl_slap", payload, reason);
    }

    public static async Task KickUser(CrossChatState state, string serverId, int userId, string reason)
    {
        var id = NextId();
        var payload = new { id, server_id = serverId, user_id = userId, reason, extra = new Dictionary<string, object>() };
        await Broadcast(state, "aowl_kick", payload, reason);
    }

    public static async Task BanUser(CrossChatState state, string serverId, int userId, string reason)
    {
        var id = NextId();
        var payload = new { id, server_id = serverId, user_id = userId, reason, extra = new Dictionary<string, object>() };
        await Broadcast(state, "aowl_ban", payload, reason);
    }

    public static async Task SlapUser(CrossChatState state, string serverId, int userId, string reason)
    {
        var id = NextId();
        var payload = new { id, server_id = serverId, user_id = userId, reason, extra = new Dictionary<string, object>() };
        await Broadcast(state, "aowl_slap", payload, reason);
    }

    private static async Task Broadcast(CrossChatState state, string oocType, object payload, string reason)
    {
        var targets = 0;
        foreach (var kv in state.Servers)
        {
            if (kv.Key != state.OwnId && kv.Value.Online)
            {
                targets++;
                await state.SendOoc(kv.Key, oocType, payload);
            }
        }
        Console.WriteLine($"[Aowl] {oocType} sent to {targets} server(s): {reason}");
    }
}
