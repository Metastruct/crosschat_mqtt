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
