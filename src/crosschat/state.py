from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Callable

from crosschat.models import CrossChatServer, CrossChatUser


class CrossChatState:
	def __init__(self) -> None:
		self.servers: dict[str, CrossChatServer] = {}
		self._own_id: str = ''
		self._next_seq: int = 1
		self._own_meta: dict = {}
		self._subscribers: dict[str, list[Callable]] = {}
		self._client: Any = None
		self._prefix: str = 'crosschat/'

	def set_own_id(self, sid: str) -> None:
		self._own_id = sid
		self._ensure_server(sid)

	def _ensure_server(self, sid: str) -> CrossChatServer:
		if sid not in self.servers:
			self.servers[sid] = CrossChatServer(id=sid)
		return self.servers[sid]

	def set_online(self, sid: str, online: bool) -> None:
		server = self._ensure_server(sid)
		server.online = online

	def set_meta(self, meta: dict) -> None:
		self._own_meta = meta
		server = self._ensure_server(self._own_id)
		server.meta = meta

	def get_meta(self) -> dict:
		return self._own_meta

	def set_client(self, client: Any, prefix: str) -> None:
		self._client = client
		self._prefix = prefix

	def set_state(self, key: str, value: str) -> None:
		server = self._ensure_server(self._own_id)
		server.states[key] = value
		if self._client is not None:
			asyncio.create_task(self._publish_state(key, value))
		self._notify(server, key, value)

	def subscribe(self, key: str, callback: Callable) -> None:
		if key not in self._subscribers:
			self._subscribers[key] = []
		self._subscribers[key].append(callback)

	def _notify(self, server: CrossChatServer, key: str, value: str) -> None:
		if key in self._subscribers:
			for cb in self._subscribers[key]:
				asyncio.create_task(cb(server, key, value))

	async def _publish_state(self, key: str, value: str) -> None:
		if self._client is None:
			return
		topic = f'{self._prefix}state/{self._own_id}/{key}'
		await self._client.publish(topic, payload=str(value), qos=1, retain=True)

	def get_or_create_user(self, server_id: str, user_id: str) -> CrossChatUser:
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

	def add_user(self, user_id: str, name: str) -> CrossChatUser:
		server = self._ensure_server(self._own_id)
		user = CrossChatUser(
			name=name,
			first_seen=datetime.now(timezone.utc),
			server=server,
			id=self._next_seq,
		)
		self._next_seq += 1
		server.users[user_id] = user
		return user

	def remove_user(self, user_id: str) -> CrossChatUser | None:
		server = self._ensure_server(self._own_id)
		return server.users.pop(user_id, None)

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
