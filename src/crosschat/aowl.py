from __future__ import annotations

import json

import click
import structlog

from aiomonitor import monitor_cli
from aiomonitor.termui.commands import auto_command_done, print_fail

log = structlog.get_logger()


async def _send_cmd(state, tg, ooc_type: str, target, reason: str, extra: dict) -> None:
    payload: dict = {
        'reason': reason,
        'extra': extra,
    }
    if isinstance(target, str):
        payload['steamid64'] = str(target)
    elif isinstance(target, dict):
        payload['server_id'] = target.get('server_id')
        payload['user_id'] = target.get('user_id')

    payload_str = json.dumps(payload)
    targets = 0
    for sid, server in state.servers.items():
        if sid != state._own_id and server.online:
            targets += 1
            tg.create_task(state.send_ooc(sid, ooc_type, payload_str))
    log.info('aowl_cmd', ooc_type=ooc_type, target=target, reason=reason, targets=targets)


# --- steamid64 broadcast commands (existing behavior) ---

@monitor_cli.command(name='aowl_kick')
@click.argument('steamid64')
@click.argument('reason', default='')
@auto_command_done
def do_kick(ctx: click.Context, steamid64: str, reason: str) -> None:
    """Kick a player by SteamID64 (broadcast to all servers).

    Usage: aowl_kick <steamid64> [reason]
    """
    monitor = ctx.obj
    state = monitor.console_locals.get('state')
    tg = monitor.console_locals.get('tg')
    if state is None or tg is None:
        print_fail('state or tg not available')
        return
    reason = reason or 'Kicked by remote admin'
    tg.create_task(_send_cmd(state, tg, 'aowl_kick', steamid64, reason, {}))
    click.echo(f'Kick sent for steamid64 {steamid64}: {reason}')


@monitor_cli.command(name='aowl_ban')
@click.argument('steamid64')
@click.argument('reason', default='')
@auto_command_done
def do_ban(ctx: click.Context, steamid64: str, reason: str) -> None:
    """Ban a player by SteamID64 (broadcast to all servers).

    Usage: aowl_ban <steamid64> [reason]
    """
    monitor = ctx.obj
    state = monitor.console_locals.get('state')
    tg = monitor.console_locals.get('tg')
    if state is None or tg is None:
        print_fail('state or tg not available')
        return
    reason = reason or 'Banned by remote admin'
    tg.create_task(_send_cmd(state, tg, 'aowl_ban', steamid64, reason, {}))
    click.echo(f'Ban sent for steamid64 {steamid64}: {reason}')


@monitor_cli.command(name='aowl_slap')
@click.argument('steamid64')
@click.argument('reason', default='')
@auto_command_done
def do_slap(ctx: click.Context, steamid64: str, reason: str) -> None:
    """Slap a player by SteamID64 (broadcast to all servers).

    Usage: aowl_slap <steamid64> [reason]
    """
    monitor = ctx.obj
    state = monitor.console_locals.get('state')
    tg = monitor.console_locals.get('tg')
    if state is None or tg is None:
        print_fail('state or tg not available')
        return
    reason = reason or 'Slapped by remote admin'
    tg.create_task(_send_cmd(state, tg, 'aowl_slap', steamid64, reason, {}))
    click.echo(f'Slap sent for steamid64 {steamid64}: {reason}')


# --- targeted user_id + server_id commands ---

@monitor_cli.command(name='aowl_kick_user')
@click.argument('server_id')
@click.argument('user_id')
@click.argument('reason', default='')
@auto_command_done
def do_kick_user(ctx: click.Context, server_id: str, user_id: str, reason: str) -> None:
    """Kick a user by server_id + user_id (broadcast, only matching server acts).

    Usage: aowl_kick_user <server_id> <user_id> [reason]
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
        print_fail(f'Invalid user_id: {user_id}')
        return
    reason = reason or 'Kicked by remote admin'
    target = {'server_id': server_id, 'user_id': uid}
    tg.create_task(_send_cmd(state, tg, 'aowl_kick', target, reason, {}))
    click.echo(f'Kick sent for {server_id}/#{uid}: {reason}')


@monitor_cli.command(name='aowl_ban_user')
@click.argument('server_id')
@click.argument('user_id')
@click.argument('reason', default='')
@auto_command_done
def do_ban_user(ctx: click.Context, server_id: str, user_id: str, reason: str) -> None:
    """Ban a user by server_id + user_id (broadcast, only matching server acts).

    Usage: aowl_ban_user <server_id> <user_id> [reason]
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
        print_fail(f'Invalid user_id: {user_id}')
        return
    reason = reason or 'Banned by remote admin'
    target = {'server_id': server_id, 'user_id': uid}
    tg.create_task(_send_cmd(state, tg, 'aowl_ban', target, reason, {}))
    click.echo(f'Ban sent for {server_id}/#{uid}: {reason}')


@monitor_cli.command(name='aowl_slap_user')
@click.argument('server_id')
@click.argument('user_id')
@click.argument('reason', default='')
@auto_command_done
def do_slap_user(ctx: click.Context, server_id: str, user_id: str, reason: str) -> None:
    """Slap a user by server_id + user_id (broadcast, only matching server acts).

    Usage: aowl_slap_user <server_id> <user_id> [reason]
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
        print_fail(f'Invalid user_id: {user_id}')
        return
    reason = reason or 'Slapped by remote admin'
    target = {'server_id': server_id, 'user_id': uid}
    tg.create_task(_send_cmd(state, tg, 'aowl_slap', target, reason, {}))
    click.echo(f'Slap sent for {server_id}/#{uid}: {reason}')
