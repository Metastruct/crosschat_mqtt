import argparse
import asyncio
import json
import logging
import signal
import sys
import traceback
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


async def run_local_console(monitor: aiomonitor.Monitor) -> None:
	import shlex
	from contextvars import copy_context

	import click
	from prompt_toolkit import PromptSession
	from prompt_toolkit.formatted_text import FormattedText

	from aiomonitor.context import command_done, current_monitor, current_stdout
	from aiomonitor.termui.commands import monitor_cli
	from aiomonitor.termui.completion import ClickCompleter

	prompt_session = PromptSession(
		completer=ClickCompleter(monitor_cli),
		complete_while_typing=False,
	)

	cm_token = current_monitor.set(monitor)
	cs_token = current_stdout.set(sys.stdout)

	try:
		while True:
			try:
				user_input = (
					await prompt_session.prompt_async(
						FormattedText([('#5fd7ff bold', monitor.prompt)]),
					)
				).strip()
			except EOFError:
				break  # no terminal?
			except asyncio.CancelledError:
				raise
			except KeyboardInterrupt:
				raise asyncio.CancelledError('ctrl+c')

			if not user_input:
				continue

			cd_event = asyncio.Event()
			cd_token = command_done.set(cd_event)
			try:
				args = shlex.split(user_input)
				term_size = prompt_session.output.get_size()
				ctx = copy_context()
				ctx.run(
					monitor_cli.main,
					args,
					prog_name='',
					obj=monitor,
					standalone_mode=False,
					max_content_width=term_size.columns,
				)
				await cd_event.wait()
			except (click.BadParameter, click.UsageError) as e:
				click.echo(str(e))
			except asyncio.CancelledError:
				break
			except Exception:
				traceback.print_exc()
			finally:
				command_done.reset(cd_token)
	finally:
		current_stdout.reset(cs_token)
		current_monitor.reset(cm_token)


async def listen_messages(client: aiomqtt.Client, state: CrossChatState) -> None:
	await client.subscribe('crosschat/state/+/#')
	await client.subscribe(f'crosschat/m/+/{state._own_id}/#')
	async for message in client.messages:
		topic = message.topic.value
		payload = message.payload.decode()
		parts = topic.split('/')
		if parts[0] != 'crosschat':
			continue
		if parts[1] == 'state' and len(parts) >= 4:
			sid = parts[2]
			key = parts[3]
			if key == 'online':
				online = payload == 'online'
				prev = state.servers.get(sid)
				prev_online = prev.online if prev else None
				state.set_online(sid, online)
				if prev_online != online:
					log.info('server_state_changed', server_id=sid, online=online)
					if online and sid != state._own_id:
						burst_topic = f'crosschat/m/{state._own_id}/{sid}/burst/start'
						log.debug('burst_pub', topic=burst_topic, payload='{}')
						tasks = [
							asyncio.create_task(
								client.publish(burst_topic, payload='{}', qos=1),
							),
						]
						own_server = state.servers.get(state._own_id)
						if own_server:
							for user in own_server.users.values():
								user_payload = json.dumps({'id': user.id, 'name': user.name})
								user_topic = f'crosschat/m/{state._own_id}/{sid}/user/{user.id}'
								log.debug('burst_pub', topic=user_topic, payload=user_payload)
								tasks.append(
									asyncio.create_task(
										client.publish(
											user_topic,
											payload=user_payload,
											qos=1,
										),
									),
								)
						end_topic = f'crosschat/m/{state._own_id}/{sid}/burst/end'
						log.debug('burst_pub', topic=end_topic, payload='{}')
						tasks.append(
							asyncio.create_task(
								client.publish(end_topic, payload='{}', qos=1),
							),
						)
						await asyncio.gather(*tasks)
						log.info('burst_sent', server_id=sid, user_count=len(own_server.users) if own_server else 0)
			elif key == 'meta' and len(parts) == 4:
				try:
					meta_data = json.loads(payload)
				except json.JSONDecodeError:
					meta_data = {}
				server = state._ensure_server(sid)
				server.meta = meta_data
				log.info('server_meta_updated', server_id=sid, meta=meta_data)
			else:
				server = state._ensure_server(sid)
				server.states[key] = payload
				state._notify(server, key, payload)
		elif parts[1] == 'm' and len(parts) >= 5 and parts[3] == state._own_id:
			from_sid = parts[2]
			endpoint = parts[4]
			if endpoint == 'burst' and len(parts) == 6:
				if parts[5] == 'start':
					log.debug('burst_recv', topic=topic, payload=payload)
					log.info('burst_start', server_id=from_sid)
				elif parts[5] == 'end':
					log.debug('burst_recv', topic=topic, payload=payload)
					log.info('burst_end', server_id=from_sid)
			elif endpoint == 'user' and len(parts) == 6:
				data = json.loads(payload)
				user_id = data['id']
				log.debug('burst_recv', topic=topic, payload=payload)
				if from_sid and from_sid != state._own_id:
					server = state._ensure_server(from_sid)
					user = CrossChatUser(
						name=data.get('name', ''),
						id=data.get('seq', 0),
						first_seen=datetime.now(timezone.utc),
						server=server,
					)
					server.users[user_id] = user
					log.info('user_added', server_id=from_sid, user_id=user_id, name=user.name)
			elif endpoint == 'user' and len(parts) == 7 and parts[6] == 'remove':
				data = json.loads(payload)
				user_id = data['id']
				server = state.servers.get(from_sid)
				if server and user_id in server.users:
					del server.users[user_id]
					log.info('user_removed', server_id=from_sid, user_id=user_id)
			elif endpoint == 'msg' and len(parts) == 6:
				sender_id = int(parts[5])
				data = json.loads(payload)
				msg_text = data.get('msg', '')
				server = state._ensure_server(from_sid, ensure=True)
				user = server.get_user(sender_id, ensure=True)
				log.debug('MESSAGE', sender=user, msg=msg_text)
			else:
				log.warning('unknown_message_endpoint', topic=topic, endpoint=endpoint)


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

		meta_payload = json.dumps(config.get('meta', {}))
		await client.publish(
			f'{prefix}state/{sid}/meta',
			payload=meta_payload,
			qos=1,
			retain=True,
		)
		log.info('state_published', topic=f'{prefix}state/{sid}/meta', state=meta_payload)
		state.set_meta(config.get('meta', {}))
		state.set_client(client, prefix)

		loop = asyncio.get_running_loop()

		class _Status:
			def __repr__(self) -> str:
				return state.format_status()

			def __call__(self) -> str:
				return state.format_status()

		status = _Status()
		console_locals = {
			'state': state,
			'status': status,
			'client': client,
		}
		monitor = aiomonitor.start_monitor(
			loop=loop,
			host=console_host,
			port=0,
			console_port=console_port,
			webui_port=0,
			locals=console_locals,
		)
		async with asyncio.TaskGroup() as tg:
			tg.create_task(listen_messages(client, state), name='mqtt_listener')

			with monitor:
				tg.create_task(run_local_console(monitor), name='local_console')

				log.info('running', server_id=sid)

	log.info('shutdown', server_id=sid)


if __name__ == '__main__':
	if sys.platform == 'win32':
		asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
	asyncio.run(main())
