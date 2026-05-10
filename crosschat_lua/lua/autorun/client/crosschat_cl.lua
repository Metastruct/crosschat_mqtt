local Tag = 'crosschat'
module(Tag, package.seeall)


local srvcol = Color(90, 90, 90, 255)
local white = Color(255, 255, 255, 255)
local red = Color(230, 100, 100, 255)
local blue = Color(150, 200, 255, 255)
local green = Color(100, 230, 100)
local grey = Color(200, 200, 200, 255)
local orange = Color(255, 180, 80, 255)
local lightblue = Color(150, 200, 255, 255)

_M._RAW = setmetatable({}, {
	__index = function(self, key)
		return rawget(_M, key)
	end,
	__newindex = function(self, key, value)
		rawset(_M, key, value)
	end
})

IN_DBG = _RAW.IN_DBG or true

function dbg(...)
	if IN_DBG then
		Msg('[crosschat CL] ')
		print(...)
	end
end

local ok = util.NetworkStringToID(Tag)

if not ok or ok < 1 then
	ok = false
	IN_DBG = true
	dbg('Crosschat Disabled')

	return
end

local joinburst = false

function IsJoinBurst()
	return joinburst
end

local function UNDECOR(txt)
	return txt
end

serverdata = _RAW.serverdata or {}
local serverdata = serverdata

concommand.Add('crosschat_status', function(ply, cmd, args, arg_str)
	local full = arg_str and arg_str:find"full"
	MsgC(white, '[CrossChat] user list:\n')

	for _, server in next, serverdata do
		local active = 0
		local sorted = {}
		for k, v in pairs(server.players) do
			if not v.left then active = active + 1 end
			table.insert(sorted, v)
		end
		local total = table.Count(server.players)
		MsgC(orange, '  ' .. server.ServerID)
		MsgC(grey, ' (' .. active)
		if full then
			MsgC(grey, '/' .. total)
		end
		MsgC(grey, ' players)\n')

		table.sort(sorted, function(a, b)
			return a.UserID > b.UserID
		end)

		for _, ply in pairs(sorted) do
			if full or not ply.left then
				if ply.left then
					MsgC(red, '  ☐ ')
				else
					MsgC(green, '  ☑ ')
				end
				MsgC(grey, '#' .. ply.UserID .. ' ')
				MsgC(white, ply.Name)
				MsgC(grey, ' [' .. (ply.SteamID64 or '?') .. ']')
				if ply.left then
					MsgC(red, ' left')
				end
				MsgC(white, '\n')

				if full and ply.extra then
					local extra_keys = {}
					for k, v in pairs(ply.extra) do
						local clr
						if type(v) == 'boolean' then
							clr = v and blue or red
						else
							clr = lightblue
						end
						table.insert(extra_keys, {key = k, color = clr})
					end
					if #extra_keys > 0 then
						table.sort(extra_keys, function(a, b) return a.key < b.key end)
						MsgC(grey, '    extra: ')
						for i, entry in ipairs(extra_keys) do
							MsgC(entry.color, entry.key)
							if i < #extra_keys then
								MsgC(grey, ', ')
							end
						end
						MsgC(white, '\n')
					end
				end
			end
		end
	end
end)

concommand.Add('statusall', function()
	for _, server in next, serverdata do
		local count = 0
		for k, v in pairs(server.players) do
			if not v.left then count = count + 1 end
		end
		MsgN('Server ' .. server.ServerID .. ' (' .. count .. ' players):')
		local sorted = {}

		for k, v in pairs(server.players) do
			table.insert(sorted, v)
		end

		table.sort(sorted, function(a, b)
			return a.UserID > b.UserID
		end)

		for _, ply in pairs(sorted) do
			if not ply.left then
				MsgN('\t', '#' .. ply.UserID, ' \t', ply.Name, ' \t', ply.SteamID64, ' \t', team.GetName(ply.Team))
			end
		end
	end

	MsgN('LocalServer:')
	local sorted = {}

	for k, v in pairs(player.GetAll()) do
		table.insert(sorted, v)
	end

	table.sort(sorted, function(a, b)
		return a:UserID() > b:UserID()
	end)

	for _, ply in pairs(sorted) do
		MsgN('\t', '#' .. ply:UserID(), ' \t', ply:Name(), ' \t', ply:SteamID64(), ' \t', team.GetName(ply:Team()))
	end
end)

function GetServer(ServerID)
	local dat = serverdata[ServerID]

	if not dat then
		dat = {
			ServerID = ServerID,
			players = {}
		}

		serverdata[ServerID] = dat
	end

	return dat
end

