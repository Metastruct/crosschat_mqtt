from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import structlog

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


@dataclass
class CrossChatServer:
	id: str
	online: bool = False
	users: dict[int, CrossChatUser] = field(default_factory=dict)
	states: dict[str, str] = field(default_factory=dict)
	meta: dict = field(default_factory=dict)
	burst_in_progress: bool = False

	def __repr__(self):
		return f"CrossChatServer({self.id!r}, users={len(self.users)})"

	def __str__(self):
		return f"<Server {self.id}>"

	def get_user(self, id: int, create=False, ensure=False):
		user = self.users.get(id, None)
		if not user:
			if create or ensure:
				user = CrossChatUser(name=f'UnknownUser{id}', server=self, id=id, first_seen=datetime.now(timezone.utc))
				if ensure and not create:
					log.warning('Created user without networked name', user=user)
					pass
		return user
