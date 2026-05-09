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

## Protocol

All topics use the `crosschat/` prefix.

### Topic Structure

All server-to-server messages use the format `m/<from_server>/<to_server>/<type>/<details>`.
The `from_server` is identified by the topic rather than the payload.

### Server Presence

| Topic | Payload | Retained |
|---|---|---|
| `state/<server_id>/online` | `"online"` / `"offline"` | Yes (with LWT) |

Published on connect; broker auto-publishes `"offline"` via Last Will on disconnect.

### User Burst (on server online)

When a server comes online, each already-online server sends all its local users in a burst:

| Topic | Payload |
|---|---|
| `m/<from>/<to>/burst/start` | `{}` |
| `m/<from>/<to>/user/<seq>` | `{"id": <seq>, "name": "..."}` |
| `m/<from>/<to>/burst/end` | `{}` |

### User Synchronisation (incremental)

| Topic | Payload |
|---|---|
| `m/<from>/<to>/user/<seq>` | `{"id": <seq>, "name": "..."}` |
| `m/<from>/<to>/user/<seq>/remove` | `{"id": <seq>}` |

`seq` is a per-server auto-incrementing integer starting at 1. Messages from self are ignored on receipt (matched by `from_server` in topic). User add/remove are published to each online server individually.

### Messaging

| Topic | Payload |
|---|---|
| `m/<from>/<to>/msg/<user_id>` | `{"msg": "..."}` |

Sent to each online server (excluding self). On receipt the recipient user is looked up in the local server's user list; if missing a warning is logged.

### Subscription

Servers subscribe to the following topics:

| Subscription | Purpose |
|---|---|
| `state/+/online` | Detect server presence changes |
| `m/+/<own_server_id>/#` | Receive all messages, user sync, and bursts destined for this server |

Unknown endpoints under `m/+/<own_server_id>/` are logged as warnings.

## Commands (aiomonitor REPL)

| Command | Description |
|---|---|
| `status` | Show known servers and their online/users state |
| `add <name>` | Add a local user (auto-generated id) and broadcast to all servers |
| `del <id>` | Remove a local user and broadcast removal |
| `msg <userid> <message>` | Send a message to a user on all online servers |
