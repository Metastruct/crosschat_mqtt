# Crosschat (mqtt edition) (WIP)

Game server cross-chat via MQTT.
Everything was written by AI, sorry. This is for thinking if it makes any sense.

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

**⚠️ WARNING**: Remote Lua execution is equivalent to giving shell access.
Only enable `lua_allow_remote` on trusted networks. All servers on the same
MQTT broker can send code to each other. There is no sandbox — code runs
with full server privileges. The `easylua` module (if installed) provides
some sandboxing but should not be relied upon for security.

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
> exit                       Shutdown
```

## Lua (Garry's Mod) Implementation

A Garry's Mod Lua implementation is available in
[`crosschat_lua/`](crosschat_lua/). It uses the `mosquitto` Garry's Mod module
for MQTT communication and the same topic/payload protocol as the Python
reference server. See the [`crosschat_lua/README.md`](crosschat_lua/README.md)
for installation and configuration details.
