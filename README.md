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

### Server Presence

| Topic | Payload | Retained |
|---|---|---|
| `state/<server_id>/online` | `"online"` / `"offline"` | Yes (with LWT) |

Published on connect; broker auto-publishes `"offline"` via Last Will on disconnect.

### User Synchronisation

| Topic | Payload |
|---|---|
| `m/all/user/<seq>` | `{"id": "...", "name": "...", "seq": <int>, "server_id": "..."}` |
| `m/all/user/<seq>/remove` | `{"id": "...", "server_id": "..."}` |

`seq` is a per-server auto-incrementing integer starting at 1. The `server_id` field identifies the origin server. Messages from self are ignored on receipt.

### Messaging

| Topic | Payload |
|---|---|
| `m/<target_server_id>/msg/<user_id>` | `{"msg": "..."}` |

Sent to all online servers (excluding self). On receipt the recipient user is looked up in the local server's user list; if missing a warning is logged.

## Commands (aiomonitor REPL)

| Command | Description |
|---|---|
| `status` | Show known servers and their online/users state |
| `add <id> <name>` | Add a local user and broadcast to all servers |
| `del <id>` | Remove a local user and broadcast removal |
| `msg <userid> <message>` | Send a message to a user on all online servers |
