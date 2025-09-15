import asyncio
from collections.abc import Callable, Iterable
import json
from multiprocessing.shared_memory import SharedMemory
import threading
from typing import Any


class Client:
    def __init__(
        self,
        run_command: Callable[[Any], None],
        on_start: Iterable[Callable[[], None]],
        on_end: Iterable[Callable[[], None]],
    ) -> None:
        self.on = False
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.task: asyncio.Task[None] | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.run_command = run_command
        self.on_start = on_start
        self.on_end = on_end
        self.buffers = dict[str, SharedMemory]()

    def start(self, port: int):
        if not self.on:
            self.on = True
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.task = self.loop.create_task(self.create_task(port))
            self.thread = threading.Thread(daemon=False, target=self.func)
            self.thread.start()

    async def create_task(self, port: int):
        reader, self.writer = await asyncio.open_connection("localhost", port=port)
        for callback in self.on_start:
            callback()
        print("connection started")
        try:
            while True:
                data_length = await reader.read(4)
                if not data_length:
                    print("connection closed")
                    break
                data_length = int.from_bytes(data_length)
                bin = await reader.read(data_length)
                if not bin:
                    print("connection closed")
                    break
                try:
                    data = json.loads(bin.decode())
                    print(f"received: {data}")
                except Exception as e:
                    print(f"unknown data: {e}")
                    continue
                self.run_command(data)

        except asyncio.CancelledError:
            print("connection canceled")
        except ConnectionError:
            print("connection lost")
        finally:
            self.writer.close()
            await self.writer.wait_closed()
            print("connection ended")

    def func(self):
        assert self.loop is not None and self.task is not None
        try:
            self.loop.run_until_complete(self.task)
        except asyncio.CancelledError:
            print("client canceled")
        except ConnectionError:
            print("server not found")
        finally:
            self.loop.close()
            self.loop = None
            self.task = None
            self.thread = None
            self.writer = None
            self.on = False
            for callback in self.on_end:
                callback()
            print("client ended")

    def end(self):
        if self.on:
            assert (
                self.loop is not None
                and self.task is not None
                and self.thread is not None
            )
            self.loop.call_soon_threadsafe(self.task.cancel)
            self.thread.join()

    def send(self, data: Any):
        if not self.writer or not self.loop:
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
            asyncio.create_task(self.writer.drain())

        self.loop.call_soon_threadsafe(send_)
