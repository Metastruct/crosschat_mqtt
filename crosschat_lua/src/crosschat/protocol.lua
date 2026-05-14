-- CrossChat Protocol
-- MQTT topic parsing, payload serialization, and message routing

local json = json or require('json')

local Protocol = {}

-- Known fields that are not stored in user.extra
local KNOWN_FIELDS = {
	name = true, first_seen = true, server = true,
	burst = true, cmd = true, id = true,
	steamid64 = true, team = true,
}

function Protocol.parse_state_topic(prefix, topic)
	if topic:sub(1, #prefix) ~= prefix then return nil end
	local path = topic:sub(#prefix + 1)
	local parts = {}
	for part in path:gmatch('[^/]+') do
		table.insert(parts, part)
	end
	if parts[1] ~= 'state' or #parts < 3 then return nil end
	return {
		type = 'state',
		server_id = parts[2],
		key = parts[3],
		subkey = parts[4],
	}
end

function Protocol.parse_m_topic(prefix, topic)
	if topic:sub(1, #prefix) ~= prefix then return nil end
	local path = topic:sub(#prefix + 1)
	local parts = {}
	for part in path:gmatch('[^/]+') do
		table.insert(parts, part)
	end
	if parts[1] ~= 'm' or #parts < 4 then return nil end
	local result = {
		type = 'm',
		from_server = parts[2],
		to_server = parts[3],
		endpoint = parts[4],
	}
	if result.endpoint == 'say' and #parts >= 5 then
		result.user_id = tonumber(parts[5])
	elseif result.endpoint == 'pm' and #parts >= 6 then
		result.from_user_id = tonumber(parts[5])
		result.to_user_id = tonumber(parts[6])
	elseif result.endpoint == 'ooc' and #parts >= 5 then
		result.ooc_type = parts[5]
	end
	return result
end

function Protocol.serialize_burst_flag(flag)
	if flag == 'startend' then return 'startend' end
	if flag == 'start' then return 'start' end
	if flag == 'end' then return 'end' end
	if flag == true or flag == 'true' then return true end
	return false
end

function Protocol.build_user_payload(user, cmd, burst_flag, reason)
	local payload = {
		id = user.id,
		cmd = cmd,
		name = user.name,
		first_seen = user.first_seen,
		server = user.server,
		burst = Protocol.serialize_burst_flag(burst_flag),
		steamid64 = user.steamid64,
		team = user.team,
	}
	if cmd == 'leave' then
		local result = {id = user.id, cmd = 'leave'}
		if reason then result.reason = reason end
		return result
	end
	for k, v in pairs(user.extra or {}) do
		payload[k] = v
	end
	return payload
end

function Protocol.extract_user_fields(data)
	local extra = {}
	for k, v in pairs(data) do
		if not KNOWN_FIELDS[k] then
			extra[k] = v
		end
	end
	return {
		name = data.name or 'Unknown',
		first_seen = data.first_seen or os.time(),
		steamid64 = data.steamid64 or '',
		team = data.team or 1,
		extra = extra,
	}
end

function Protocol.build_say_payload(text)
	return {say = text}
end

function Protocol.build_status_payload(started)
	return {started = started}
end

-- Burst flag dispatch
-- Returns: type ('start'|'end'|'both'|nil)
function Protocol.get_burst_action(burst_value)
	if burst_value == 'startend' then return 'both' end
	if burst_value == 'start' then return 'start' end
	if burst_value == 'end' then return 'end' end
	return nil
end

-- Determine burst flag for a user in a burst sequence
function Protocol.get_burst_for_index(index, total)
	if total == 1 then return 'startend' end
	if index == 1 then return 'start' end
	if index == total then return 'end' end
	return true
end

return Protocol
