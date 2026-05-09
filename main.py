import argparse
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from crosschat import CrossChat, UserCommand
from crosschat.models import CrossChatUser
from rich.console import Console


console = Console(stderr=True)


FAKE_NAMES = ['Alice', 'Bob', 'Charlie', 'Diana', 'Eve', 'Frank', 'Grace', 'Hank']


class HandlerExample:
	async def on_user(self, user: CrossChatUser, cmd: str) -> None:
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
		console.print(f'[bold {style}]user {action}[/] [italic]{user}[/]')

	async def on_msg(self, user: CrossChatUser, msg: str) -> None:
		console.print(f'[bold blue]message[/] [italic]{user}[/]: {msg}')


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument('--config', '-c', type=Path, default=Path('config.json'))
	parser.add_argument('--host', type=str)
	parser.add_argument('--port', type=int)
	parser.add_argument('--server-id', type=str)
	parser.add_argument('--console-port', type=int)
	parser.add_argument('--verbose', '-v', action='store_true')
	return parser.parse_args()


async def add_and_broadcast(chat: CrossChat, name: str) -> None:
	await chat.state.add_user_and_broadcast(name)


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
	_infinite = asyncio.Event()

	async with asyncio.TaskGroup() as tg:
		count = random.randint(1, 2)
		print('adding immediate fake users')
		for _ in range(count):
			name = random.choice(FAKE_NAMES)
			await add_and_broadcast(chat, 'Imm' + name)

		async def add_fake():

			await asyncio.sleep(4)
			print('adding late user')
			await add_and_broadcast(chat, 'LateUser1')

		tg.create_task(add_fake(), name='add_fake_user')
		tg.create_task(chat.run(tg), name='crosschat')
		await _infinite.wait()


if __name__ == '__main__':
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	asyncio.run(main())
