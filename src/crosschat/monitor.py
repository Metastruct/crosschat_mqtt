from aiomonitor import Monitor


class CrossChatMonitor(Monitor):
	async def _ui_main_async(self) -> None:
		loop = asyncio.get_running_loop()
		self._termination_info_queue = janus.Queue()
		self._cancellation_chain_queue = janus.Queue()
		self._ui_loop = loop
		self._ui_forever_future = loop.create_future()
		self._ui_termination_handler_task = loop.create_task(
			self._ui_handle_termination_updates()
		)
		self._ui_cancellation_handler_task = loop.create_task(
			self._ui_handle_cancellation_updates()
		)
		telnet_server = TelnetServer(
			interact=functools.partial(interact, self),
			host=self._host,
			port=self._termui_port,
		)
		telnet_server.start()
		await asyncio.sleep(0)
		self._ui_started.set()
		try:
			await self._ui_forever_future
		except asyncio.CancelledError:
			pass
		finally:
			termui_tasks = {*self._termui_tasks}
			for termui_task in termui_tasks:
				termui_task.cancel()
			await asyncio.gather(*termui_tasks, return_exceptions=True)
			self._ui_termination_handler_task.cancel()
			self._ui_cancellation_handler_task.cancel()
			with contextlib.suppress(asyncio.CancelledError):
				await self._ui_termination_handler_task
			with contextlib.suppress(asyncio.CancelledError):
				await self._ui_cancellation_handler_task
			await telnet_server.stop()
