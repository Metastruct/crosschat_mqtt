# crosschat-lua

Cross-server chat for Garry's Mod via MQTT.

This is the **Garry's Mod Lua** implementation of the CrossChat protocol,
compatible with the [crosschat-python](https://github.com/anomalyco/crosschat_python)
reference server.

## Architecture

```
   GMOD Server A  <--->  MQTT Broker  <--->  GMOD Server B
         |                                       |
   GMOD Clients                            GMOD Clients
```

Servers communicate through an MQTT broker. No direct server-to-server TCP.
Each server publishes its state and users to MQTT topics and subscribes to
messages from other servers. Local players are forwarded to/from remote servers
via Garry's Mod net messages.

## Files

| Path | Purpose |
|------|---------|
| `lua/autorun/server/crosschat.lua` | Main server module: config, MQTT integration, hooks, net messages |
| `lua/autorun/server/meta_mqtt.lua` | MQTT client library (mosquitto bindings) |
| `lua/autorun/client/crosschat_cl.lua` | Client-side net message handlers, chat UI |
| `lua/autorun/client/chat_teams.lua` | Team definitions for chat colours |
| `src/crosschat/init.lua` | Source entry point |
| `src/crosschat/models.lua` | Data structures: `CrossChatUser`, `CrossChatServer`, `BurstFlag` |
| `src/crosschat/protocol.lua` | Topic parsing, payload serialization helpers |
| `src/crosschat/state.lua` | State management (`CrossChatState`) |
| `cfg/crosschat.json` | Server configuration (not included, see below) |

## Requirements

- Garry's Mod server
- [mosquitto](https://github.com/ANormaly/gm_mosquitto) Garry's Mod module
- MQTT broker (e.g. Mosquitto, EMQX)

## Installation

1. Copy the `lua/` directory to your Garry's Mod server's `garrysmod/addons/` or `garrysmod/lua/`.
2. Install the `mosquitto` module on your server.
3. Create `garrysmod/data/cfg/crosschat.json`:

```json
{
	"server_id": "myserver",
	"topic_prefix": "crosschat/",
	"mqtt": {
		"host": "10.0.0.1",
		"port": 1883,
		"username": "",
		"password": ""
	},
	"meta": {
		"link": "steam://connect/YOUR_IP:27015"
	}
}
```

### MQTT Broker Configuration

If using Mosquitto, create `/etc/mosquitto/conf.d/crosschat.conf`:

```
listener 1883 0.0.0.0
allow_anonymous true
```

## Protocol

All topics use the configurable prefix (default `crosschat/`).

### Topic Structure

```
crosschat/
  state/<server_id>/status   -- {"started": <unix_ts>} (retained, LWT)
  state/<server_id>/meta     -- {<arbitrary json>} (retained)
  state/<server_id>/<key>    -- "<value>" (retained, dynamic state)
  m/<from>/<to>/user         -- user add/del/update + burst flag
  m/<from>/<to>/say/<uid>    -- {"say": "..."}
  m/<from>/<to>/pm/<fuid>/<tuid>  -- {"say": "..."}
  m/<from>/<to>/ooc/<type>   -- any JSON value
```

### User Burst

When a server comes online, each online server sends all its local users
with a `burst` field in the payload:

| Burst Value | Meaning |
|-------------|---------|
| `"start"` | First user in burst |
| `true` | Middle user |
| `"end"` | Last user |
| `"startend"` | Only user |

### User Payload

```json
{
	"id": 1,
	"cmd": "add",
	"name": "PlayerName",
	"first_seen": 1712345678,
	"server": "myserver",
	"burst": false,
	"steamid64": "76561197960265728",
	"team": 1,
	"<extra_field>": "<value>"
}
```

### Subscriptions

Each server subscribes to:
- `crosschat/state/+/#` - all server state
- `crosschat/m/+/<own_id>/#` - messages destined for this server

## Hooks

The server module hooks into:
- `PlayerInitialSpawn` - broadcast new player to all servers
- `PlayerSay` - broadcast chat messages
- `PlayerDisconnected` - broadcast player leave
- `OnMQTT` - receive MQTT messages

Client-side hooks available:
- `CPlayerData(playerdata, old_data)` - when player data is received/updated
- `CrossChatSay(ServerID, UserID, text, player)` - when a crosschat message arrives

## Client Commands

| Command | Description |
|---------|-------------|
| `statusall` | Show all known players across all servers |
| `crosschat_show` | Client convar: show/hide crosschat messages (default 1) |
| `crosschat_svname` | Client convar: show/hide server name prefix (default 1) |
| `crosschat_postfix` | Client convar: show server name after message (default 0) |

## Source Modules

The `src/crosschat/` directory contains a reusable Lua implementation of
the protocol, mirroring the Python `src/crosschat/` package structure:

- **models.lua**: `CrossChatUser`, `CrossChatServer`, `BurstFlag` data types
- **protocol.lua**: Topic parsing, payload building, serialization helpers
- **state.lua**: `CrossChatState` class managing server/user state
