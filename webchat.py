import json

from fastapi import FastAPI, WebSocket

app = FastAPI()


@app.websocket('/ws')
async def websocket_endpoint(ws: WebSocket) -> None:
	await ws.accept()
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
