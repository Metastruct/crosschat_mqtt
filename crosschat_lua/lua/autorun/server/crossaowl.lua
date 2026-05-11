-- CrossAowl - Cross-server admin actions via OOC
-- Sends/receives kick/ban/slap commands over crosschat OOC topics
-- Supports steamid64 (broadcast) and server_id+user_id (targeted) modes

local json = json or require('json')
local Tag = 'crossaowl'

-- Defer init because we load before crosschat.lua alphabetically
local function init()
	if not crosschat or not crosschat.SERVER_ID then
		timer.Simple(0, init)
		return
	end

	local function find_player(steamid64)
		for _, ply in ipairs(player.GetAll()) do
			if ply:SteamID64() == steamid64 then
				return ply
			end
		end
	end

	local M = {}

	-- Broadcast by steamid64 (GMod players)
	function M.kick(steamid64, reason, extra)
		reason = reason or 'Kicked by remote admin'
		local payload = json.encode({steamid64 = steamid64, reason = reason, extra = extra or {}})
		crosschat.broadcast_ooc('aowl_kick', payload)
		print('[CrossAowl] Sent kick for steamid64 ' .. steamid64)
	end

	function M.ban(steamid64, reason, extra)
		reason = reason or 'Banned by remote admin'
		local payload = json.encode({steamid64 = steamid64, reason = reason, extra = extra or {}})
		crosschat.broadcast_ooc('aowl_ban', payload)
		print('[CrossAowl] Sent ban for steamid64 ' .. steamid64)
	end

	function M.slap(steamid64, reason, extra)
		reason = reason or 'Slapped by remote admin'
		local payload = json.encode({steamid64 = steamid64, reason = reason, extra = extra or {}})
		crosschat.broadcast_ooc('aowl_slap', payload)
		print('[CrossAowl] Sent slap for steamid64 ' .. steamid64)
	end

	-- Targeted by server_id + user_id (webchat users, broadcast but only target acts)
	function M.kick_user(server_id, user_id, reason, extra)
		reason = reason or 'Kicked by remote admin'
		local payload = json.encode({server_id = server_id, user_id = user_id, reason = reason, extra = extra or {}})
		crosschat.broadcast_ooc('aowl_kick', payload)
		print('[CrossAowl] Sent kick for ' .. server_id .. '/#' .. user_id)
	end

	function M.ban_user(server_id, user_id, reason, extra)
		reason = reason or 'Banned by remote admin'
		local payload = json.encode({server_id = server_id, user_id = user_id, reason = reason, extra = extra or {}})
		crosschat.broadcast_ooc('aowl_ban', payload)
		print('[CrossAowl] Sent ban for ' .. server_id .. '/#' .. user_id)
	end

	function M.slap_user(server_id, user_id, reason, extra)
		reason = reason or 'Slapped by remote admin'
		local payload = json.encode({server_id = server_id, user_id = user_id, reason = reason, extra = extra or {}})
		crosschat.broadcast_ooc('aowl_slap', payload)
		print('[CrossAowl] Sent slap for ' .. server_id .. '/#' .. user_id)
	end

	hook.Add('CrossChatOOC', Tag, function(from_sid, ooc_type, payload)
		if ooc_type ~= 'aowl_kick' and ooc_type ~= 'aowl_ban' and ooc_type ~= 'aowl_slap' then return end

		local ok, data = pcall(json.decode, payload)
		if not ok or type(data) ~= 'table' then return true end

		-- Check if targeted to a specific server
		local target_server = data.server_id
		if target_server and target_server ~= crosschat.SERVER_ID then
			return true -- not for us
		end

		local reason = data.reason or 'No reason'
		local extra = data.extra or {}

		-- Targeted user_id mode (webchat users)
		local user_id = data.user_id
		if user_id then
			print('[CrossAowl] Received ' .. ooc_type .. ' for user_id=' .. user_id .. ' on ' .. crosschat.SERVER_ID)
			return true
		end

		-- SteamID64 mode (GMod players)
		local steamid64 = data.steamid64
		if not steamid64 or steamid64 == '' then return true end

		local target = find_player(steamid64)

		if not target then
			print('[CrossAowl] Player ' .. steamid64 .. ' not found on this server')
			return true
		end

		if ooc_type == 'aowl_kick' then
			hook.Run('CrossAowlKick', steamid64, reason, extra)
			target:Kick(reason)
			print('[CrossAowl] Kicked ' .. steamid64 .. ': ' .. reason)
		elseif ooc_type == 'aowl_ban' then
			hook.Run('CrossAowlBan', steamid64, reason, extra)
			target:Ban(reason)
			print('[CrossAowl] Banned ' .. steamid64 .. ': ' .. reason)
		elseif ooc_type == 'aowl_slap' then
			hook.Run('CrossAowlSlap', steamid64, reason, extra)
			target:Slap()
			target:PrintMessage(HUD_PRINTTALK, '[CrossAowl] You were slapped: ' .. reason)
			print('[CrossAowl] Slapped ' .. steamid64 .. ': ' .. reason)
		end

		return true
	end)

	crossaowl = M
	print('[CrossAowl] Loaded')
end

init()
