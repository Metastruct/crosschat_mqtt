import argparse
import asyncio
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from crosschat import CrossChat


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


async def add_and_broadcast(chat: CrossChat, name: str) -> None:
	await chat.state.add_user_and_broadcast(name)


async def main() -> None:
	args = parse_args()
	chat = CrossChat(
		config=args.config,
		host=args.host,
		port=args.port,
		server_id=args.server_id,
		console_port=args.console_port,
		verbose=args.verbose,
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
