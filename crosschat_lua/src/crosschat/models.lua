-- CrossChat Data Models
-- Pure Lua reference implementation of protocol data structures

local CrossChatUser = {}
CrossChatUser.__index = CrossChatUser

function CrossChatUser.new(name, server, opts)
	opts = opts or {}
	return setmetatable({
		name = name,
		first_seen = opts.first_seen or os.time(),
		server = server,
		id = opts.id or 0,
		extra = opts.extra or {},
		steamid64 = opts.steamid64 or '',
		team = opts.team or 1,
	}, CrossChatUser)
end

function CrossChatUser:serialize()
	local result = {
		name = self.name,
		first_seen = self.first_seen,
		server = self.server.id,
	}
	for k, v in pairs(self.extra) do
		result[k] = v
	end
	return result
end

function CrossChatUser:__tostring()
	return string.format('<User %s on %s>', self.name, self.server.id)
end

local BurstFlag = {
	NONE = 0,
	STARTEND = 1,
	START = 2,
	END = 3,
	ACTIVE = 4,
}

BurstFlag.__index = BurstFlag

function BurstFlag.serialize(flag)
	local map = {
		[BurstFlag.NONE] = false,
		[BurstFlag.STARTEND] = 'startend',
		[BurstFlag.START] = 'start',
		[BurstFlag.END] = 'end',
		[BurstFlag.ACTIVE] = true,
	}
	return map[flag]
end

function BurstFlag.deserialize(value, default)
	if value == false or value == 'false' then
		return BurstFlag.NONE
	end
	if value == true or value == 'true' then
		return BurstFlag.ACTIVE
	end
	if value == 'startend' then
		return BurstFlag.STARTEND
	end
	if value == 'start' then
		return BurstFlag.START
	end
	if value == 'end' then
		return BurstFlag.END
	end
	return default or BurstFlag.NONE
end

local CrossChatServer = {}
CrossChatServer.__index = CrossChatServer

function CrossChatServer.new(id)
	return setmetatable({
		id = id,
		online = false,
		started = 0,
		users = {},
		meta = {},
		states = {},
		bursting = false,
	}, CrossChatServer)
end

function CrossChatServer:add_user(name, extra)
	local uid = self._next_seq or 1
	self._next_seq = uid + 1
	local user = CrossChatUser.new(name, self, {
		id = uid,
		first_seen = os.time(),
		extra = extra or {},
	})
	self.users[uid] = user
	return uid
end

function CrossChatServer:del_user(uid)
	local user = self.users[uid]
	self.users[uid] = nil
	return user
end

function CrossChatServer:get_user(uid)
	return self.users[uid]
end

function CrossChatServer:get_or_create_user(uid)
	local user = self.users[uid]
	if not user then
		user = CrossChatUser.new(string.format('UnknownUser%d', uid), self, {id = uid})
		self.users[uid] = user
	end
	return user
end

local UserCommand = {
	ADD = 'add',
	REMOVE = 'leave',
	UPDATE = 'update',
}

return {
	CrossChatUser = CrossChatUser,
	CrossChatServer = CrossChatServer,
	BurstFlag = BurstFlag,
	UserCommand = UserCommand,
}
