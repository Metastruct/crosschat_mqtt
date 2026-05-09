from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class CrossChatUser:
	name: str
	first_seen: datetime
	server: CrossChatServer
	id: int = 0


@dataclass
class CrossChatServer:
	id: str
	online: bool = False
	users: dict[str, CrossChatUser] = field(default_factory=dict)
