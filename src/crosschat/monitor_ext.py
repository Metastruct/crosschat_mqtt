import json

import click

from aiomonitor import monitor_cli
from aiomonitor.termui.commands import auto_command_done, print_fail


@monitor_cli.command(name='status')
@auto_command_done
def do_status(ctx: click.Context) -> None:
	"""
	Show known servers and their online/users state.
	"""
	monitor = ctx.obj
	state = monitor.console_locals.get('state')
	if state is None:
		print_fail('state not available')
		return
	click.echo(state.format_status())


@monitor_cli.command(name='add')
@click.argument('name')
@auto_command_done
def do_add(ctx: click.Context, name: str) -> None:
	"""
	Add a local user and broadcast to other game servers.

	Usage: add <name>
	"""
	monitor = ctx.obj
	state = monitor.console_locals.get('state')
	tg = monitor.console_locals.get('tg')
	if state is None or tg is None:
		print_fail('state or tg not available')
		return
	user_id = state._next_seq
	tg.create_task(state.add_user(name))
	click.echo(f'User {user_id} ({name}) added with seq {user_id}')


@monitor_cli.command(name='del')
@click.argument('user_id')
@auto_command_done
def do_del(ctx: click.Context, user_id: str) -> None:
	"""
	Remove a local user and notify other game servers.

	Usage: del <id>
	"""
	monitor = ctx.obj
	state = monitor.console_locals.get('state')
	tg = monitor.console_locals.get('tg')
	if state is None or tg is None:
		print_fail('state or tg not available')
		return
	try:
		uid = int(user_id)
	except ValueError:
		print_fail(f'Invalid user id: {user_id}')
		return
	server = state.servers.get(state._own_id)
	user = server.users.get(uid) if server else None
	if user is None:
		print_fail(f'User {user_id} not found')
		return
	user_name = user.name
	tg.create_task(server.del_user(uid))
	click.echo(f'User {user_id} ({user_name}) removed')


@monitor_cli.command(name='msg')
@click.argument('user_id')
@click.argument('message', nargs=-1, required=True)
@auto_command_done
def do_msg(ctx: click.Context, user_id: str, message: tuple[str, ...]) -> None:
	"""
	Send a message to a user on all online game servers.

	Usage: msg <userid> <message>
	"""
	monitor = ctx.obj
	state = monitor.console_locals.get('state')
	client = monitor.console_locals.get('client')
	tg = monitor.console_locals.get('tg')
	if state is None or client is None or tg is None:
		print_fail('state, client or tg not available')
		return
	try:
		uid = int(user_id)
	except ValueError:
		print_fail(f'Invalid user id: {user_id}')
		return
	own_server = state.servers.get(state._own_id)
	if own_server is None or uid not in own_server.users:
		print_fail(f'User {user_id} not found')
		return
	user = own_server.users[uid]
	msg_text = ' '.join(message)
	payload = json.dumps({'msg': msg_text})
	targets = 0
	for sid, server in state.servers.items():
		if sid != state._own_id and server.online:
			targets += 1
			tg.create_task(
				state.publish(f'm/{state._own_id}/{sid}/msg/{user.id}', payload=payload)
			)
	click.echo(f'Message sent to {user_id} ({user.name}) on {targets} online server(s)')


@monitor_cli.command(name='pm')
@click.argument('from_user_id')
@click.argument('target_server_id')
@click.argument('to_user_id')
@click.argument('message', nargs=-1, required=True)
@auto_command_done
def do_pm(ctx: click.Context, from_user_id: str, target_server_id: str, to_user_id: str, message: tuple[str, ...]) -> None:
	"""
	Send a private message from a local user to a user on another server.

	Usage: pm <from_user_id> <target_server_id> <to_user_id> <message>
	"""
	monitor = ctx.obj
	state = monitor.console_locals.get('state')
	client = monitor.console_locals.get('client')
	tg = monitor.console_locals.get('tg')
	if state is None or client is None or tg is None:
		print_fail('state, client or tg not available')
		return
	msg_text = ' '.join(message)
	payload = json.dumps({'msg': msg_text})
	tg.create_task(
		state.publish(f'm/{state._own_id}/{target_server_id}/pm/{from_user_id}/{to_user_id}', payload=payload)
	)
	click.echo(f'PM sent from {from_user_id} to {target_server_id}/{to_user_id}')
