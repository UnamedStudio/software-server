from __future__ import annotations

from asyncio import (
    StreamWriter,
    StreamReader,
    AbstractEventLoop,
    Task,
    new_event_loop,
    set_event_loop,
    start_server,
    create_task,
    CancelledError,
)
from collections.abc import Callable
import json
import threading
from typing import Any


class Connection:
    def __init__(self, server: Server, writer: StreamWriter) -> None:
        self.server = server
        self.writer = writer

    def send(self, data: Any):
        if not self.server.loop:
            print("no connection")
            return

        def send_():
            if not self.writer:
                print("no connection")
                return
            bin: bytes = json.dumps(data).encode()
            length = len(bin)
            self.writer.write(length.to_bytes(length=4))
            self.writer.write(bin)
            create_task(self.writer.drain())

        self.server.loop.call_soon_threadsafe(send_)


class Server:
    def __init__(
        self,
        run_command: Callable[[Any], None],
        on_connection_start: Callable[[Connection], None],
        on_connection_end: Callable[[], None],
    ) -> None:
        self.on = False
        self.thread: threading.Thread | None = None
        self.loop: AbstractEventLoop | None = None
        self.task: Task[None] | None = None
        self.run_command = run_command
        self.on_connection_start = on_connection_start
        self.on_connection_end = on_connection_end

    def start(self, port: int):
        if not self.on:
            self.on = True
            self.loop = new_event_loop()
            set_event_loop(self.loop)
            self.task = self.loop.create_task(self.create_task(port))
            self.thread = threading.Thread(daemon=False, target=self.func)
            self.thread.start()

    async def create_task(self, port: int):
        server = await start_server(self.handle_client, port=port)
        print(f"server started at port: {port}")
        async with server:
            await server.serve_forever()

    def func(self):
        assert self.loop is not None and self.task is not None
        try:
            self.loop.run_until_complete(self.task)
        except CancelledError:
            print("server canceled")
        finally:
            self.loop.close()
            print("server ended")

    def end(self):
        if self.on:
            self.on = False
            assert (
                self.loop is not None
                and self.task is not None
                and self.thread is not None
            )
            self.loop.call_soon_threadsafe(self.task.cancel)
            self.thread.join()

    async def handle_client(self, reader: StreamReader, writer: StreamWriter):
        addr = writer.get_extra_info("peername")
        print(f"connection: {addr} started")
        self.on_connection_start(Connection(self, writer))

        try:
            try:
                while True:
                    length_bin = await reader.read(4)
                    if not length_bin:
                        print("connection closed")
                        break
                    data_length = int.from_bytes(length_bin)
                    bin = await reader.read(data_length)
                    if not bin:
                        print("connection closed")
                        break
                    try:
                        data = json.loads(bin.decode())
                        print(f"received: {data}")
                    except Exception:
                        print(f"unknown data: {bin}")
                        continue
                    self.run_command(data)

            except CancelledError:
                print(f"connection: {addr} canceled.")
            finally:
                writer.close()
                await writer.wait_closed()
                print(f"connection: {addr} ended")
        except ConnectionError:
            print(f"connection: {addr} lost")
        finally:
            self.on_connection_end()
