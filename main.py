import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))

from crosschat import CrossChat


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument('--config', '-c', type=Path, default=Path('config.json'))
	parser.add_argument('--host', type=str)
	parser.add_argument('--port', type=int)
	parser.add_argument('--server-id', type=str)
	parser.add_argument('--console-port', type=int)
	parser.add_argument('--verbose', '-v', action='store_true')
	return parser.parse_args()


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
	await chat.run()


if __name__ == '__main__':
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	asyncio.run(main())
