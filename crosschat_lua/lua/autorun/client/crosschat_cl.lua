local Tag = 'crosschat'
module(Tag, package.seeall)

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

concommand.Add('crosschat_status', function()
	MsgN('[CrossChat] Known servers:')

	for _, server in next, serverdata do
		local count = 0
		for _ in pairs(server.players) do count = count + 1 end
		MsgN('  ' .. server.ServerID .. ' (' .. count .. ' players)')
		local sorted = {}
		for k, v in pairs(server.players) do
			table.insert(sorted, v)
		end
		table.sort(sorted, function(a, b)
			return a.UserID > b.UserID
		end)
		for _, ply in pairs(sorted) do
			if not ply.left then
				MsgN('\t#' .. ply.UserID .. ' ' .. ply.Name .. ' [' .. (ply.SteamID64 or '?') .. ']')
			end
		end
	end
end)

concommand.Add('statusall', function()
	for _, server in next, serverdata do
		MsgN('Server ' .. server.ServerID .. ':')
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

local srvcol = Color(90, 90, 90, 255)
local white = Color(255, 255, 255, 255)
local red = Color(230, 100, 100, 255)
local blue = Color(150, 200, 255, 255)
local green = Color(100, 230, 100)
local grey = Color(200, 200, 200, 255)

local servercolors = {
	['0'] = Color(100, 255, 100, 255)
}

local servernames = {
	['0'] = 'WEB'
}

local crosschat_show = CreateClientConVar('crosschat_show', '1', true, false)
local crosschat_svname = CreateClientConVar('crosschat_svname', '1', true, false)
local crosschat_postfix = CreateClientConVar('crosschat_postfix', '0', true, false)

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

function ConnectionStatus(ServerID, Status)
	Chat(ServerID, true, statuses[tonumber(Status)] or Status)
end

local translate = {'join', 'left', 'say', 'startburst', 'endburst', 'status', 'message'}

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
	elseif what == 'status' then
		local ServerID = net.ReadString()
		local Status = net.ReadUInt(32)
		ConnectionStatus(ServerID, Status)
	elseif what == 'message' then
		local ServerID = net.ReadString()
		local message = net.ReadString()
		ConnectionStatus(ServerID, message)
	else
		dbg('Unhandled message', what or 'NONE??')
	end
end)

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
