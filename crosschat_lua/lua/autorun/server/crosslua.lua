-- CrossLua via CrossChat OOC
-- Replaces the old TCP-based crosslua.lua
-- Sends/receives Lua code over crosschat OOC topics (m/<from>/<to>/ooc/lua)

local json = json or require('json')
local Tag = 'crosslua'

if not crosschat or not crosschat.SERVER_ID then
	print('[CrossLua] CrossChat not loaded')
	return
end

local SERVER_ID = crosschat.SERVER_ID
local pending = {}
local msg_seq = 0

local lua_allow_remote = CreateConVar('lua_allow_remote', '1', {FCVAR_ARCHIVE, FCVAR_NOTIFY})

local function get_online_servers()
	local t = {}
	for sid, srv in pairs(crosschat.GetTable()) do
		if sid ~= SERVER_ID and srv.online then
			t[#t + 1] = sid
		end
	end
	return t
end

local function send_lua(code, target_sid, who, cb)
	local steamid = '?'
	if type(who) == 'Player' then
		steamid = who:SteamID()
	elseif type(who) == 'string' then
		steamid = who
	end

	msg_seq = msg_seq + 1
	local msg_id = msg_seq

	local payload = json.encode({
		id = msg_id,
		code = code,
		steamid = steamid,
	})

	if cb then
		pending[msg_id] = cb
	end

	if target_sid and type(target_sid) == 'string' and crosschat.send_ooc then
		return crosschat.send_ooc(target_sid, 'lua', payload)
	elseif not target_sid then
		local targets = get_online_servers()
		for _, sid in ipairs(targets) do
			if crosschat.send_ooc then
				crosschat.send_ooc(sid, 'lua', payload)
			end
		end
		return #targets > 0
	end
	return false
end

local function run_preprocess_hooks(from_sid, data, reply)
	local hooks = hook.GetTable()
	if not hooks then return end
	local list = hooks.CrossLuaPreprocess
	if not list then return end
	for id, func in pairs(list) do
		local ok, ret1, ret2 = pcall(func, from_sid, data, reply)
		if ok and ret1 ~= nil then
			if ret1 == true then
				return true
			elseif ret1 == false then
				return false, ret2 or 'rejected by hook'
			end
		end
	end
end

hook.Add('CrossChatOOC', Tag, function(from_sid, ooc_type, payload)
	if ooc_type ~= 'lua' and ooc_type ~= 'lua_reply' then return end

	local ok, data = pcall(json.decode, payload)
	if not ok or type(data) ~= 'table' then return true end

	if ooc_type == 'lua_reply' then
		local cb = pending[data.id]
		if cb then
			pending[data.id] = nil
			cb(data.result or data.error or '')
		end
		return true
	end

	if not lua_allow_remote:GetBool() then return true end

	local code = data.code
	local who = data.steamid or '?'
	if not code or code == '' then return true end

	local reply_fn = function(msg)
		local reply = json.encode({id = data.id, result = ('#%s: %s'):format(SERVER_ID, msg)})
		if crosschat.send_ooc then
			crosschat.send_ooc(from_sid, 'lua_reply', reply)
		end
	end

	local handled, reject_msg = run_preprocess_hooks(from_sid, data, reply_fn)
	if handled == true then
		return true
	elseif handled == false then
		reply_fn('ERROR: ' .. tostring(reject_msg))
		return true
	end

	ErrorNoHalt('[CrossLua] from ' .. from_sid .. ' (#' .. (data.id or '?') .. ', ' .. who .. ')\n')
	ErrorNoHalt('> ' .. code .. '\n')

	local result

	if easylua then
		local t = easylua.RunLua(nil, code, '<' .. from_sid .. '|' .. who .. '>')
		if t.error then
			result = 'ERROR: ' .. t.error
		elseif #t.args > 0 then
			for i, v in ipairs(t.args) do
				t.args[i] = tostring(v)
			end
			result = table.concat(t.args, ', ')
		end
	else
		local func = CompileString(code, '<' .. from_sid .. '|' .. who .. '>')
		if func then
			local ok_ret, ret = pcall(func)
			if not ok_ret then
				result = 'ERROR: ' .. tostring(ret)
			elseif ret ~= nil then
				result = tostring(ret)
			end
		else
			result = 'ERROR: syntax check failed'
		end
	end

	if result then
		reply_fn(result)
	end
	return true
end)

local function send_syntax_checked(code, target, who, cb)
	local func = CompileString(code, '')
	if not func then
		if cb then cb('ERROR: syntax check failed') end
		return false
	end
	return send_lua(code, target, who, cb)
end

CrossLua = function(code, target, who, cb)
	if not cb and type(who) == 'function' then
		cb = who
		who = nil
	end
	if not cb and type(target) == 'function' then
		cb = target
		target = nil
	end
	if type(code) ~= 'string' or code == '' then
		error('CrossLua: expected Lua code string')
	end
	return send_syntax_checked(code, target, who, cb)
end

local function register_aowl_commands()
	if not aowl then return end

	aowl.AddCommand('cl', function(ply, line)
		send_syntax_checked(line, nil, ply)
	end, 'developers')

	aowl.AddCommand('bl', function(ply, line)
		local func = CompileString(line, '')
		if func then
			local ok, ret = pcall(func)
			if not ok then
				print('[CrossLua] local error:', tostring(ret))
			elseif ret ~= nil then
				print('[CrossLua] local result:', tostring(ret))
			end
		end
		for _, sid in ipairs(get_online_servers()) do
			send_lua(line, sid, ply)
		end
	end, 'developers')

	local registered = {}

	local function register_sid(sid)
		if sid == SERVER_ID or registered[sid] then return end
		registered[sid] = true
		local sid_closure = sid
		aowl.AddCommand('cl' .. sid, function(ply, line)
			send_syntax_checked(line, sid_closure, ply)
		end, 'developers')
		DBG('CrossLua command registered: cl' .. sid)
	end

	hook.Add('CrossChatServerOnline', Tag, register_sid)

	for sid, srv in pairs(crosschat.GetTable()) do
		if srv.online then register_sid(sid) end
	end
end

timer.Simple(1, register_aowl_commands)

print('[CrossLua] Loaded (OOC)')
