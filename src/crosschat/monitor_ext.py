from __future__ import annotations

import asyncio
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


async def _do_add(state, handler, name: str) -> None:
	uid = await state.add_user(name)
	if handler is not None:
		server = state.servers.get(state._own_id)
		if server:
			user = server.users.get(uid)
			if user:
				await handler.on_user(user, 'add')


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
	handler: object | None = monitor.console_locals.get('handler')
	uid = state._next_seq
	tg.create_task(_do_add(state, handler, name))
	click.echo(f'User {uid} ({name}) added with seq {uid}')


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


@monitor_cli.command(name='say')
@click.argument('user_id')
@click.argument('message', nargs=-1, required=True)
@auto_command_done
def do_say(ctx: click.Context, user_id: str, message: tuple[str, ...]) -> None:
	"""
	Send a message to a user on all online game servers.

	Usage: say <userid> <message>
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
	say_text = ' '.join(message)
	payload = json.dumps({'say': say_text})
	targets = 0
	for sid, server in state.servers.items():
		if sid != state._own_id and server.online:
			targets += 1
			tg.create_task(state.publish(f'm/{state._own_id}/{sid}/say/{user.id}', payload=payload))
	handler: object | None = monitor.console_locals.get('handler')
	if handler is not None:
		tg.create_task(handler.on_say(user, say_text))
	click.echo(f'Message sent to {user_id} ({user.name}) on {targets} online server(s)')


@monitor_cli.command(name='pm')
@click.argument('from_user_id', required=False)
@click.argument('target_server_id', required=False)
@click.argument('to_user_id', required=False)
@click.argument('message', nargs=-1, required=False)
@auto_command_done
def do_pm(
	ctx: click.Context, from_user_id: str | None, target_server_id: str | None, to_user_id: str | None, message: tuple[str, ...] | None
) -> None:
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
	if not from_user_id or not target_server_id or not to_user_id or not message:
		print_fail('Usage: pm <from_user_id> <target_server_id> <to_user_id> <message>')
		click.echo('')
		click.echo('Available users:')
		for sid, server in state.servers.items():
			badge = 'ONLINE' if server.online else 'OFFLINE'
			click.echo(f'  {sid} ({badge}):')
			for uid in sorted(server.users):
				user = server.users[uid]
				click.echo(f'    #{uid} - {user.name or "?"}')
		return
	try:
		fuid = int(from_user_id)
	except ValueError:
		print_fail(f'Invalid from_user_id: {from_user_id}')
		return
	try:
		tuid = int(to_user_id)
	except ValueError:
		print_fail(f'Invalid to_user_id: {to_user_id}')
		return
	own = state.servers.get(state._own_id)
	if own is None or fuid not in own.users:
		print_fail(f'Local user #{from_user_id} not found')
		return
	target_server = state.servers.get(target_server_id)
	if target_server is None or not target_server.online:
		print_fail(f'Target server {target_server_id} not found or offline')
		return
	if tuid not in target_server.users:
		print_fail(f'Target user #{to_user_id} not found on {target_server_id}')
		return
	say_text = ' '.join(message)
	payload = json.dumps({'say': say_text})
	tg.create_task(
		state.publish(f'm/{state._own_id}/{target_server_id}/pm/{from_user_id}/{to_user_id}', payload=payload)
	)
	click.echo(f'PM sent from #{from_user_id} ({own.users[fuid].name}) to {target_server_id}/#{to_user_id} ({target_server.users[tuid].name})')


@monitor_cli.command(name='exit')
@auto_command_done
def do_exit(ctx: click.Context) -> None:
	"""
	Exit the application.

	Usage: exit
	"""
	monitor = ctx.obj
	shutdown: asyncio.Event | None = monitor.console_locals.get('shutdown')
	print('Calling for shutdown...')
	if shutdown is not None:
		shutdown.set()
	raise asyncio.CancelledError('exit by user')


@monitor_cli.command(name='quit')
@auto_command_done
def do_quit(ctx: click.Context) -> None:
	"""
	Exit the application.

	Usage: quit
	"""
	monitor = ctx.obj
	shutdown: asyncio.Event | None = monitor.console_locals.get('shutdown')
	print('Calling for shutdown...')
	if shutdown is not None:
		shutdown.set()
	raise asyncio.CancelledError('exit by user')
