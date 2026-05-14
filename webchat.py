import json
import sys
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from fastapi import FastAPI, WebSocket
from starlette.websockets import WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from crosschat.models import BurstFlag, CrossChatServer, CrossChatUser

log = structlog.get_logger()

app = FastAPI()
app.state.ws_clients: set[WebSocket] = set()
app.state.ws_users: dict[int, WebSocket] = {}


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

	async def on_user(self, user: CrossChatUser, cmd: str, burst: BurstFlag = BurstFlag.NONE, reason: str = '') -> None:
		payload: dict = {'cmd': 'user', 'user': user.serialize(), 'action': cmd}
		if reason:
			payload['reason'] = reason
		await self._broadcast(payload)

	async def on_say(self, user: CrossChatUser, say: str) -> None:
		await self._broadcast({'cmd': 'say', 'user': user.serialize(), 'say': say})

	async def on_pm(self, sender: CrossChatUser, target_server_id: str, target_user_id: int, say: str) -> None:
		own_id = self._app.state.crosschat.state._own_id
		if target_server_id != own_id:
			return
		payload = json.dumps({
			'cmd': 'pm',
			'from_server': sender.server.id,
			'from_user': sender.serialize(),
			'to_server': target_server_id,
			'to_user_id': target_user_id,
			'say': say,
		})
		ws = self._app.state.ws_users.get(target_user_id)
		if ws is not None:
			try:
				await ws.send_text(payload)
			except Exception:
				self._app.state.ws_users.pop(target_user_id, None)
				self._app.state.ws_clients.discard(ws)

	async def on_server_add(self, server: CrossChatServer) -> None:
		await self._broadcast({'cmd': 'server_add', 'id': server.id})

	async def on_server_del(self, server: CrossChatServer) -> None:
		await self._broadcast({'cmd': 'server_del', 'id': server.id})

	async def on_server_status(self, server: CrossChatServer) -> None:
		await self._broadcast(
			{
				'cmd': 'server_status',
				'id': server.id,
				'online': server.online,
				'started': server.started,
			}
		)


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
			'users': [user.serialize() for user in srv.users.values()],
		}
		for sid, srv in state.servers.items()
	]
	await ws.send_text(json.dumps({'cmd': 'server_list', 'servers': servers}))

	user_id: int | None = None
	handler: WebchatHandler = ws.app.state.handler
	disconnect_reason = ''

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
				app.state.ws_users[uid] = ws
				await ws.send_text(json.dumps({'cmd': 'joined', 'user_id': uid, 'name': name}))
				user = state.servers[state._own_id].users[uid]
				await handler.on_user(user, 'join')

			elif cmd == 'say':
				if user_id is None:
					await ws.send_text(json.dumps({'cmd': 'error', 'msg': 'must join first'}))
					continue
				say_text = payload.get('say', '')
				if not say_text:
					await ws.send_text(json.dumps({'cmd': 'error', 'msg': 'say required'}))
					continue
				for sid, srv in state.servers.items():
					if sid != state._own_id and srv.online:
						await state.publish(
							f'm/{state._own_id}/{sid}/say/{user_id}',
							payload=json.dumps({'say': say_text}),
						)
				user = state.servers[state._own_id].users[user_id]
				await handler.on_say(user, say_text)
				await ws.send_text(json.dumps({'cmd': 'say_sent'}))

			elif cmd == 'pm':
				if user_id is None:
					await ws.send_text(json.dumps({'cmd': 'error', 'msg': 'must join first'}))
					continue
				target_server = payload.get('server', '')
				target_user_id = payload.get('to_user_id')
				pm_text = payload.get('say', '')
				if not target_server or target_user_id is None or not pm_text:
					await ws.send_text(json.dumps({'cmd': 'error', 'msg': 'server, to_user_id, say required'}))
					continue
				if target_server != state._own_id:
					await state.publish(
						f'm/{state._own_id}/{target_server}/pm/{user_id}/{target_user_id}',
						payload=json.dumps({'say': pm_text}),
					)
				sender = state.servers[state._own_id].users.get(user_id)
				if sender:
					await handler.on_pm(sender, target_server, target_user_id, pm_text)
				await ws.send_text(json.dumps({'cmd': 'pm_sent'}))

			elif cmd == 'client_error':
				report = ws.app.state.crosschat._config.get('webchat', {}).get('report_client_errors', True)
				if report:
					log.error('webchat_client_error', msg=payload.get('msg'), stack=payload.get('stack'))

			else:
				await ws.send_text(json.dumps({'cmd': 'error', 'msg': f'unknown cmd: {cmd}'}))
	except WebSocketDisconnect as e:
		log.info('websocket_disconnect', code=e.code)
		if e.code != 1000:
			disconnect_reason = {1001: 'going away', 1006: 'timeout'}.get(e.code, f'close code {e.code}')
	except Exception:
		log.exception('websocket_handler_error')
		disconnect_reason = 'unhandled exception'
	finally:
		app.state.ws_clients.discard(ws)
		if user_id is not None:
			app.state.ws_users.pop(user_id, None)
			user = await state.del_user(user_id, disconnect_reason)
			if user:
				await handler.on_user(user, 'leave', reason=disconnect_reason)


static_dir = Path(__file__).resolve().parent / 'static'
if static_dir.is_dir():
	app.mount('/', StaticFiles(directory=str(static_dir), html=True), name='static')
