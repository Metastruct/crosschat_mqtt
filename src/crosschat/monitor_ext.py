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
	client = monitor.console_locals.get('client')
	if state is None or client is None:
		print_fail('state or client not available')
		return
	user_id = state._next_seq
	user = state.add_user(user_id, name)
	payload = json.dumps(user.serialize())
	for sid, server in state.servers.items():
		if sid != state._own_id and server.online:
			asyncio.create_task(
				client.publish(f'crosschat/m/{state._own_id}/{sid}/user/{user.id}', payload=payload, qos=2)
			)
	click.echo(f'User {user_id} ({name}) added with seq {user.id}')


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
	client = monitor.console_locals.get('client')
	if state is None or client is None:
		print_fail('state or client not available')
		return
	user = state.remove_user(int(user_id))
	if user is None:
		click.echo(f'User {user_id} not found')
		return
	payload = json.dumps({})
	for sid, server in state.servers.items():
		if sid != state._own_id and server.online:
			asyncio.create_task(
				client.publish(f'crosschat/m/{state._own_id}/{sid}/user/{user.id}/remove', payload=payload, qos=2)
			)
	click.echo(f'User {user_id} removed')


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
	if state is None or client is None:
		print_fail('state or client not available')
		return
	msg_text = ' '.join(message)
	payload = json.dumps({'msg': msg_text})
	targets = 0
	for sid, server in state.servers.items():
		if sid != state._own_id and server.online:
			targets += 1
			asyncio.create_task(
				client.publish(f'crosschat/m/{state._own_id}/{sid}/msg/{user_id}', payload=payload, qos=2)
			)
	click.echo(f'Message sent to {user_id} on {targets} online server(s)')


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
	if state is None or client is None:
		print_fail('state or client not available')
		return
	msg_text = ' '.join(message)
	payload = json.dumps({'msg': msg_text})
	topic = f'crosschat/m/{state._own_id}/{target_server_id}/pm/{from_user_id}/{to_user_id}'
	asyncio.create_task(
		client.publish(topic, payload=payload, qos=2)
	)
	click.echo(f'PM sent from {from_user_id} to {target_server_id}/{to_user_id}')
