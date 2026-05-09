import json
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles

app = FastAPI()


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket) -> None:
	await ws.accept()

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

	try:
		while True:
			raw = await ws.receive_text()
			payload = json.loads(raw)
			cmd = payload.get('cmd')
			i = payload.get('i', 0)
			if cmd == 'echo':
				await ws.send_text(json.dumps({'cmd': 'echo_reply', 'i': i}))
			else:
				await ws.send_text(json.dumps({'cmd': 'error', 'msg': f'unknown cmd: {cmd}'}))
	except Exception:
		pass


static_dir = Path(__file__).resolve().parent / 'static'
if static_dir.is_dir():
	app.mount('/', StaticFiles(directory=str(static_dir), html=True), name='static')