function GetPlayer(ServerID, UserID)
	local dat = serverdata[ServerID]
	if not dat then return false end
	local ply = dat.players[UserID]

	return ply
end


local servercolors = {
	['0'] = Color(100, 255, 100, 255)
}

local servernames = {
	['0'] = 'WEB'
}

local crosschat_show = CreateClientConVar('crosschat_show', '1', true, false)
local crosschat_svname = CreateClientConVar('crosschat_svname', '1', true, false, 'Show server name prefix on crosschat messages')
local crosschat_postfix = CreateClientConVar('crosschat_postfix', '0', true, false, 'Show server name as postfix instead of prefix')
local crosschat_joinsummary = CreateClientConVar('crosschat_joinsummary', '1', true, false)

function ChatX(console_only, ServerID, needid, ...)
	if not crosschat_show:GetBool() then return end
	local servername = servernames[ServerID] or ('#' .. ServerID)
	local srvcol = servercolors[ServerID] or srvcol
	local chat_data

	if crosschat_svname:GetBool() or needid then
		if crosschat_postfix:GetBool() then
			chat_data = {white, ...}

			table.insert(chat_data, srvcol)
			table.insert(chat_data, ' ' .. servername)
		else
			chat_data = {srvcol, servername .. ' ', white, ...}
		end
	else
		chat_data = {white, ...}
	end

	if console_only then
		table.insert(chat_data, '\n')
		MsgC(unpack(chat_data))
	else
		chat.AddText(unpack(chat_data))
	end

	dbg('Chat', ServerID, ...)
end

function Chat(...)
	return ChatX(false, ...)
end

function ChatConsole(...)
	return ChatX(false, ...)
end

local function sid32ify(s)
	if not s or s == '' or not tonumber(s) then return '?' end
	local sid32 = util.SteamIDFrom64(s)
	if sid32 and sid32 ~= '' then return sid32 end

	return s
end

local function GetPlayerData(ply_data, team_id)
	if not ply_data then return Color(255, 0, 0), 'WTF' end
	local nick = UNDECOR(ply_data.Name) or 'WTF'
	local chat_pastelize = GetConVar('easychat_pastel')
	local ply_col = team.GetColor(team_id or 0)

	if EasyChat and chat_pastelize and chat_pastelize:GetBool() then
		ply_col = EasyChat.PastelizeNick(nick)
	end

	return ply_col, nick
end

function PlayerJoin(ServerID, UserID, Name, SteamID64, Team, extra)
	local server = GetServer(ServerID)

	local playerdata = {
		server = server,
		ServerID = ServerID,
		SteamID64 = SteamID64,
		Name = Name,
		UserID = UserID,
		Team = Team,
		left = false,
		extra = extra
	}

	local playerdata_old = server.players[UserID]
	hook.Run('CPlayerData', playerdata, playerdata_old)

	if playerdata_old and playerdata_old.left then
		dbg('join', '(had left, ignoring previous data)', ServerID, UserID, SteamID64, Name)
		playerdata_old = nil
	end

	if playerdata_old then
		local t = playerdata_old.extra

		if t then
			for k, v in pairs(playerdata.extra or {}) do
				t[k] = v
			end

			playerdata.extra = nil
		end

		for k, v in next, playerdata do
			playerdata_old[k] = v
		end
	else
		server.players[UserID] = playerdata
	end

	dbg('join', ServerID, UserID, SteamID64, Name, joinburst and 'joinburst' or '')

	if next(extra or {}) then
		dbg('joinextra=', table.ToString(extra))
	end

	local console_only = joinburst or (extra and not extra.connected_this_map)
	local ply = GetPlayer(ServerID, UserID)

	if not ply then
		dbg('join', 'No player', ServerID, UserID)

		return
	end

	local ply_col, nick = GetPlayerData(ply, Team)
	ChatX(console_only, ServerID, nil, 'Player ', ply_col, nick, grey, ' (' .. sid32ify(ply.SteamID64) .. ')', green, ' joined')
end

function PlayerLeft(ServerID, UserID, why)
	local ply = GetPlayer(ServerID, UserID)

	if not ply then
		dbg('leave', 'No player', ServerID, UserID, why)

		return
	end

	ply.left = RealTime()
	why = #why > 0 and string.format(' (%s)', why) or ''
	local ply_col, nick = GetPlayerData(ply, ply.Team)
	ChatX(joinburst, ServerID, nil, 'Player ', ply_col, nick, grey, ' (' .. sid32ify(ply.SteamID64) .. ')', red, ' left', white, why)
end

