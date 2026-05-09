require 'json'
local Tag = 'crosschat'

local config_paths = {'cfg/crosschat.json', 'crosschat.json'}
local config
for _, path in ipairs(config_paths) do
	local data = file.Read(path, 'GAME') or file.Read(path, 'DATA')
	if data then
		local ok, result = pcall(json.decode, data)
		if ok and result then
			config = result
			break
		end
	end
end

if not config or not config.server_id then
	print('[CrossChat] Disabled - no valid cfg/crosschat.json found')

	return
end

module(Tag, package.seeall)
local _M = _M

_M._RAW = setmetatable({}, {
	__index = function(self, key)
		return rawget(_M, key)
	end,
	__newindex = function(self, key, value)
		rawset(_M, key, value)
	end
})

util.AddNetworkString(Tag)

IN_DBG = _RAW.IN_DBG or true

function dbg(...)
	if IN_DBG then
		Msg('[CC] ')
		print(...)
	end
end

function DBG(...)
	Msg('[CC] ')
	print(...)
end

local SERVER_ID = config.server_id
local TOPIC_PREFIX = config.topic_prefix or 'crosschat/'
local META_CONFIG = config.meta or {}

local next_user_id = 1
local servers = {}
local local_users = {}

local subscribers = {}

local translate = {'join', 'left', 'say', 'startburst', 'endburst', 'status', 'message'}
for i = 1, #translate do
	translate[translate[i]] = i
end

local function INT(x, y)
	net.WriteUInt(x, y or 32)
end

local function STR(s)
	net.WriteString(tostring(s or ''))
end

local function TBL(t)
	net.WriteTable(t or {})
end

local function BEGIN(what)
	net.Start(Tag)
	local int = translate[what]
	if not int then return false end
	INT(int, 8)

	return true
end

local function END(where)
	net.Send(where or subscribers)
end

local function publish(topic, payload, retain, qos)
	if not mq.connected() then return nil, 'not connected' end
	local full_topic = TOPIC_PREFIX .. topic
	if type(payload) == 'table' then
		payload = json.encode(payload)
	end

	return mq.send(full_topic, tostring(payload), nil, retain or false, qos or 2)
end

local function get_server(sid)
	if not servers[sid] then
		servers[sid] = {
			id = sid,
			online = false,
			started = 0,
			users = {},
			meta = {},
			states = {},
			bursting = false,
		}
	end

	return servers[sid]
end

local function broadcast(msg_type, ...)
	if not BEGIN(msg_type) then return end
	local args = {...}

	for _, v in ipairs(args) do
		local t = type(v)

		if t == 'number' then
			INT(v)
		elseif t == 'string' then
			STR(v)
		elseif t == 'table' then
			TBL(v)
		end
	end

	END()
end

local function broadcast_all(where, msg_type, ...)
	if not BEGIN(msg_type) then return end
	local args = {...}

	for _, v in ipairs(args) do
		local t = type(v)

		if t == 'number' then
			INT(v)
		elseif t == 'string' then
			STR(v)
		elseif t == 'table' then
			TBL(v)
		end
	end

	END(where)
end

local function set_burst(start, where)
	if start then
		broadcast_all(where, 'startburst')
	else
		broadcast_all(where, 'endburst')
	end
end

local function clean_subscribers()
	for k = #subscribers, 1, -1 do
		if not IsValid(subscribers[k]) then
			table.remove(subscribers, k)
		end
	end
end

