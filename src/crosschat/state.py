from __future__ import annotations

from datetime import datetime, timezone

from crosschat.models import CrossChatServer, CrossChatUser


class CrossChatState:
	def __init__(self) -> None:
		self.servers: dict[str, CrossChatServer] = {}
		self._own_id: str = ''

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

	def get_or_create_user(self, server_id: str, user_id: str) -> CrossChatUser:
		server = self._ensure_server(server_id)
		if user_id in server.users:
			return server.users[user_id]
		user = CrossChatUser(
			id=user_id,
			first_seen=datetime.now(timezone.utc),
			server=server,
		)
		server.users[user_id] = user
		return user

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
				parts.append(f'    └ {uid}  (since {ts})')
		if not self.servers:
			parts.append('  (no servers known)')
		return '\n'.join(parts)
