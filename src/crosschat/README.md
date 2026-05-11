# crosschat-python

Cross-server chat via MQTT — Python reference library.
Compatible with the C# and Lua Garry's Mod implementations.

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Structure

| Module | Purpose |
|--------|---------|
| `crosschat.py` | `CrossChat` class: lifecycle, MQTT message routing, OOC dispatch |
| `state.py` | `CrossChatState`: server/user management, OOC, publish/subscribe |
| `models.py` | Data models: `CrossChatUser`, `CrossChatServer`, `BurstFlag`, `CrossChatHandler` (protocol) |
| `aowl.py` | Remote admin CLI commands + send helper |
| `monitor_ext.py` | aiomonitor REPL extensions (status, add, del, say, pm, sendlua) |

## CrossChat API

```python
from crosschat import CrossChat

chat = CrossChat(config='config.json', verbose=True)
await chat.run()
```

### Constructor

```python
CrossChat(
    config: dict | str | Path | None = None,
    *,
    host: str | None = None,
    port: int | None = None,
    server_id: str | None = None,
    console_port: int | None = None,
    verbose: bool = False,
    handler: CrossChatHandler | None = None,
)
```

| Parameter | Description |
|-----------|-------------|
| `config` | Config dict, JSON file path, or `None` for defaults |
| `host` / `port` | Override MQTT broker address |
| `server_id` | Override server ID |
| `console_port` | aiomonitor REPL port (default from config) |
| `verbose` | Enable debug logging |
| `handler` | Optional `CrossChatHandler` for user/say/server events |

### CrossChatHandler Protocol

```python
class CrossChatHandler(Protocol):
    async def on_user(self, user: CrossChatUser, cmd: str, burst: BurstFlag = BurstFlag.NONE) -> None: ...
    async def on_say(self, user: CrossChatUser, say: str) -> None: ...
    async def on_pm(self, sender: CrossChatUser, target_server_id: str, target_user_id: int, say: str) -> None: ...
    async def on_server_add(self, server: CrossChatServer) -> None: ...
    async def on_server_del(self, server: CrossChatServer) -> None: ...
    async def on_server_status(self, server: CrossChatServer) -> None: ...
```

### CrossChatState

Accessible as `chat.state`:

| Method | Description |
|--------|-------------|
| `state.add_user(name, extra=None)` | Add local user, broadcast to all servers |
| `state.del_user(user_id)` | Remove local user, broadcast removal |
| `state.send_ooc(target_sid, ooc_name, payload)` | Send OOC message to a server |
| `state.subscribe_ooc(ooc_name, callback)` | Receive incoming OOC messages |
| `state.publish(topic, payload, qos=2, retain=False)` | Publish to MQTT |
| `state.set_state(key, value)` | Publish retained dynamic state |
| `state.set_status(sid, started)` | Update server online status |
| `state.format_status(full=False)` | Get formatted server/user status string |

## Aowl — Remote Admin Actions

### Sending via REPL

```
aowl_kick <steamid64> [reason]         Broadcast kick by SteamID64
aowl_ban <steamid64> [reason]          Broadcast ban by SteamID64
aowl_slap <steamid64> [reason]         Broadcast slap by SteamID64
aowl_kick_user <sid> <uid> [reason]    Kick user by server+userid
aowl_ban_user <sid> <uid> [reason]     Ban user by server+userid
aowl_slap_user <sid> <uid> [reason]    Slap user by server+userid
```

### Sending programmatically

```python
from crosschat.aowl import _send_cmd

# By SteamID64 (broadcast)
await _send_cmd(state, tg, 'aowl_kick', '76561197986413226', 'spam', {})

# By server_id + user_id (targeted — broadcast but only matching server acts)
await _send_cmd(state, tg, 'aowl_slap', {'server_id': 'myserver', 'user_id': 1}, 'being annoying', {})
```

### Receiving (automatic)

The `CrossChat.run()` method subscribes to `aowl_kick`/`ban`/`slap` OOC types:
- `aowl_kick` / `aowl_ban` with `user_id` → calls `state.del_user(user_id)` then `handler.on_user(user, 'del')`
- `aowl_slap` with `user_id` → broadcasts a `say` with text `"ow"` and calls `handler.on_say(user, 'ow')`

### Custom OOC handlers

```python
async def on_aowl_kick(server: CrossChatServer, payload: str, ooc_type: str):
    data = json.loads(payload)
    print(f'{ooc_type} from {server.id}: {data}')

chat.state.subscribe_ooc('aowl_kick', on_aowl_kick)
```

## REPL Commands

Available via aiomonitor (`telnet localhost 20103`):

| Command | Description |
|---------|-------------|
| `status` | Show known servers and users |
| `add <name>` | Add a local user and broadcast |
| `del <id>` | Remove a local user |
| `say <uid> <msg>` | Send chat message from user |
| `pm <from> <sid> <to> <msg>` | Send private message |
| `sendlua <sid> <code>` | Send Lua code via OOC |
| `aowl_kick <sid64> [reason]` | Kick by SteamID64 |
| `aowl_ban <sid64> [reason]` | Ban by SteamID64 |
| `aowl_slap <sid64> [reason]` | Slap by SteamID64 |
| `aowl_kick_user <sid> <uid> [r]` | Kick by server+userid |
| `aowl_ban_user <sid> <uid> [r]` | Ban by server+userid |
| `aowl_slap_user <sid> <uid> [r]` | Slap by server+userid |
| `exit` / `quit` | Shutdown |