local function ProcessMentions(text, server_id, player_color, player_nick)
	local text_color = white
	if not crosschat_show:GetBool() then return text_color end
	if not EasyChat then return text_color end
	if not EasyChat.Mentions then return text_color end
	local mentions_flash = GetConVar('easychat_mentions_flash_window')

	if EasyChat.Mentions:IsMention(text) then
		if mentions_flash:GetBool() then
			system.FlashWindow()
		end

		local lp = LocalPlayer()

		local data = {('#%s '):format(server_id), player_color, player_nick, EasyChat.Mentions:GetColor(), ' ' .. text}

		if not system.HasFocus() or (lp.IsAFK and lp:IsAFK()) then
			EasyChat.Mentions:AddMissedMention(data)
		end

		return EasyChat.Mentions:GetColor()
	end

	return text_color
end

_RAW.gagged = _RAW.gagged or {}

function PlayerSay(ServerID, UserID, Txt)
	local server = serverdata[ServerID]

	if not server then
		ErrorNoHalt('No server??', ServerID)

		return
	end

	local ply = GetPlayer(ServerID, UserID)

	if not ply then
		dbg('No player ' .. tostring(UserID) .. '??')
		return
	end

	if gagged[ply.SteamID64] then return end
	hook.Run('CrossChatSay', ServerID, UserID, Txt, ply)
	local ply_col, nick = GetPlayerData(ply, ply.Team)
	local text_color = ProcessMentions(Txt, ServerID, ply_col, nick)
	Chat(ServerID, nil, ply_col, nick, text_color, ': ' .. Txt)
end

local statuses = {
	[0] = 'Connection lost!',
	[1] = 'Server has come online!'
}

function PlayerPM(ServerID, UserID, Name, Txt)
	local ply_col, nick = GetPlayerData({Name = Name}, 0)
	Chat(ServerID, nil, Color(150, 200, 255, 255), '[PM] ', ply_col, nick, white, ': ' .. Txt)
end

function ConnectionStatus(ServerID, Status)
	Chat(ServerID, true, statuses[tonumber(Status)] or Status)
end

local translate = {'join', 'left', 'say', 'startburst', 'endburst', 'status', 'message', 'pm'}

for i = 1, #translate do
	translate[translate[i]] = i
end

net.Receive(Tag, function(len)
	local what = net.ReadUInt(8)
	local what_s = translate[what] or what
	if type(what_s) == 'number' then
		dbg('net.Receive: unknown type', what)
		return
	end
	what = what_s
	dbg('net.Receive:', what)

	if what == 'join' then
		local ServerID = net.ReadString()
		local UserID = net.ReadUInt(32)
		local SteamID64 = net.ReadString()
		local Name = net.ReadString()
		local Team = net.ReadUInt(32)
		local extra = net.ReadTable()
		dbg('net.Receive join:', ServerID, UserID, Name)
		PlayerJoin(ServerID, UserID, Name, SteamID64, Team, extra)
		dbg('net.Receive join done, serverdata count:', table.Count(serverdata))
	elseif what == 'left' then
		local ServerID = net.ReadString()
		local UserID = net.ReadUInt(32)
		local why = net.ReadString()
		PlayerLeft(ServerID, UserID, why)
	elseif what == 'say' then
		local ServerID = net.ReadString()
		local UserID = net.ReadUInt(32)
		local Txt = net.ReadString()
		PlayerSay(ServerID, UserID, Txt)
	elseif what == 'startburst' then
		dbg('net.Receive: startburst')
		joinburst = true
	elseif what == 'endburst' then
		dbg('net.Receive: endburst')
		joinburst = false
		if crosschat_joinsummary:GetBool() then PrintSummary() end
	elseif what == 'status' then
		local ServerID = net.ReadString()
		local Status = net.ReadUInt(32)
		ConnectionStatus(ServerID, Status)
	elseif what == 'message' then
		local ServerID = net.ReadString()
		local message = net.ReadString()
		ConnectionStatus(ServerID, message)
	elseif what == 'pm' then
		local ServerID = net.ReadString()
		local UserID = net.ReadUInt(32)
		local Name = net.ReadString()
		local Txt = net.ReadString()
		PlayerPM(ServerID, UserID, Name, Txt)
	else
		dbg('Unhandled message', what or 'NONE??')
	end
end)

function GetTable()
	return serverdata
end

