import asyncio
import json
import logging
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
import aiomqtt
import aiomonitor
import structlog

from crosschat.models import BurstFlag, CrossChatHandler, CrossChatUser
from crosschat.state import CrossChatState

import crosschat.monitor_ext  # noqa: F401


from paho.mqtt.properties import Properties
from paho.mqtt.packettypes import PacketTypes

# 1. Create the properties object for the CONNECT packet
properties = Properties(PacketTypes.CONNECT)
# 2. Set the interval (e.g., 3600 seconds for 1 hour)
properties.SessionExpiryInterval = 9


log = structlog.get_logger()


class CrossChat:
	_init = False

	def __init__(
		self,
		config: dict | str | Path | None = None,
		*,
		host: str | None = None,
		port: int | None = None,
		server_id: str | None = None,
		console_port: int | None = None,
		verbose: bool = False,
		handler: CrossChatHandler | None = None,
	):
		self.state = CrossChatState()
		self._config: dict = {}
		self._verbose = verbose
		self._handler = handler
		self.shutdown = asyncio.Event()

		if isinstance(config, (str, Path)):
			self.load_config(Path(config))
		elif isinstance(config, dict):
			self._config = config

		if host is not None:
			self._config.setdefault('mqtt', {})['host'] = host
		if port is not None:
			self._config.setdefault('mqtt', {})['port'] = port
		if server_id is not None:
			self._config['server_id'] = server_id
		if console_port is not None:
			self._config['console_port'] = console_port

		sid = self._config.get('server_id', '')
		if sid:
			self.state.set_own_id(sid)

	def load_config(self, path: Path) -> None:
		with open(path) as f:
			self._config = json.load(f)

	@staticmethod
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

	@staticmethod
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
					break
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

	async def init(self, client: aiomqtt.Client):
		if self._init:
			return
		self._init = True

		state = self.state
		started = self.started
		sid = self.state._own_id
		await client.subscribe('crosschat/state/+/#')
		await client.subscribe(f'crosschat/m/+/{state._own_id}/#')

		await self.state.publish(f'state/{sid}/status', payload={'started': started}, retain=True)
		log.info('state_published', topic=f'state/{sid}/status', started=started)

		meta_payload = self._config.get('meta', {})
		await self.state.publish(f'state/{sid}/meta', payload=meta_payload, retain=True)
		log.info('state_published', topic=f'state/{sid}/meta', state=meta_payload)
		self.state.set_meta(self._config.get('meta', {}))

	async def listen_messages(self, client: aiomqtt.Client, tg: asyncio.TaskGroup) -> None:
		await self.init(client)

		state = self.state
		async for message in client.messages:
			topic = message.topic.value
			payload = message.payload.decode()
			parts = topic.split('/')
			if parts[0] != 'crosschat':
				continue
			if parts[1] == 'state' and len(parts) >= 4:
				await self._handle_state_message(client, tg, parts, payload)
			elif parts[1] == 'm' and len(parts) >= 5 and parts[3] == state._own_id:
				await self._handle_m_message(topic, parts, payload)

	async def _handle_state_message(
		self, client: aiomqtt.Client, tg: asyncio.TaskGroup, parts: list[str], payload: str
	) -> None:
		state = self.state
		sid = parts[2]
		key = parts[3]
		if key == 'status':
			prev = state.servers.get(sid)
			prev_started = prev.started if prev else 0
			try:
				data = json.loads(payload)
				started = data.get('started', 0)
			except (json.JSONDecodeError, TypeError):
				started = 0
			state.set_status(sid, started)
			server = state.servers.get(sid)
			if started != prev_started:
				if self._handler is not None and server is not None:
					if started > 0:
						if prev_started == 0:
							await self._handler.on_server_add(server)
					else:
						await self._handler.on_server_del(server)
					await self._handler.on_server_status(server)
				log.info('server_state_changed', server_id=sid, started=started)
				if started > 0 and sid != state._own_id:
					own_server = state.servers.get(state._own_id)
					if own_server:
						users = list(own_server.users.values())
						user_count = len(users)
						for i, user in enumerate(users):
							serialized = user.serialize()
							serialized['id'] = int(user.id)
							serialized['cmd'] = 'add'
							if user_count == 1:
								serialized['burst'] = BurstFlag.STARTEND.serialize()
							elif i == 0:
								serialized['burst'] = BurstFlag.START.serialize()
							elif i == user_count - 1:
								serialized['burst'] = BurstFlag.END.serialize()
							else:
								serialized['burst'] = BurstFlag.ACTIVE.serialize()
							user_payload = json.dumps(serialized)
							user_topic = f'crosschat/m/{state._own_id}/{sid}/user'
							log.debug('send add(in burst)', topic=user_topic, payload=user_payload)
							tg.create_task(
								state.publish(f'm/{state._own_id}/{sid}/user', payload=user_payload),
							)
					user_count = len(own_server.users) if own_server else 0
					log.info('burst_sent', server_id=sid, user_count=user_count)
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

	async def _handle_m_message(self, topic: str, parts: list[str], payload: str) -> None:
		from_sid = parts[2]
		endpoint = parts[4]
		if endpoint == 'user':
			await self._handle_user_message(from_sid, topic, parts, payload)
		elif endpoint == 'msg' and len(parts) == 6:
			await self._handle_msg_message(from_sid, topic, parts, payload)
		elif endpoint == 'ooc' and len(parts) == 6:
			await self._handle_ooc_message(from_sid, topic, parts, payload)
		elif endpoint == 'pm' and len(parts) == 7:
			await self._handle_pm_message(from_sid, topic, parts, payload)
		else:
			log.warning('unknown_message_endpoint', topic=topic, endpoint=endpoint)

	async def _handle_user_message(self, from_sid: str, topic: str, parts: list[str], payload: str) -> None:
		state = self.state
		data = json.loads(payload)
		user_id = data.get('id')
		cmd = data.get('cmd', 'add')
		log.debug('user_message', topic=topic, payload=payload)
		user: CrossChatUser | None = None
		if from_sid and from_sid != state._own_id:
			server = state._ensure_server(from_sid)
			if cmd == 'del':
				user = server.users.pop(user_id, None)
				if user is not None:
					log.info('user_removed', server_id=from_sid, user_id=user_id)
			else:
				first_seen_str = data.get('first_seen')
				first_seen = datetime.fromisoformat(first_seen_str) if first_seen_str else datetime.now(timezone.utc)
				known = {'name', 'first_seen', 'server', 'burst', 'cmd', 'id'}
				extra = {k: v for k, v in data.items() if k not in known}
				user = CrossChatUser(
					name=data.get('name', ''),
					id=user_id,
					first_seen=first_seen,
					server=server,
					extra=extra,
				)
				server.users[user_id] = user
				log.info('user_added', server_id=from_sid, user_id=user_id, name=user.name)
		burst = BurstFlag.deserialize(data.get('burst'))
		if cmd == 'add' and from_sid and from_sid != state._own_id:
			server = state.servers.get(from_sid)
			if server is not None:
				if burst is BurstFlag.START or burst is BurstFlag.STARTEND:
					server.bursting = True
				if burst is BurstFlag.END or burst is BurstFlag.STARTEND:
					server.bursting = False
		if self._handler is not None and user is not None and cmd in ('add', 'del', 'update'):
			await self._handler.on_user(user, cmd, burst=burst)

	async def _handle_msg_message(self, from_sid: str, topic: str, parts: list[str], payload: str) -> None:
		state = self.state
		sender_id = int(parts[5])
		data = json.loads(payload)
		msg_text = data.get('msg', '')
		server = state._ensure_server(from_sid, ensure=True)
		user = server.get_user(sender_id, ensure=True)
		log.debug('MESSAGE', sender=user, msg=msg_text)
		if self._handler is not None:
			assert user
			await self._handler.on_msg(user, msg_text)

	async def _handle_ooc_message(self, from_sid: str, topic: str, parts: list[str], payload: str) -> None:
		state = self.state
		ooc_name = parts[5]
		server = state._ensure_server(from_sid)
		await state._notify_ooc(server, ooc_name, payload)

	async def _handle_pm_message(self, from_sid: str, topic: str, parts: list[str], payload: str) -> None:
		state = self.state
		from_user_id = int(parts[5])
		to_user_id = int(parts[6])
		data = json.loads(payload)
		msg_text = data.get('msg', '')
		sender_server = state.servers.get(from_sid)
		sender_user = sender_server.users.get(from_user_id) if sender_server else None
		receiver_server = state.servers.get(state._own_id)
		receiver_user = receiver_server.users.get(to_user_id) if receiver_server else None
		log.info(
			'PM',
			from_server=from_sid,
			from_user=from_user_id,
			from_name=sender_user.name if sender_user else '?',
			to_user=to_user_id,
			to_name=receiver_user.name if receiver_user else '?',
			msg=msg_text,
		)

	async def run(self, tg: asyncio.TaskGroup) -> None:
		self.setup_logging(self._verbose)
		config = self._config

		sid = config.get('server_id', '')
		prefix = config.get('topic_prefix', 'crosschat/')
		host = config.get('mqtt', {}).get('host', 'localhost')
		port = config.get('mqtt', {}).get('port', 1883)
		console_host = config.get('console_host', '127.0.0.1')
		console_port = config.get('console_port', 20103)
		console_enabled = config.get('console_enabled', True)
		self.sid = sid
		self.state.set_own_id(sid)
		self.state.set_task_group(tg)

		self.started = int(time.time())
		will = aiomqtt.Will(
			topic=f'{prefix}state/{sid}/status',
			payload=json.dumps({'started': 0}),
			qos=2,
			retain=True,
		)

		log.info('connecting', host=host, port=port, server_id=sid)
		async with aiomqtt.Client(
			hostname=host,
			port=port,
			will=will,
			identifier=sid,
			# clean_session=True,
			clean_start=True,
			properties=properties,
			keepalive=4,
			protocol=aiomqtt.ProtocolVersion.V5,
		) as client:
			log.info('connected', host=host, port=port, server_id=sid)
			self.state.set_client(client, prefix)

			for level in ('debug', 'warning', 'info'):
				self.state.subscribe_ooc(
					level,
					lambda server, payload, name, _level=level: getattr(log, _level)(
						'ooc_log',
						server_id=server.id,
						ooc_type=name,
						payload=payload,
					),
				)

			loop = asyncio.get_running_loop()
			_state = self.state

			class _Status:
				def __repr__(self) -> str:
					return _state.format_status()

				def __call__(self) -> str:
					return _state.format_status()

			status = _Status()
			console_locals = {
				'state': self.state,
				'status': status,
				'client': client,
				'tg': tg,
				'shutdown': self.shutdown,
				'handler': self._handler,
			}
			if console_enabled:
				monitor = aiomonitor.start_monitor(
					loop=loop,
					host=console_host,
					port=0,
					console_port=console_port,
					webui_port=0,
					locals=console_locals,
				)
			else:
				monitor = None

			tg.create_task(self.listen_messages(client, tg), name='mqtt_listener')

			if monitor is not None:
				with monitor:
					await asyncio.sleep(5)
					tg.create_task(self.run_local_console(monitor), name='local_console')
					log.info('running', server_id=sid)
			await self.shutdown.wait()

		log.info('shutdown', server_id=sid)