concommand.Add('crosschat_status', function(ply)
	if ply and IsValid(ply) and not ply:IsAdmin() and not ply:IsSuperAdmin() then return end
	MsgN('[CrossChat] Server ID: ', SERVER_ID)
	MsgN('[CrossChat] Topic Prefix: ', TOPIC_PREFIX)
	MsgN('[CrossChat] MQTT Connected: ', tostring(mq.connected()))
	MsgN('')

	for sid, server in pairs(servers) do
		local badge = server.online and 'ONLINE' or 'OFFLINE'
		local marker = sid == SERVER_ID and ' (self)' or ''
		local user_count = 0

		for _ in pairs(server.users) do user_count = user_count + 1 end

		MsgN('  ' .. sid .. ': ' .. badge .. marker .. ' (' .. user_count .. ' users)')

		for uid, user in pairs(server.users) do
			if not user.left then
				MsgN('\t#' .. uid .. ' ' .. (user.name or '?'))
			end
		end
	end

	local local_count = 0
	for _ in pairs(local_users) do local_count = local_count + 1 end
	MsgN('')
	MsgN('[CrossChat] Local users: ' .. local_count)
	MsgN('[CrossChat] Client subscribers: ' .. #subscribers)
end)

hook.Add('Think', Tag, clean_subscribers)

local function sync_player(ply)
	local t = {ply}
	set_burst(true, t)

	for uid, user in pairs(local_users) do
		if not user.left then
			broadcast_all(t, 'join', SERVER_ID, uid, user.steamid64 or '', user.name or 'Unknown', user.team or 1, user.extra or {})
		end
	end

	for sid, server in pairs(servers) do
		if sid ~= SERVER_ID then
			for uid, user in pairs(server.users) do
				if not user.left then
					broadcast_all(t, 'join', sid, uid, user.steamid64 or '', user.name or 'Unknown', user.team or 1, user.extra or {})
				end
			end
		end
	end

	set_burst(false, t)
end

local function get_join_packet(ply)
	local connected_this_map = false
	local ok = pcall(function() return ply:ConnectedThisMap() end)
	if ok then
		connected_this_map = ply:ConnectedThisMap()
	end

	return {
		name = ply:Name(),
		steamid64 = ply:SteamID64() or ply:SteamID() or '0',
		team = ply:Team() or 1,
		first_seen = os.time(),
		extra = {
			connected_this_map = connected_this_map,
			user_group = ply:GetUserGroup(),
		}
	}
end

function add_local_user(ply)
	local uid = next_user_id
	next_user_id = next_user_id + 1
	local data = get_join_packet(ply)
	data.id = uid
	local_users[uid] = data

	for sid, server in pairs(servers) do
		if sid ~= SERVER_ID and server.online then
			local payload = {
				id = uid,
				cmd = 'add',
				name = data.name,
				first_seen = tostring(data.first_seen),
				server = SERVER_ID,
				burst = false,
				steamid64 = data.steamid64,
				team = data.team,
			}
			if data.extra then
				for k, v in pairs(data.extra) do
					payload[k] = v
				end
			end
			publish('m/' .. SERVER_ID .. '/' .. sid .. '/user', payload)
		end
	end

	broadcast('join', SERVER_ID, uid, data.steamid64, data.name, data.team, data.extra or {})

	return uid
end

function remove_local_user(ply, reason)
	local uid = ply._crosschat_uid

	if not uid then
		local sid = ply:SteamID64() or ply:SteamID()

		for id, data in pairs(local_users) do
			if data.steamid64 == sid then
				uid = id
				break
			end
		end
	end

	if not uid then return end

	local user = local_users[uid]
	local_users[uid] = nil
	user.left = RealTime()

	for sid, server in pairs(servers) do
		if sid ~= SERVER_ID and server.online then
			publish('m/' .. SERVER_ID .. '/' .. sid .. '/user', {
				id = uid,
				cmd = 'del',
			})
		end
	end

	broadcast('left', SERVER_ID, uid, reason or '')
end

function broadcast_player_update(ply)
	local uid = ply._crosschat_uid

	if not uid then
		local sid = ply:SteamID64() or ply:SteamID()

		for id, data in pairs(local_users) do
			if data.steamid64 == sid then
				uid = id
				break
			end
		end
	end

	if not uid then return end

	local data = get_join_packet(ply)

	for sid, server in pairs(servers) do
		if sid ~= SERVER_ID and server.online then
			local payload = {
				id = uid,
				cmd = 'update',
				name = data.name,
				first_seen = tostring(data.first_seen),
				server = SERVER_ID,
				burst = false,
				steamid64 = data.steamid64,
				team = data.team,
			}
			if data.extra then
				for k, v in pairs(data.extra) do
					payload[k] = v
				end
			end
			publish('m/' .. SERVER_ID .. '/' .. sid .. '/user', payload)
		end
	end
end

function handle_state_status(sid, payload)
	local ok, data = pcall(json.decode, payload)
	if not ok then return end

	local started = data.started or 0
	local server = get_server(sid)
	local prev_started = server.started
	server.started = started
	server.online = started > 0

	if started == prev_started then return end

	if started > 0 then
		DBG('Server online:', sid)
		broadcast('status', sid, 1)

		if sid ~= SERVER_ID then
			local user_list = {}

			for uid, user in pairs(local_users) do
				table.insert(user_list, {uid = uid, user = user})
			end

			local count = #user_list

			for i, entry in ipairs(user_list) do
				local burst_flag

				if count == 1 then
					burst_flag = 'startend'
				elseif i == 1 then
					burst_flag = 'start'
				elseif i == count then
					burst_flag = 'end'
				else
					burst_flag = true
				end

				local payload = {
					id = entry.uid,
					cmd = 'add',
					name = entry.user.name,
					first_seen = tostring(entry.user.first_seen),
					server = SERVER_ID,
					burst = burst_flag,
					steamid64 = entry.user.steamid64,
					team = entry.user.team,
				}

				if entry.user.extra then
					for k, v in pairs(entry.user.extra) do
						payload[k] = v
					end
				end

				publish('m/' .. SERVER_ID .. '/' .. sid .. '/user', payload)
			end

			DBG('User burst sent to', sid, '-', count, 'users')
		end
	else
		DBG('Server offline:', sid)
		broadcast('status', sid, 0)

		for uid, _ in pairs(server.users) do
			broadcast('left', sid, uid, '')
		end

		server.users = {}
	end
end

function handle_m_user(from_sid, payload)
	if from_sid == SERVER_ID then return end
	local ok, data = pcall(json.decode, payload)
	if not ok or not data.id then return end

	local uid = data.id
	local cmd = data.cmd or 'add'
	local server = get_server(from_sid)

	if cmd == 'del' then
		local user = server.users[uid]
		server.users[uid] = nil

		if user then
			broadcast('left', from_sid, uid, '')
		end

		return
	end

	local burst = data.burst

	if burst == 'start' or burst == 'startend' then
		server.bursting = true
	end

	if burst == 'end' or burst == 'startend' then
		server.bursting = false
	end

	local user = server.users[uid]

	if not user then
		user = {
			name = data.name or 'Unknown',
			steamid64 = data.steamid64 or '',
			team = data.team or 1,
			extra = {},
			left = false,
		}
		server.users[uid] = user
	else
		if data.name then user.name = data.name end
		if data.steamid64 then user.steamid64 = data.steamid64 end
		if data.team then user.team = data.team end
	end

	local known = {name = true, first_seen = true, server = true, burst = true, cmd = true, id = true, steamid64 = true, team = true}

	for k, v in pairs(data) do
		if not known[k] then
			user.extra[k] = v
		end
	end

	local burst_action = data.burst

	if burst_action == 'start' or burst_action == 'startend' then
		broadcast('startburst')
	end

	broadcast('join', from_sid, uid, user.steamid64, user.name, user.team, user.extra or {})

	if burst_action == 'end' or burst_action == 'startend' then
		broadcast('endburst')
	end

	dbg('burst user', from_sid, uid, user.name)
end

function handle_m_say(from_sid, uid, payload)
	if from_sid == SERVER_ID then return end
	local ok, data = pcall(json.decode, payload)
	if not ok then return end
	local text = data.say or ''
	local uid_num = tonumber(uid)
	if not uid_num then return end
	broadcast('say', from_sid, uid_num, text)
end

function on_mqtt(topic, payload)
	if topic:sub(1, #TOPIC_PREFIX) ~= TOPIC_PREFIX then return end
	local path = topic:sub(#TOPIC_PREFIX + 1)
	local parts = string.Explode('/', path)

	if parts[1] == 'state' and #parts >= 3 then
		local sid = parts[2]
		local key = parts[3]

		if key == 'status' then
			handle_state_status(sid, payload)
		elseif key == 'meta' and #parts == 3 then
			local ok, data = pcall(json.decode, payload)
			if ok then
				get_server(sid).meta = data
			end
		elseif #parts == 3 then
			get_server(sid).states[key] = payload
		end
	elseif parts[1] == 'm' and #parts >= 5 then
		local from_sid = parts[2]
		local to_sid = parts[3]

		if to_sid ~= SERVER_ID then return end
		local endpoint = parts[4]

		if endpoint == 'user' then
			handle_m_user(from_sid, payload)
		elseif endpoint == 'say' and #parts >= 5 then
			handle_m_say(from_sid, parts[5], payload)
		end
	end
end

net.Receive(Tag, function(len, ply)
	local what = net.ReadUInt(8)

	if what == 1 then
		if not table.HasValue(subscribers, ply) then
			table.insert(subscribers, ply)
		end

		sync_player(ply)
	end
end)

hook.Add('PlayerInitialSpawn', Tag, function(ply)
	timer.Simple(0, function()
		if not IsValid(ply) then return end
		ply._crosschat_uid = add_local_user(ply)
	end)
end)

hook.Add('PlayerSay', Tag, function(ply, txt, teamchat, localchat)
	if teamchat == true or localchat == true then return end
	local ok = pcall(function() return ply:IsBanned() end)

	if ok and ply:IsBanned() then return end

	local uid = ply._crosschat_uid

	if not uid then
		local sid = ply:SteamID64() or ply:SteamID()

		for id, data in pairs(local_users) do
			if data.steamid64 == sid then
				uid = id
				break
			end
		end

		if not uid then return end
	end

	for sid, server in pairs(servers) do
		if sid ~= SERVER_ID and server.online then
			publish('m/' .. SERVER_ID .. '/' .. sid .. '/say/' .. uid, {say = txt})
		end
	end

	broadcast('say', SERVER_ID, uid, txt)
end)

local function handle_player_remove(ply)
	if not IsValid(ply) or not ply:IsPlayer() then return end
	remove_local_user(ply, '')
end

hook.Add('PlayerDisconnected', Tag, handle_player_remove)

hook.Add('ShutDown', Tag, function()
	hook.Remove('PlayerInitialSpawn', Tag)
	hook.Remove('PlayerSay', Tag)
	hook.Remove('PlayerDisconnected', Tag)
	hook.Remove('Think', Tag)
	hook.Remove('OnMQTT', Tag)
	hook.Remove('ShutDown', Tag)
end)

local function publish_own_status()
	if not mq.connected() then return end
	local started = os.time()
	publish('state/' .. SERVER_ID .. '/status', {started = started}, true)
	publish('state/' .. SERVER_ID .. '/meta', META_CONFIG, true)
	DBG('State published, server_id=' .. SERVER_ID .. ', started=' .. started)
end

local function init()
	hook.Add('OnMQTT', Tag, on_mqtt)
	hook.Add('OnMQTTConnected', Tag, function(ok)
		if ok then
			publish_own_status()
		end
	end)

	mq.subscribe(TOPIC_PREFIX .. 'state/+/#')
	mq.subscribe(TOPIC_PREFIX .. 'm/+/' .. SERVER_ID .. '/#')

	if mq.connected() then
		publish_own_status()
	end

	DBG('Initialized, server_id=' .. SERVER_ID)
end

timer.Simple(0, function()
	if mq and mq.set_will then
		mq.set_will(TOPIC_PREFIX .. 'state/' .. SERVER_ID .. '/status', '{"started":0}', 2, true)
	end
end)

timer.Simple(1, function()
	if not mq.connected() then
		timer.Simple(2, init)
	else
		init()
	end
end)
