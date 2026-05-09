import argparse
import asyncio
import json
import os
import random
import sys
from pathlib import Path

import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from crosschat import CrossChat
from webchat import WebchatHandler, app as webchat_app


FAKE_NAMES = ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve', 'Frank', 'Grace', 'Hank']


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument('--config', '-c', type=Path, default=Path('config.json'))
	parser.add_argument('--host', type=str)
	parser.add_argument('--port', type=int)
	parser.add_argument('--server-id', type=str)
	parser.add_argument('--console-port', type=int)
	parser.add_argument('--verbose', '-v', action='store_true')
	return parser.parse_args()


async def add_and_broadcast(chat: CrossChat, name: str) -> int:
	return await chat.state.add_user(name)


async def main() -> int:
	args = parse_args()
	handler = WebchatHandler(webchat_app)
	webchat_app.state.handler = handler
	chat = CrossChat(
		config=args.config,
		host=args.host,
		port=args.port,
		server_id=args.server_id,
		console_port=args.console_port,
		verbose=args.verbose,
		handler=handler,
	)

	with open(args.config) as f:
		cfg = json.load(f)
	webchat_host = cfg.get('webchat_host', '0.0.0.0')
	webchat_port = cfg.get('webchat_port', 8765)

	try:
		try:
			async with asyncio.TaskGroup() as tg:
				fake_user_ids: list[int] = []

				count = random.randint(1, 2)
				print('adding immediate fake users')
				for _ in range(count):
					name = random.choice(FAKE_NAMES)
					uid = await add_and_broadcast(chat, 'Imm' + name)
					fake_user_ids.append(uid)

				async def add_fake():
					await asyncio.sleep(4)
					print('adding late user')
					uid = await add_and_broadcast(chat, 'LateUser1')
					fake_user_ids.append(uid)

				async def send_messages():
					await asyncio.sleep(6)
					for uid in fake_user_ids:
						payload = json.dumps({'say': f'Hello from user {uid}'})
						for sid, server in chat.state.servers.items():
							if sid != chat.state._own_id and server.online:
								tg.create_task(
									chat.state.publish(f'm/{chat.state._own_id}/{sid}/say/{uid}', payload=payload)
								)
						user = chat.state.servers[chat.state._own_id].users.get(uid)
						if user:
							tg.create_task(handler.on_say(user, f'Hello from user {uid}'))

				webchat_app.state.crosschat = chat
				webchat_config = uvicorn.Config(webchat_app, host=webchat_host, port=webchat_port, log_level='info')
				webchat_server = uvicorn.Server(webchat_config)

				tg.create_task(add_fake(), name='add_fake_user')
				tg.create_task(send_messages(), name='send_fake_messages')
				tg.create_task(chat.run(tg), name='crosschat')
				tg.create_task(webchat_server.serve(), name='webchat')
				await chat.shutdown.wait()
		except* (KeyboardInterrupt, SystemExit):
			pass
		except* asyncio.exceptions.CancelledError:
			pass

	except asyncio.exceptions.CancelledError:
		return 0
	except ExceptionGroup as eg:
		for ex in eg.exceptions:
			if isinstance(ex, asyncio.exceptions.CancelledError):
				continue
			else:
				raise ex
	except (KeyboardInterrupt, SystemExit):
		return 0
	return 0


if __name__ == '__main__':
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	sys.exit(asyncio.run(main()))
