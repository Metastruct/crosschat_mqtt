# crosschat-python

Game server cross-chat via MQTT.

## Requirements

- Python >= 3.14
- [uv](https://docs.astral.sh/uv/getting-started/installation/)

## Usage

```sh
PYTHONPATH=src uv run python -m crosschat.main
PYTHONPATH=src uv run python -m crosschat.main --config config.metatest2.json
PYTHONPATH=src uv run python -m crosschat.main --server-id metatest2 --host 10.0.0.1 -v
```

Connect to the aiomonitor REPL:

```sh
telnet localhost 20103
```

Type `status` to see known servers and their online/users state.

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
	"topic_prefix": "crosschat/",
	"meta": {
		"link": "steam://connect/164.92.180.157:27015/metaweb"
	}
}
```

| Key | Description |
|---|---|
| `mqtt.host` / `mqtt.port` | MQTT broker address |
| `server_id` | Unique ID for this server instance |
| `console_host` / `console_port` | aiomonitor REPL listen address |
| `topic_prefix` | MQTT topic prefix (default `crosschat/`) |
| `meta` | Arbitrary metadata published as retained `/meta` state |

## Protocol

All topics use the `crosschat/` prefix.

### Topic Structure

All server-to-server messages use the format `m/<from_server>/<to_server>/<type>/<details>`.
The `from_server` is identified by the topic rather than the payload.

### Server Presence

| Topic | Payload | Retained |
|---|---|---|
| `state/<server_id>/online` | `"online"` / `"offline"` | Yes (with LWT) |
| `state/<server_id>/meta` | `{...}` (JSON object) | Yes |

`online` is published on connect; broker auto-publishes `"offline"` via Last Will on disconnect.
`meta` is published once on connect with the contents of the `meta` key from config.json.

### Dynamic State

| Topic | Payload | Retained |
|---|---|---|
| `state/<server_id>/<key>` | `"<value>"` (string) | Yes |

Arbitrary key-value pairs published by the server at runtime (e.g. `map`, `gamemode`).
Other servers receive these updates and can react via the subscription API.

### User Burst (on server online)

When a server comes online, each already-online server sends all its local users in a burst:

| Topic | Payload |
|---|---|
| `m/<from>/<to>/burst/start` | `{}` |
| `m/<from>/<to>/user/<id>` | `{"name": "...", "first_seen": "...", "server": "<sid>"}` |
| `m/<from>/<to>/burst/end` | `{"user_count": <n>}` |

The `user_count` in burst end lets the receiver verify all users were received; a warning is logged on mismatch. Failure to publish a burst sends an OOC `error` to the target server.

### User Synchronisation (incremental)

| Topic | Payload |
|---|---|
| `m/<from>/<to>/user/<id>` | `{"name": "...", "first_seen": "...", "server": "<sid>"}` |
| `m/<from>/<to>/user/<id>/remove` | `{}` |

`id` is a per-server auto-incrementing integer starting at 1. The user's `id` is conveyed by the topic, not the payload. Unknown keys in the user payload are stored in `user.extra`. Messages from self are ignored on receipt (matched by `from_server` in topic). User add/remove are published to each online server individually.

### Messaging

| Topic | Payload |
|---|---|
| `m/<from>/<to>/msg/<user_id>` | `{"msg": "..."}` |

Sent to each online server (excluding self). On receipt the recipient user is looked up in the local server's user list; if missing a warning is logged.

### Out-of-Character (OOC) Messaging

Servers can exchange arbitrary out-of-band messages via OOC topics:

| Topic | Payload |
|---|---|
| `m/<from>/<to>/ooc/<type>` | `<any JSON value>` |

OOC messages are delivered via `state.subscribe_ooc(type, callback)` and sent via
`state.send_ooc(target_sid, type, payload)` or `server.send_ooc(type, payload)`.

The callback receives `(sender_server: CrossChatServer, payload, ooc_type)`.

```python
# Log remote debug/warning/info messages locally
for level in ('debug', 'warning', 'info'):
    state.subscribe_ooc(level, lambda server, payload, name, _l=level:
        getattr(log, _l)('ooc_log', server_id=server.id, ooc_type=name, payload=payload))
```

### Subscription

Servers subscribe to the following topics:

| Subscription | Purpose |
|---|---|
| `state/+/#` | Receive server presence, metadata, and dynamic state updates |
| `m/+/<own_server_id>/#` | Receive all messages, user sync, bursts, and OOC destined for this server |

Unknown endpoints under `m/+/<own_server_id>/` are logged as warnings.

## State API

The `CrossChatState` object provides helpers for dynamic state and OOC management:

| Method | Description |
|---|---|
| `state.set_state(key, value)` | Set own state, publish retained `state/<sid>/<key>` to MQTT, and notify subscribers |
| `state.subscribe(key, callback)` | Register `async def cb(server: CrossChatServer, key: str, value: str)` for state changes on any server |
| `state.get_meta()` | Return own metadata dict |
| `state.set_meta(meta)` | Set own metadata (called automatically from config on startup) |
| `state.set_client(client, prefix)` | Wire up MQTT client; without this, `set_state` operates in-memory only |
| `state.subscribe_ooc(type, callback)` | Register `async def cb(server: CrossChatServer, payload, type: str)` for OOC messages |
| `state.send_ooc(target_sid, type, payload)` | Send an OOC message to another server |
| `server.send_ooc(type, payload)` | Convenience wrapper; sends to `server.id` via the owning state |

### Example

```python
state.set_state("map", "gm_construct")

async def on_map_change(server, key, value):
    print(f"{server.id} changed {key} to {value}")

state.subscribe("map", on_map_change)
```

All callbacks are dispatched as `asyncio.Task` and receive the originating `CrossChatServer` instance, the state key, and the new value.

The `CrossChatUser` class provides a `serialize()` method that returns a JSON-serializable dict (without `id`, which is conveyed by the MQTT topic). Extra keys received in the payload are stored in `user.extra` as a dict.

## Commands (aiomonitor REPL)

| Command | Description |
|---|---|
| `status` | Show known servers and their online/users state |
| `add <name>` | Add a local user (auto-generated id) and broadcast to all servers |
| `del <id>` | Remove a local user and broadcast removal |
| `msg <userid> <message>` | Send a message to a user on all online servers |
