# crosschat-csharp

Cross-server chat via MQTT — C# implementation using MQTTnet.
Compatible with the [crosschat-python](https://github.com/Metastruct/crosschat_mqtt)
reference server and the Lua Garry's Mod implementation.

## Requirements

- [.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)
- MQTT broker (e.g. Mosquitto, EMQX)

## CLI Usage

```sh
dotnet run -- --config ../config.json
dotnet run -- --config ../config.json --host 10.0.0.1
dotnet run -- --server-id myserver --host 10.0.0.1 -v
```

### REPL Commands

```
> status                     Show known servers and users
> add Alice                  Add a local user
> del 1                      Remove a local user
> say 1 hello                Send chat message from user
> pm 1 eu2 2 hi              Send private message
> sendlua eu2 print('hi')    Send Lua code via OOC
> aowl_kick 76561197986413226 hmm    Kick player by SteamID64
> aowl_kick_user myserver 1 bye      Kick user by server+userid
> exit                       Shutdown
```

## Files

| File | Purpose |
|------|---------|
| `CrossChat.cs` | Main host: config, MQTT lifecycle, message routing, REPL |
| `State.cs` | `CrossChatState`: server/user management, OOC, publish |
| `Models.cs` | Data models: `CrossChatUser`, `CrossChatServer`, `BurstFlag`, `ICrossChatHandler` |
| `Aowl.cs` | Remote admin actions: kick/ban/slap |

## ICrossChatHandler

Implement this interface to receive events from the CrossChat host:

```csharp
public interface ICrossChatHandler
{
    Task OnUser(CrossChatUser user, string cmd, BurstFlag burst = BurstFlag.None);
    Task OnSay(CrossChatUser user, string say);
    Task OnPm(CrossChatUser sender, string targetServerId, int targetUserId, string say);
    Task OnServerAdd(CrossChatServer server);
    Task OnServerDel(CrossChatServer server);
    Task OnServerStatus(CrossChatServer server);
}
```

Pass it to the `CrossChatHost` constructor:

```csharp
var handler = new MyHandler();
var host = new CrossChatHost(config: "config.json", handler: handler);
await host.RunAsync();
```

## Aowl — Remote Admin Actions

The static `Aowl` class provides cross-server kick/ban/slap.
Messages are broadcast to all online servers. Two targeting modes:

### By SteamID64 (broadcast — all GMod servers act)

```csharp
await Aowl.Kick(state, "76561197986413226", "spam");
await Aowl.Ban(state, "76561197986413226", "griefing");
await Aowl.Slap(state, "76561197986413226", "being annoying");
```

### By server_id + user_id (targeted — only matching server acts)

```csharp
await Aowl.KickUser(state, "myserver", 1, "spam");
await Aowl.BanUser(state, "myserver", 1, "griefing");
await Aowl.SlapUser(state, "myserver", 1, "being annoying");
```

### Receiving

The host automatically subscribes to `aowl_kick`/`ban`/`slap` OOC types:
- `aowl_kick` / `aowl_ban` with `user_id` → calls `State.DelUser(userId)` then `handler.OnUser(user, "del")`
- `aowl_slap` with `user_id` → broadcasts `say` with text `"ow"` then `handler.OnSay(user, "ow")`

## CrossChatState API

| Method | Description |
|--------|-------------|
| `state.AddUser(name, extra?)` | Add a local user and broadcast to all servers |
| `state.DelUser(userId)` | Remove a local user and broadcast removal |
| `state.SendOoc(targetSid, oocName, payload)` | Send an OOC message to another server |
| `state.SubscribeOoc(oocName, callback)` | Register for incoming OOC messages |
| `state.Publish(topic, payload, qos=2, retain=false)` | Publish to MQTT |
| `state.SetState(key, value)` | Publish retained dynamic state |
| `state.FormatStatus()` | Get formatted server/user status string |

## Configuration

```json
{
    "mqtt": { "host": "10.0.0.1", "port": 1883 },
    "server_id": "metatest1",
    "meta": { "link": "steam://connect/..." }
}
```

| Key | Description |
|-----|-------------|
| `mqtt.host` / `mqtt.port` | MQTT broker address |
| `server_id` | Unique server ID |
| `topic_prefix` | MQTT topic prefix (default `crosschat/`) |
| `meta` | Arbitrary metadata (published as retained `/meta` state) |
