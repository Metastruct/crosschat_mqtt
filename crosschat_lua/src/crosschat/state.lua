-- CrossChat State Manager
-- Tracks servers, users, and message dispatch

local models = require('src.crosschat.models')
if not models then
	models = _G.CrossChatModels
end

local CrossChatUser = models.CrossChatUser
local CrossChatServer = models.CrossChatServer
local BurstFlag = models.BurstFlag

local CrossChatState = {}
CrossChatState.__index = CrossChatState

function CrossChatState.new(own_id)
	return setmetatable({
		servers = {},
		own_id = own_id or '',
		next_seq = 1,
		publish_fn = nil,
	}, CrossChatState)
end

function CrossChatState:set_publish_fn(fn)
	self.publish_fn = fn
end

function CrossChatState:get_or_create_server(sid)
	if not self.servers[sid] then
		self.servers[sid] = CrossChatServer.new(sid)
	end
	return self.servers[sid]
end

function CrossChatState:get_own_server()
	return self:get_or_create_server(self.own_id)
end

function CrossChatState:handle_status(sid, started)
	local server = self:get_or_create_server(sid)
	local prev_started = server.started
	server.started = started
	server.online = started > 0
	return server, prev_started
end

function CrossChatState:handle_user(from_sid, data)
	if from_sid == self.own_id then return nil end
	local uid = data.id
	if not uid then return nil end
	local cmd = data.cmd or 'add'
	local server = self:get_or_create_server(from_sid)
	local burst = BurstFlag.deserialize(data.burst)
	if cmd == 'leave' then
		local user = server:del_user(uid)
		return {user = user, cmd = cmd, burst = burst, server = server, reason = data.reason or ''}
	end
	if burst == BurstFlag.START or burst == BurstFlag.STARTEND then
		server.bursting = true
	end
	if burst == BurstFlag.END or burst == BurstFlag.STARTEND then
		server.bursting = false
	end
	local known = {name = true, first_seen = true, server = true, burst = true, cmd = true, id = true, steamid64 = true, team = true}
	local extra = {}
	for k, v in pairs(data) do
		if not known[k] then extra[k] = v end
	end
	local user = server:get_or_create_user(uid)
	user.name = data.name or user.name
	user.steamid64 = data.steamid64 or user.steamid64
	user.team = data.team or user.team
	for k, v in pairs(extra) do
		user.extra[k] = v
	end
	return {user = user, cmd = cmd, burst = burst, server = server}
end

function CrossChatState:add_local_user(name, extra)
	local server = self:get_own_server()
	local uid = self.next_seq
	self.next_seq = self.next_seq + 1
	local user = CrossChatUser.new(name, server, {
		id = uid,
		first_seen = os.time(),
		extra = extra or {},
	})
	server.users[uid] = user
	return uid
end

function CrossChatState:del_local_user(uid)
	return self:get_own_server():del_user(uid)
end

function CrossChatState:get_user_on_server(sid, uid)
	local server = self.servers[sid]
	if not server then return nil end
	return server:get_user(uid)
end

function CrossChatState:get_burst_users()
	local user_list = {}
	for uid, user in pairs(self:get_own_server().users) do
		table.insert(user_list, {uid = uid, user = user})
	end
	table.sort(user_list, function(a, b) return a.uid < b.uid end)
	return user_list
end

function CrossChatState:format_status()
	local parts = {string.format('[Own ID: %s]', self.own_id), ''}
	local sorted_ids = {}
	for sid, _ in pairs(self.servers) do
		table.insert(sorted_ids, sid)
	end
	table.sort(sorted_ids)
	for _, sid in ipairs(sorted_ids) do
		local server = self.servers[sid]
		local marker = sid == self.own_id and ' (self)' or ''
		local badge = server.online and 'ONLINE' or 'OFFLINE'
		table.insert(parts, string.format('  %s: %s%s', sid, badge, marker))
		local user_ids = {}
		for uid, _ in pairs(server.users) do
			table.insert(user_ids, uid)
		end
		table.sort(user_ids)
		for _, uid in ipairs(user_ids) do
			local user = server.users[uid]
			table.insert(parts, string.format('    %d (%s)', uid, user.name))
		end
	end
	if not next(self.servers) then
		table.insert(parts, '  (no servers known)')
	end
	return table.concat(parts, '\n')
end

return CrossChatState
