from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from typing import TYPE_CHECKING, Any, Protocol

import structlog

if TYPE_CHECKING:
    from crosschat.state import CrossChatState

log = structlog.get_logger()


@dataclass
class CrossChatUser:
	name: str
	first_seen: datetime
	server: CrossChatServer
	id: int = 0
	extra: dict = field(default_factory=dict)

	def serialize(self):
		result = {
			'name': self.name,
			'first_seen': self.first_seen.isoformat(),
			'server': self.server.id,
		}
		result.update(self.extra)
		return result

	def __repr__(self):
		return f"CrossChatUser({self.name!r}, server={self.server!r})"

	def __str__(self):
		return f"<User {self.name} on {self.server.id}>"


class UserCommand:
	ADD = 'add'
	REMOVE = 'del'
	UPDATE = 'update'


class CrossChatHandler(Protocol):
	async def on_user(self, user: CrossChatUser, cmd: str) -> None: ...
	async def on_msg(self, user: CrossChatUser, msg: str) -> None: ...


@dataclass
class CrossChatServer:
	id: str
	online: bool = False
	started: int = 0
	users: dict[int, CrossChatUser] = field(default_factory=dict)
	states: dict[str, str] = field(default_factory=dict)
	meta: dict = field(default_factory=dict)
	_state: CrossChatState | None = field(default=None, repr=False, compare=False)

	def __repr__(self):
		return f"CrossChatServer({self.id!r}, users={len(self.users)})"

	def __str__(self):
		return f"<Server {self.id}>"

	async def send_ooc(self, ooc_name: str, payload: Any) -> None:
		if self._state is not None:
			await self._state.send_ooc(self.id, ooc_name, payload)

	def get_user(self, id: int, create=False, ensure=False):
		user = self.users.get(id, None)
		if not user:
			if create or ensure:
				user = CrossChatUser(name=f'UnknownUser{id}', server=self, id=id, first_seen=datetime.now(timezone.utc))
				if ensure and not create:
					log.warning('Created user without networked name', user=user)
					pass
		return user

	async def add_user(self, name: str, extra: dict | None = None) -> int:
		state = self._state
		if state is None:
			raise RuntimeError('CrossChatServer has no state reference')
		user_id = state._next_seq
		user = CrossChatUser(
			name=name,
			first_seen=datetime.now(timezone.utc),
			server=self,
			id=user_id,
			extra=extra or {},
		)
		state._next_seq += 1
		self.users[user_id] = user

		if state._client is not None:
			user_data = user.serialize()
			user_data['id'] = user.id
			user_data['cmd'] = 'add'
			user_data['burst'] = False
			payload = json.dumps(user_data)
			for sid, srv in state.servers.items():
				if sid != state._own_id and srv.online:
					await state._client.publish(
						f'{state._prefix}m/{state._own_id}/{sid}/user',
						payload=payload,
						qos=2,
					)
		return user_id

	async def del_user(self, user_id: int) -> CrossChatUser | None:
		state = self._state
		user = self.users.pop(user_id, None)
		if user is None:
			return None

		if state is not None and state._client is not None:
			payload = json.dumps({'id': user.id, 'cmd': 'del'})
			for sid, srv in state.servers.items():
				if sid != state._own_id and srv.online:
					await state._client.publish(
						f'{state._prefix}m/{state._own_id}/{sid}/user',
						payload=payload,
						qos=2,
					)
		return user