function PrintSummary()
	local data = GetTable()
	local total_players = 0
	local sids = {}
	for sid, _ in pairs(data) do table.insert(sids, sid) end
	table.sort(sids)
	chat.AddText(Color(255, 180, 80, 255), '[CrossChat] ', Color(255, 255, 255, 255), 'Connected to ' .. #sids .. ' server' .. (#sids ~= 1 and 's' or '') .. ':')
	for _, sid in ipairs(sids) do
		local server = data[sid]
		local active = 0
		for _, v in pairs(server.players) do
			if not v.left then active = active + 1 end
		end
		local color = servercolors[sid] or Color(200, 200, 200, 255)
		chat.AddText(Color(150, 150, 150, 255), '  ', color, sid, Color(255, 255, 255, 255), ' (' .. active .. ' player' .. (active ~= 1 and 's' or '') .. ')')
		total_players = total_players + active
	end
	chat.AddText(Color(150, 150, 150, 255), 'Total: ', Color(255, 255, 255, 255), tostring(total_players) .. ' player' .. (total_players ~= 1 and 's' or ''))
end

function SendPM(target_server, target_user_id, message)
	target_user_id = tonumber(target_user_id)
	if not target_server or not target_user_id or not message or message == '' then return false end
	net.Start(Tag)
	net.WriteUInt(2, 8)
	net.WriteString(target_server)
	net.WriteUInt(target_user_id, 32)
	net.WriteString(message)
	net.SendToServer()
	return true
end

function PrintPMUsage(cmd)
	chat.AddText(Color(255, 180, 80, 255), '[CrossChat] ', Color(255, 255, 255, 255), 'Usage: ' .. cmd .. ' <target_server> <target_user_id> <message>')
	local data = GetTable()
	for sid, server in pairs(data) do
		local count = 0
		for uid, user in pairs(server.players) do
			if not user.left then
				chat.AddText(Color(255, 255, 255, 255), '  ' .. sid .. ' #' .. uid .. ' - ' .. (user.Name or '?'))
				count = count + 1
			end
		end
		if count == 0 then
			chat.AddText(Color(200, 200, 200, 255), '  ' .. sid .. ': (no players)')
		end
	end
end

local _next_ac_print = 0
local function pm_autocomplete(cmd, arg_str, args)
	local t = {}
	local data = GetTable()
	local argn = #args
	if argn == 0 then
		if os.time() >= _next_ac_print then PrintPMUsage(cmd) end
		for sid, _ in pairs(data) do
			table.insert(t, cmd .. ' ' .. sid)
		end
	elseif argn == 1 then
		local typed = args[1]
		local server = data[typed]
		if server then
			for uid, user in pairs(server.players) do
				if not user.left then
					table.insert(t, cmd .. ' ' .. typed .. ' ' .. tostring(uid) .. ' - ' .. (user.Name or '?'))
				end
			end
		else
			local typed_lower = typed:lower()
			for sid, srv in pairs(data) do
				for uid, user in pairs(srv.players) do
					if not user.left then
						local name_match = (user.Name or ''):lower():sub(1, #typed_lower) == typed_lower
						local id_match = tostring(uid):sub(1, #typed) == typed
						if name_match or id_match then
							table.insert(t, cmd .. ' ' .. sid .. ' ' .. tostring(uid) .. ' - ' .. (user.Name or '?'))
						end
					end
				end
			end
		end
	elseif argn >= 2 then
		table.insert(t, cmd .. ' ' .. args[1] .. ' ' .. args[2].. ' ')
	end
	_next_ac_print = os.time() + 60
	return t
end

local function pm_cmd(ply, cmd, args, arg_str)
	if not args[1] or not args[2] then
		PrintPMUsage(cmd)
		return
	end
	local target_server = args[1]
	local target_user_id = tonumber(args[2])
	if not target_user_id then
		chat.AddText(Color(255, 180, 80, 255), '[CrossChat] ', Color(255, 255, 255, 255), 'Invalid target_user_id')
		return
	end
	local msg = table.concat(args, ' ', 3)
	SendPM(target_server, target_user_id, msg)
end
concommand.Add('crosschat_pm', pm_cmd, pm_autocomplete, 'Send a private message to a player on another server. Usage: crosschat_pm <target_server> <target_user_id> <message>')
concommand.Add('pm', pm_cmd, pm_autocomplete, 'Send a private message to a player on another server. Usage: crosschat_pm <target_server> <target_user_id> <message>')

timer.Simple(1, function()
	if util.NetworkStringToID(Tag) < 1 then
		dbg('Network string not ready, retrying...')
		timer.Simple(1, function()
			if util.NetworkStringToID(Tag) < 1 then
				dbg('Network string never ready, giving up')
				return
			end
			net.Start(Tag)
			net.WriteUInt(1, 8)
			joinburst = true
			net.SendToServer()
			dbg('subscription sent (retry)')
		end)
		return
	end
	net.Start(Tag)
	net.WriteUInt(1, 8)
	joinburst = true
	net.SendToServer()
	dbg('subscription sent')
end)
