from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable

import aiomqtt
import structlog

from crosschat.models import CrossChatServer, CrossChatUser

log = structlog.get_logger()


class CrossChatState:
	_client: aiomqtt.Client | None  # None if it is us. #TODO: verify there is only one with None

	def __init__(self) -> None:
		self.servers: dict[str, CrossChatServer] = {}
		self._own_id: str = ''
		self._client = None
		self._next_seq: int = 1
		self._own_meta: dict = {}
		self._subscribers: dict[str, list[Callable]] = {}
		self._ooc_subscribers: dict[str, list[Callable]] = {}
		self._prefix: str = 'crosschat/'
		self._tg: asyncio.TaskGroup | None = None

	def set_own_id(self, sid: str) -> None:
		self._own_id = sid
		self._ensure_server(sid)

	def _ensure_server(self, sid: str, ensure=True) -> CrossChatServer:
		if sid not in self.servers:
			self.servers[sid] = CrossChatServer(id=sid, _state=self)
			if not ensure:
				log.warning('Created unknown server', id=sid)
		return self.servers[sid]

	def me(self):
		return self.servers[self._own_id]

	def set_status(self, sid: str, started: int) -> None:
		server = self.me()
		server.started = started
		server.online = started > 0

	def set_meta(self, meta: dict) -> None:
		self._own_meta = meta
		server = self.me()
		server.meta = meta

	def get_meta(self) -> dict:
		return self._own_meta

	def set_client(self, client: aiomqtt.Client, prefix: str) -> None:
		self._client = client
		self._prefix = prefix

	async def publish(self, topic: str, payload: str | dict | list, qos: int = 2, retain: bool = False) -> None:
		if self._client is None:
			return
		full_topic = f'{self._prefix}{topic}'
		if not isinstance(payload, str):
			payload = json.dumps(payload)
		try:
			await self._client.publish(full_topic, payload=payload, qos=qos, retain=retain)
		except aiomqtt.exceptions.MqttCodeError:
			if self._client:
				raise
			raise

	def set_task_group(self, tg: asyncio.TaskGroup) -> None:
		self._tg = tg

	def set_state(self, key: str, value: str) -> None:
		server = self.me()
		server.states[key] = value
		if self._client is not None and self._tg is not None:
			self._tg.create_task(self._publish_state(key, value))
		self._notify(server, key, value)

	def subscribe(self, key: str, callback: Callable) -> None:
		if key not in self._subscribers:
			self._subscribers[key] = []
		self._subscribers[key].append(callback)

	def _notify(self, server: CrossChatServer, key: str, value: str) -> None:
		if key in self._subscribers and self._tg is not None:
			for cb in self._subscribers[key]:
				self._tg.create_task(cb(server, key, value))

	async def _publish_state(self, key: str, value: str) -> None:
		await self.publish(f'state/{self._own_id}/{key}', payload=str(value), retain=True)

	def get_or_create_user(self, server_id: str, user_id: int) -> CrossChatUser:
		server = self._ensure_server(server_id)
		if user_id in server.users:
			return server.users[user_id]
		user = CrossChatUser(
			name='',
			first_seen=datetime.now(timezone.utc),
			server=server,
		)
		server.users[user_id] = user
		return user

	async def add_user(self, name: str, extra: dict | None = None) -> int:
		server = self.me()
		return await server.add_user(name, extra)

	async def del_user(self, user_id: int) -> CrossChatUser | None:
		server = self.me()
		return await server.del_user(user_id)

	def subscribe_ooc(self, ooc_name: str, callback: Callable) -> None:
		if ooc_name not in self._ooc_subscribers:
			self._ooc_subscribers[ooc_name] = []
		self._ooc_subscribers[ooc_name].append(callback)

	async def send_ooc(self, target_sid: str, ooc_name: str, payload: Any) -> None:
		await self.publish(f'm/{self._own_id}/{target_sid}/ooc/{ooc_name}', payload=payload)

	async def _notify_ooc(self, server: CrossChatServer, ooc_name: str, payload: str) -> None:
		if ooc_name in self._ooc_subscribers:
			for cb in self._ooc_subscribers[ooc_name]:
				await cb(server, payload, ooc_name)

	def format_status(self) -> str:
		parts = [f'[Own ID: {self._own_id}]', '']
		for sid in sorted(self.servers):
			server = self.servers[sid]
			badge = 'ONLINE' if server.online else 'OFFLINE'
			marker = ' (self)' if sid == self._own_id else ''
			parts.append(f'  {sid}: {badge}{marker}')
			for uid in sorted(server.users):
				user = server.users[uid]
				ts = user.first_seen.strftime('%Y-%m-%d %H:%M:%S UTC')
				parts.append(f'    └ {uid} ({user.name})  (since {ts})')
		if not self.servers:
			parts.append('  (no servers known)')
		return '\n'.join(parts)
