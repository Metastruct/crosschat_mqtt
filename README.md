# Crosschat (mqtt edition) (WIP)

Game server cross-chat via MQTT.

> **Warning**  
> Everything here was written by AI. This is for thinking if it makes any sense.  
> **C# has had the least eyeballs** — it may be buggy or incomplete. Use Python or Lua for anything critical.

## TODO

 - ALL / protocol
   - HIGH: protocol versioning — add `proto_ver` to server meta for compatibility
   - MED: consistent burst encoding — use strings only (`"none"`, `"active"`, etc.) instead of mixing `bool`/`str`
   - MED: remove redundant `server` field from user payload — already implied by MQTT topic
   - MED: keepalive mechanism — application-level ping/pong
   - LOW: standardized error reporting via OOC
 - Lua
   - Server
      - HIGH: private messaging
   - Client
      - HIGH: private messaging command line example
      - HIGH: ooc/oob example of cross server lua execution 
	  - BUG: do not print local player(s)
	  - BUG: fix join/leave burst still appearing
	  - FEAT: Fix gmod/meta scoreboard to accept format with no steamid
 - Python
   - library
      - HIGH: private messaging — ✅ `on_pm` handler wired up
   - webchat frontend
      - FEAT: "scoreboard"
	  - FEAT: actual chat view instead of debug view
      - HIGH: private messaging — ✅ PM UI (click user, send/receive PM)
      - FEAT: client error reporting — ✅ JS errors sent to server, controllable via `webchat.report_client_errors`
	  - HIGH: steam login (and/or discord?)
   - daemon
	  - HIGH: steam login? (where to fetch bans?)
	  - HIGH: Finish PM Interface
      - IDEA: publish chat log stream for website
	  - IDEA: authenticate via JWT to talk via websocket/etc from ingame
	  - IDEA: long poll chat? (vrchat "bridge" https://creators.vrchat.com/worlds/udon/string-loading/ )
	  - Discord/Matrix bridge (if not node.js)
	    - only users who speak become visible
	  - IDEA: IRC "gateway"
	  - BUG: does not shutdown gracefully
	  - test library separation mode 
 - C#
   - library
      - private messaging
      - test integrating with Basis VR, SBox
 - Node
   - Unimplemented
   - discord bridge. Replaces metaconcord bridge: https://github.com/Metastruct/node-metaconcord/
   - https://github.com/Metastruct/node-metaconcord/blob/master/app/services/gamebridge/payloads/ChatPayload.ts
 - Misc
   - FEAT: avatars  
   - BUG: ai smell
   - FEAT: keepalive
   - Python tests — no test suite exists yet
## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Usage

### CLI

```sh
uv run python main.py
uv run python main.py --config config.metatest2.json
uv run python main.py --server-id metatest2 --host 10.0.0.1 -v
```

Connect to the aiomonitor REPL:

```sh
telnet localhost 20103
```

Type `status` to see known servers and their online/users state.

### Library

```python
import asyncio
from crosschat import CrossChat

async def main():
    chat = CrossChat(config='config.json', verbose=True)
    await chat.run()

asyncio.run(main())
```

Create a `CrossChat` instance with a config dict directly:

```python
chat = CrossChat({
    'server_id': 'myserver',
    'mqtt': {'host': '10.0.0.1', 'port': 1883},
})
await chat.run()
```

Override any config value at construction time:

```python
chat = CrossChat(config='config.json', host='10.0.0.2', server_id='metatest2')
```

## Configuration

The config file is a JSON document. Example:

```json
{
	"mqtt": {
		"host": "10.0.0.1",
		"port": 1883
	},
	"server_id": "metatest1",
	"console_host": "0.0.0.0",
	"console_port": 20103,
	"webchat_host": "0.0.0.0",
	"webchat_port": 8765,
	"topic_prefix": "crosschat/",
	"meta": {
		"link": "steam://connect/164.92.180.157:27015/metaweb"
	}
}
```

| Key | Description |
|---|---|---|
| `mqtt.host` / `mqtt.port` | MQTT broker address |
| `server_id` | Unique ID for this server instance |
| `console_host` / `console_port` | aiomonitor REPL listen address |
| `webchat_host` / `webchat_port` | WebSocket webchat server listen address |
| `topic_prefix` | MQTT topic prefix (default `crosschat/`) |
| `webchat.report_client_errors` | Log JS errors from webchat clients (default `true`) |
| `meta` | Arbitrary metadata published as retained `/meta` state |

## Protocol

All topics use the `crosschat/` prefix.

### Topic Structure

All server-to-server messages use the format `m/<from_server>/<to_server>/<type>/<details>`.
The `from_server` is identified by the topic rather than the payload.

### Server Presence

| Topic | Payload | Retained |
|---|---|---|
| `state/<server_id>/status` | `{"started": <unix timestamp>, "version": <proto ver>}` / `{"started": 0, "version": <proto ver>}` | Yes (with LWT) |
| `state/<server_id>/meta` | `{...}` (JSON object) | Yes |

`status` is published on connect with the current unix timestamp and protocol version (`PROTOCOL_VERSION = 1`); broker auto-publishes `{"started": 0}` via Last Will on disconnect.
When a server reconnects with a changed `started` timestamp, a new user burst is triggered.
`meta` is published once on connect with the contents of the `meta` key from config.json.

### Quality of Service

All server-to-server messages (`m/<from>/<to>/...`) and retained state (`state/<server_id>/...`) are published at **QoS 2** (exactly-once delivery) via `CrossChatState.publish()`. This guarantees no duplicates for user sync, messages, and state — critical for correct user tracking across servers.

The Last Will message uses **QoS 1** (at-least-once delivery), since a duplicate offline signal is harmless and the LWT is not resent by the broker.

MQTT subscriptions use broker-default QoS (mapped to the publisher's QoS by the broker).

### Dynamic State

| Topic | Payload | Retained |
|---|---|---|
| `state/<server_id>/<key>` | `"<value>"` (string) | Yes |

Arbitrary key-value pairs published by the server at runtime (e.g. `map`, `gamemode`).
Other servers receive these updates and can react via the subscription API.

### User Burst (on server online)

When a server comes online (or restarts with a new `started` timestamp), each already-online server sends all its local users. Burst metadata is inlined in each user payload rather than sent as separate messages:

| Topic | Payload |
|---|---|
| `m/<from>/<to>/user` | `{"id": <n>, "cmd": "add", "name": "...", "first_seen": "...", "server": "<sid>", "burst": "start" \| true \| "end"}` |

- First user in burst: `"burst": "start"` (`BurstFlag.START`)
- Last user in burst: `"burst": "end"` (`BurstFlag.END`)
- Middle users: `"burst": true` (`BurstFlag.ACTIVE`)
- Single-user burst: `"burst": "startend"` (`BurstFlag.STARTEND`)

The receiver uses `cmd` to distinguish add/update/delete. Inbound burst values are decoded to the `BurstFlag` enum via `BurstFlag.deserialize()`; the `on_user` handler receives a `BurstFlag` parameter.

### User Synchronisation (incremental)

| Topic | Payload |
|---|---|
| `m/<from>/<to>/user` | `{"id": <n>, "cmd": "add" \| "del" \| "update", "name": "...", "first_seen": "...", "server": "<sid>", "burst": false}` (serialized as `BurstFlag.NONE`, decoded to `BurstFlag.NONE` on receipt) |

All user operations share a single topic `m/<from>/<to>/user`. The `cmd` field indicates the action:
- `"add"`: create a new user
- `"del"`: remove a user
- `"update"`: update an existing user

`id` is a per-server auto-incrementing integer starting at 1. Unknown keys in the user payload are stored in `user.extra`. Messages from self are ignored on receipt (matched by `from_server` in topic). User changes are published to each online server individually.

### Messaging

| Topic | Payload |
|---|---|
| `m/<from>/<to>/say/<user_id>` | `{"say": "..."}` |

Sent to each online server (excluding self). On receipt the recipient user is looked up in the local server's user list; if missing a warning is logged.

### Private Messaging

| Topic | Payload |
|---|---|
| `m/<from>/<to>/pm/<from_user_id>/<to_user_id>` | `{"say": "..."}` |

Sent from a specific user on one server to a specific user on another server.
On receipt the handler's `on_pm` callback is invoked with the sender user, target server, target user id, and message.

### Out-of-Character (OOC) Messaging

Servers can exchange arbitrary out-of-band messages via OOC topics:

| Topic | Payload |
|---|---|
| `m/<from>/<to>/ooc/<type>` | `<any JSON value>` |

OOC messages are delivered via `chat.state.subscribe_ooc(type, callback)` and sent via
`chat.state.send_ooc(target_sid, type, payload)` or `server.send_ooc(type, payload)`.

The callback receives `(sender_server: CrossChatServer, payload, ooc_type)`.

```python
# Log remote debug/warning/info messages locally
for level in ('debug', 'warning', 'info'):
    chat.state.subscribe_ooc(level, lambda server, payload, name, _l=level:
        getattr(log, _l)('ooc_log', server_id=server.id, ooc_type=name, payload=payload))
```

### CrossAowl — Remote Admin Actions via OOC

CrossChat supports cross-server admin actions (kick/ban/slap) via OOC messages.
This lets an admin on one server remotely moderate users on another server.

**Two targeting modes:**
- `steamid64` — broadcast to all servers; each GMod server looks up the player by SteamID64
- `server_id + user_id` — broadcast to all servers but only the matching server acts (for webchat/demo users)

| OOC Type | Payload (steamid64 mode) | Payload (targeted mode) |
|---|---|---|
| `aowl_kick` | `{"steamid64": "...", "reason": "...", "extra": {}}` | `{"server_id": "...", "user_id": <n>, "reason": "...", "extra": {}}` |
| `aowl_ban` | (same structure) | (same structure) |
| `aowl_slap` | (same structure) | (same structure) |

**Lua-side (`crossaowl.lua`):**
- Receives `aowl_kick`/`ban`/`slap` with `steamid64` and executes `player:Kick()`, `player:Ban()`, `player:Slap()`.
- Targeted `server_id + user_id` messages are acknowledged but not executed (no webchat users on GMod).
- The `CrossAowlKick`/`CrossAowlBan`/`CrossAowlSlap` hooks are fired before execution for addon integration.

#### Python API

**Sending** — via aiomonitor REPL commands or programmatically:

```python
# Broadcast by steamid64
from crosschat.aowl import _send_cmd
await _send_cmd(state, tg, 'aowl_kick', '76561197986413226', 'spam', {})

# Targeted by server_id + user_id
await _send_cmd(state, tg, 'aowl_slap', {'server_id': 'myserver', 'user_id': 1}, 'being annoying', {})
```

**Receiving** — handled automatically by `CrossChat.run()` which subscribes to `aowl_kick`/`ban`/`slap` OOC types. The handler protocol is:

```python
class CrossChatHandler(Protocol):
    async def on_user(self, user: CrossChatUser, cmd: str, burst: BurstFlag = BurstFlag.NONE) -> None: ...
    async def on_say(self, user: CrossChatUser, say: str) -> None: ...
    # Plus on_pm, on_server_add, on_server_del, on_server_status (see full API)
```

When a kick/ban with `user_id` is received, `state.del_user(user_id)` is called followed by `handler.on_user(user, 'del')`. When a slap is received, the user says `"ow"` via `handler.on_say(user, 'ow')` and the say is broadcast to all servers.

**Custom handling** — subscribe to aowl OOC types directly:

```python
async def on_aowl_kick(server: CrossChatServer, payload: str, ooc_type: str):
    data = json.loads(payload)
    print(f"Kick from {server.id}: {data}")

chat.state.subscribe_ooc('aowl_kick', on_aowl_kick)
```

#### C# API

**Sending** — via the static `Aowl` class (`csharp/Aowl.cs`):

```csharp
// Broadcast by steamid64
await Aowl.Kick(state, "76561197986413226", "spam");
await Aowl.Ban(state, "76561197986413226", "griefing");
await Aowl.Slap(state, "76561197986413226", "being annoying");

// Targeted by server_id + user_id
await Aowl.KickUser(state, "myserver", 1, "spam");
await Aowl.BanUser(state, "myserver", 1, "griefing");
await Aowl.SlapUser(state, "myserver", 1, "being annoying");
```

**Receiving** — handled automatically by `CrossChatHost.RunAsync()` which subscribes to `aowl_kick`/`ban`/`slap` OOC types. The `ICrossChatHandler` interface is:

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

When a kick/ban with `user_id` is received, `State.DelUser(userId)` is called followed by `handler.OnUser(user, "del")`. When a slap is received, the user says `"ow"` via `handler.OnSay(user, "ow")` and the say is broadcast to all servers.

### CrossLua — Remote Lua Execution via OOC

CrossChat supports remote Lua code execution across servers via the `lua` OOC type.
This is **extremely dangerous** — it gives the sender full server-side code execution
on the target machine.

| Topic | Payload |
|---|---|
| `m/<from>/<to>/ooc/lua` | `{"id": <n>, "code": "<lua code>", "steamid": "<sender>"}` |
| `m/<from>/<to>/ooc/lua_reply` | `{"id": <n>, "result": "<output or error>"}` |

**Lua-side (`crosslua.lua`)**:
- The `lua_allow_remote` convar (default `1`) gates incoming execution.
- Commands: `cl <code>` (broadcast), `bl <code>` (broadcast + execute locally),
  `cl<ID> <code>` (target specific server).
- Only developers (aowl group) can use these commands.

**Python-side (aiomonitor REPL)**:
| Command | Description |
|---|---|
| `sendlua <server_id> <code>` | Send Lua code to a server. Replies print asynchronously. |

> **Warning** — Remote Lua execution is equivalent to giving shell access.  
> Only enable `lua_allow_remote` on trusted networks. All servers on the same  
> MQTT broker can send code to each other. There is no sandbox — code runs  
> with full server privileges. The `easylua` module (if installed) provides  
> some sandboxing but should not be relied upon for security.

### Subscription

Servers subscribe to the following topics:

| Subscription | Purpose |
|---|---|
| `state/+/#` | Receive server presence, metadata, and dynamic state updates |
| `m/+/<own_server_id>/#` | Receive all messages, user sync, bursts, and OOC destined for this server |

Unknown endpoints under `m/+/<own_server_id>/` are logged as warnings.

## CrossChat API

The `CrossChat` class wraps the full lifecycle and exposes `CrossChatState` as `chat.state`:

| Method / Attribute | Description |
|---|---|
| `CrossChat(config, *, host, port, server_id, console_port, verbose, handler)` | Create instance. `config` can be a dict, file path, or `None` for all-defaults. Keyword args override config values. Optional `handler` receives `on_user(user, cmd, burst)`, `on_say(user, say)`, `on_server_add(server)`, `on_server_del(server)`, and `on_server_status(server)` callbacks. |
| `chat.state` | The underlying `CrossChatState` instance |
| `await chat.run()` | Connect to MQTT, publish state, listen for messages, start aiomonitor console |
| `await chat.listen_messages(client, tg)` | Subscribe to MQTT topics and process incoming messages in a task group |
| `chat.load_config(path)` | Load JSON config from file |
| `chat.setup_logging(verbose)` | Configure structlog (called automatically by `run()`) |

### CrossChatState

The `CrossChatState` object provides helpers for dynamic state, OOC, user, and publish management, accessible via `chat.state`:

| Method | Description |
|---|---|
| `chat.state.set_state(key, value)` | Set own state, publish retained `state/<sid>/<key>` to MQTT, and notify subscribers |
| `chat.state.subscribe(key, callback)` | Register `async def cb(server: CrossChatServer, key: str, value: str)` for state changes on any server |
| `chat.state.get_meta()` | Return own metadata dict |
| `chat.state.set_meta(meta)` | Set own metadata (called automatically from config on startup) |
| `chat.state.set_client(client, prefix)` | Wire up MQTT client and topic prefix; without this, `set_state` operates in-memory only |
| `chat.state.publish(topic, payload, qos=2, retain=False)` | Publish to `{prefix}{topic}`; non-string payloads are JSON-encoded automatically |
| `chat.state.add_user(name, extra=None)` | Add a local user and broadcast to all online servers (delegates to `server.add_user`) |
| `chat.state.del_user(user_id)` | Remove a local user and broadcast removal (delegates to `server.del_user`) |
| `chat.state.subscribe_ooc(type, callback)` | Register `async def cb(server: CrossChatServer, payload, type: str)` for OOC messages |
| `chat.state.send_ooc(target_sid, type, payload)` | Send an OOC message to another server |
| `server.send_ooc(type, payload)` | Convenience wrapper; sends to `server.id` via the owning state |

### CrossChatServer

The `CrossChatServer` class exposes user management with built-in broadcast:

| Method | Description |
|---|---|
| `server.add_user(name, extra=None)` | Create a user on this server, assign an auto-incrementing id, and broadcast to all online servers |
| `server.del_user(user_id)` | Remove a user by id and broadcast the removal |
| `server.send_ooc(type, payload)` | Send an OOC message to this server |
| `server.get_user(id, create=False, ensure=False)` | Look up a user by id, optionally creating a placeholder |

### Example

```python
chat.state.set_state('map', 'gm_construct')

async def on_map_change(server, key, value):
    print(f'{server.id} changed {key} to {value}')

chat.state.subscribe('map', on_map_change)
```

All callbacks are dispatched as `asyncio.Task` and receive the originating `CrossChatServer` instance, the state key, and the new value.

The `CrossChatUser` class provides a `serialize()` method that returns a JSON-serializable dict. Extra keys received in the payload are stored in `user.extra` as a dict.

## Commands (aiomonitor REPL)

| Command | Description |
|---|---|
| `status` | Show known servers and their online/users state |
| `add <name>` | Add a local user (auto-generated id) and broadcast to all servers |
| `del <id>` | Remove a local user and broadcast removal |
| `say <userid> <message>` | Send a message to a user on all online servers |
| `pm <from_user_id> <target_server_id> <to_user_id> <message>` | Send a private message from a local user to a user on another server |
| `aowl_kick <steamid64> [reason]` | Kick player by SteamID64 (broadcast) |
| `aowl_ban <steamid64> [reason]` | Ban player by SteamID64 (broadcast) |
| `aowl_slap <steamid64> [reason]` | Slap player by SteamID64 (broadcast) |
| `aowl_kick_user <server_id> <user_id> [reason]` | Kick user by server+userid (targeted) |
| `aowl_ban_user <server_id> <user_id> [reason]` | Ban user by server+userid (targeted) |
| `aowl_slap_user <server_id> <user_id> [reason]` | Slap user by server+userid (targeted) |

## C# Implementation

A C# implementation using MQTTnet is available in [`csharp/`](csharp/).

### Requirements

- [.NET 10 SDK](https://dotnet.microsoft.com/en-us/download/dotnet/10.0)
- MQTT broker (e.g. Mosquitto, EMQX)

### CLI Usage

```sh
cd csharp/
dotnet run -- --config ../config.json
dotnet run -- --config ../config.json --host 10.0.0.1
dotnet run -- --server-id myserver --host 10.0.0.1 -v
```

The REPL supports the same commands as the Python version:

```
> status                     Show known servers and users
> add Alice                  Add a local user
> del 1                      Remove a local user
> say 1 hello                Send chat message from user
> pm 1 eu2 2 hi              Send private message
> sendlua eu2 print('hi')    Send Lua code via OOC (replies print asynchronously)
> aowl_kick 76561197986413226 hmm    Kick player by SteamID64
> aowl_kick_user myserver 1 bye      Kick user by server+userid
> exit                       Shutdown
```

## Lua (Garry's Mod) Implementation

A Garry's Mod Lua implementation is available in
[`crosschat_lua/`](crosschat_lua/). It uses the `mosquitto` Garry's Mod module
for MQTT communication and the same topic/payload protocol as the Python
reference server. See the [`crosschat_lua/README.md`](crosschat_lua/README.md)
for installation and configuration details.
