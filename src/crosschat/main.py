import argparse
import asyncio
import json
import logging
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiomqtt
import aiomonitor
import structlog

from crosschat.models import CrossChatUser
from crosschat.state import CrossChatState

import crosschat.monitor_ext  # noqa: F401  register aiomonitor commands


def parse_args() -> argparse.Namespace:
	parser = argparse.ArgumentParser()
	parser.add_argument('--config', '-c', type=Path, default=Path('config.json'))
	parser.add_argument('--host', type=str)
	parser.add_argument('--port', type=int)
	parser.add_argument('--server-id', type=str)
	parser.add_argument('--console-port', type=int)
	parser.add_argument('--verbose', '-v', action='store_true')
	return parser.parse_args()


def load_config(path: Path) -> dict:
	with open(path) as f:
		return json.load(f)


def setup_logging(verbose: bool) -> None:
	level = logging.DEBUG if verbose else logging.INFO
	structlog.configure(
		processors=[
			structlog.stdlib.add_log_level,
			structlog.processors.TimeStamper(fmt='iso'),
			structlog.dev.ConsoleRenderer(),
		],
		wrapper_class=structlog.stdlib.BoundLogger,
		cache_logger_on_first_use=True,
	)
	logging.basicConfig(format='%(message)s', level=level, force=True)


log = structlog.get_logger()


async def listen_messages(client: aiomqtt.Client, state: CrossChatState) -> None:
	await client.subscribe('crosschat/state/+/online')
	await client.subscribe('crosschat/m/+/user/+')
	await client.subscribe('crosschat/m/+/user/+/remove')
	await client.subscribe(f'crosschat/m/{state._own_id}/msg/+')
	async for message in client.messages:
		topic = message.topic.value
		payload = message.payload.decode()
		parts = topic.split('/')
		if len(parts) >= 4 and parts[0] == 'crosschat' and parts[1] == 'state' and parts[3] == 'online':
			sid = parts[2]
			online = payload == 'online'
			prev = state.servers.get(sid)
			prev_online = prev.online if prev else None
			state.set_online(sid, online)
			if prev_online != online:
				log.info('server_state_changed', server_id=sid, online=online)
		elif len(parts) == 5 and parts[0] == 'crosschat' and parts[1] == 'm' and parts[3] == 'user':
			data = json.loads(payload)
			sid = data.get('server_id', '')
			if sid and sid != state._own_id:
				server = state._ensure_server(sid)
				user_id = data['id']
				user = CrossChatUser(
					id=user_id,
					name=data.get('name', ''),
					seq=data.get('seq', 0),
					first_seen=datetime.now(timezone.utc),
					server=server,
				)
				server.users[user_id] = user
				log.info('user_added', server_id=sid, user_id=user_id, name=user.name)
		elif len(parts) == 6 and parts[0] == 'crosschat' and parts[1] == 'm' and parts[3] == 'user' and parts[5] == 'remove':
			data = json.loads(payload)
			sid = data.get('server_id', '')
			user_id = data['id']
			server = state.servers.get(sid)
			if server and user_id in server.users:
				del server.users[user_id]
				log.info('user_removed', server_id=sid, user_id=user_id)
		elif len(parts) == 5 and parts[0] == 'crosschat' and parts[1] == 'm' and parts[3] == 'msg':
			recipient_id = parts[4]
			data = json.loads(payload)
			msg_text = data.get('msg', '')
			own = state.servers.get(state._own_id)
			if own and recipient_id in own.users:
				log.info('msg_received', to_user=recipient_id, msg=msg_text)
			else:
				log.warning('msg_user_missing', user_id=recipient_id)


async def main() -> None:
	args = parse_args()
	setup_logging(args.verbose)
	config = load_config(args.config)

	if args.host is not None:
		config['mqtt']['host'] = args.host
	if args.port is not None:
		config['mqtt']['port'] = args.port
	if args.server_id is not None:
		config['server_id'] = args.server_id

	sid = config['server_id']
	prefix = config['topic_prefix']
	host = config['mqtt']['host']
	port = config['mqtt']['port']
	console_host = config.get('console_host', '127.0.0.1')
	console_port = config.get('console_port', 20103)
	if args.console_port is not None:
		console_port = args.console_port

	state = CrossChatState()
	state.set_own_id(sid)

	will = aiomqtt.Will(
		topic=f'{prefix}state/{sid}/online',
		payload='offline',
		qos=1,
		retain=True,
	)

	log.info('connecting', host=host, port=port, server_id=sid)
	async with aiomqtt.Client(
		hostname=host,
		port=port,
		will=will,
		identifier=sid,
	) as client:
		log.info('connected', host=host, port=port, server_id=sid)
		await client.publish(
			f'{prefix}state/{sid}/online',
			payload='online',
			qos=1,
			retain=True,
		)
		log.info('state_published', topic=f'{prefix}state/{sid}/online', state='online')

		listener = asyncio.create_task(listen_messages(client, state))

		loop = asyncio.get_running_loop()

		class _Status:
			def __repr__(self) -> str:
				return state.format_status()

			def __call__(self) -> str:
				return state.format_status()

		status = _Status()
		with aiomonitor.start_monitor(
			loop=loop,
			host=console_host,
			port=0,
			console_port=console_port,
			webui_port=0,
			locals={
				'state': state,
				'status': status,
				'client': client,
			},
		):
			stop_event = asyncio.Event()
			try:
				loop.add_signal_handler(signal.SIGINT, stop_event.set)
				loop.add_signal_handler(signal.SIGTERM, stop_event.set)
			except NotImplementedError:
				pass

			log.info('running', server_id=sid)
			await stop_event.wait()

		listener.cancel()
		try:
			await listener
		except asyncio.CancelledError:
			pass

	log.info('shutdown', server_id=sid)


if __name__ == '__main__':
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	asyncio.run(main())
