import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

from crosschat.models import BurstFlag, CrossChatServer, CrossChatUser

app = FastAPI()
app.state.ws_clients: set[WebSocket] = set()


class WebchatHandler:
	def __init__(self, fastapi_app: FastAPI) -> None:
		self._app = fastapi_app

	async def _broadcast(self, payload: dict) -> None:
		text = json.dumps(payload)
		for ws in list(self._app.state.ws_clients):
			try:
				await ws.send_text(text)
			except Exception:
				self._app.state.ws_clients.discard(ws)

	async def on_user(self, user: CrossChatUser, cmd: str, burst: BurstFlag = BurstFlag.NONE) -> None:
		await self._broadcast({'cmd': 'user', 'user': user.serialize(), 'action': cmd})

	async def on_msg(self, user: CrossChatUser, msg: str) -> None:
		await self._broadcast({'cmd': 'msg', 'user': user.serialize(), 'msg': msg})

	async def on_server_add(self, server: CrossChatServer) -> None:
		await self._broadcast({'cmd': 'server_add', 'id': server.id})

	async def on_server_del(self, server: CrossChatServer) -> None:
		await self._broadcast({'cmd': 'server_del', 'id': server.id})

	async def on_server_status(self, server: CrossChatServer) -> None:
		await self._broadcast({
			'cmd': 'server_status', 'id': server.id,
			'online': server.online, 'started': server.started,
		})


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket) -> None:
	await ws.accept()
	app.state.ws_clients.add(ws)

	state = ws.app.state.crosschat.state
	servers = [
		{
			'id': sid,
			'online': srv.online,
			'started': srv.started,
			'meta': srv.meta,
			'states': srv.states,
			'users': [
				{'id': uid, **user.serialize()}
				for uid, user in srv.users.items()
			],
		}
		for sid, srv in state.servers.items()
	]
	await ws.send_text(json.dumps({'cmd': 'server_list', 'servers': servers}))

	user_id: int | None = None
	handler: WebchatHandler = ws.app.state.handler

	try:
		while True:
			raw = await ws.receive_text()
			payload = json.loads(raw)
			cmd = payload.get('cmd')

			if cmd == 'echo':
				await ws.send_text(json.dumps({'cmd': 'echo_reply', 'i': payload.get('i', 0)}))

			elif cmd == 'join':
				name = payload.get('name', '')
				if not name:
					await ws.send_text(json.dumps({'cmd': 'error', 'msg': 'name required'}))
					continue
				uid = await state.add_user(name)
				user_id = uid
				await ws.send_text(json.dumps({'cmd': 'joined', 'user_id': uid, 'name': name}))
				user = state.servers[state._own_id].users[uid]
				await handler.on_user(user, 'add')

			elif cmd == 'msg':
				if user_id is None:
					await ws.send_text(json.dumps({'cmd': 'error', 'msg': 'must join first'}))
					continue
				msg_text = payload.get('msg', '')
				if not msg_text:
					await ws.send_text(json.dumps({'cmd': 'error', 'msg': 'msg required'}))
					continue
				for sid, srv in state.servers.items():
					if sid != state._own_id and srv.online:
						await state.publish(
							f'm/{state._own_id}/{sid}/msg/{user_id}',
							payload=json.dumps({'msg': msg_text}),
						)
				user = state.servers[state._own_id].users[user_id]
				await handler.on_msg(user, msg_text)
				await ws.send_text(json.dumps({'cmd': 'msg_sent'}))

			else:
				await ws.send_text(json.dumps({'cmd': 'error', 'msg': f'unknown cmd: {cmd}'}))
	except Exception:
		pass
	finally:
		app.state.ws_clients.discard(ws)


static_dir = Path(__file__).resolve().parent / 'static'
if static_dir.is_dir():
	app.mount('/', StaticFiles(directory=str(static_dir), html=True), name='static')
