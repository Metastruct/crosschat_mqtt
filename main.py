import argparse
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from crosschat import CrossChat, UserCommand
from crosschat.models import BurstFlag, CrossChatServer, CrossChatUser
from rich.console import Console


console = Console(stderr=True)


FAKE_NAMES = ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve', 'Frank', 'Grace', 'Hank']


class HandlerExample:
	async def on_user(self, user: CrossChatUser, cmd: str, burst: BurstFlag = BurstFlag.NONE) -> None:
		style = {
			UserCommand.ADD: 'green',
			UserCommand.REMOVE: 'red',
			UserCommand.UPDATE: 'yellow',
		}.get(cmd, 'white')
		action = {
			UserCommand.ADD: 'added',
			UserCommand.REMOVE: 'removed',
			UserCommand.UPDATE: 'updated',
		}.get(cmd, 'unknown')
		burst_info = f' [dim](burst={burst.name})[/]' if burst else ''
		console.print(f'[bold {style}]user {action}[/] [italic]{user}[/]{burst_info}')

	async def on_msg(self, user: CrossChatUser, msg: str) -> None:
		console.print(f'[bold blue]message[/] [italic]{user}[/]: {msg}')

	async def on_server_add(self, server: CrossChatServer) -> None:
		console.print(f'[bold green]server added[/] [italic]{server}[/]')

	async def on_server_del(self, server: CrossChatServer) -> None:
		console.print(f'[bold red]server removed[/] [italic]{server}[/]')

	async def on_server_status(self, server: CrossChatServer) -> None:
		status = 'online' if server.online else 'offline'
		console.print(f'[bold cyan]server status[/] [italic]{server}[/] is {status}')


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


async def main() -> None:
	args = parse_args()
	handler = HandlerExample()
	chat = CrossChat(
		config=args.config,
		host=args.host,
		port=args.port,
		server_id=args.server_id,
		console_port=args.console_port,
		verbose=args.verbose,
		handler=handler,
	)

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
			import json

			await asyncio.sleep(6)
			for uid in fake_user_ids:
				payload = json.dumps({'msg': f'Hello from user {uid}'})
				for sid, server in chat.state.servers.items():
					if sid != chat.state._own_id and server.online:
						tg.create_task(
							chat.state.publish(f'm/{chat.state._own_id}/{sid}/msg/{uid}', payload=payload)
						)

		tg.create_task(add_fake(), name='add_fake_user')
		tg.create_task(send_messages(), name='send_fake_messages')
		tg.create_task(chat.run(tg), name='crosschat')
		await chat.shutdown.wait()


if __name__ == '__main__':
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	asyncio.run(main())
