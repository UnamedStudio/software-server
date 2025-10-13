from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any
from software_client.client import Client
from multiprocessing.shared_memory import SharedMemory
from numpy.typing import NDArray
from numpy import array, copyto, float32, int32, ndarray


def create_mesh(
    client: Client,
    positions: NDArray[float],
    triangles: NDArray[float],
    path: Path,
    file_path: Path,
    sync: bool,
):
    positions_shared = create_buffer(client, positions.nbytes)
    triangles_shared = create_buffer(client, triangles.nbytes)
    if positions_shared:
        copyto(
            ndarray(positions.shape, positions.dtype, positions_shared.buf), positions
        )
    if triangles_shared:
        copyto(
            ndarray(triangles.shape, triangles.dtype, triangles_shared.buf), triangles
        )
    client.send(
        {
            "id": "create_mesh",
            "params": {
                "positions_name": positions_shared.name if positions_shared else "",
                "triangles_name": triangles_shared.name if triangles_shared else "",
                "vertices_length": len(positions),
                "triangles_length": len(triangles),
                "path": path.as_posix(),
                "file_path": file_path.as_posix(),
                "sync": sync,
            },
        }
    )

def create_cube(
    client: Client,
    size: float,
    path: Path,
    file_path: Path,
):
    client.send(
        {
            "id": "create_cube",
            "params": {
                "size": size,
                "path": path.as_posix(),
                "file_path": file_path.as_posix(),
            },
        }
    )


def create_cylinder(
    client: Client,
    radius: float,
    height: float,
    axis: str,
    path: Path,
    file_path: Path,
):
    client.send(
        {
            "id": "create_cylinder",
            "params": {
                "radius": radius,
                "height": height,
                "axis": axis,
                "path": path.as_posix(),
                "file_path": file_path.as_posix(),
            },
        }
    )


def set_xform(
    client: Client,
    translation: NDArray[float],
    rotation: NDArray[float],
    scale: NDArray[float],
    path: Path,
    file_path: Path,
    sync: bool,
):
    client.send(
        {
            "id": "set_xform",
            "params": {
                "translation": translation.tolist(),
                "rotation": rotation.tolist(),
                "scale": scale.tolist(),
                "path": path.as_posix(),
                "file_path": file_path.as_posix(),
                "sync": sync,
            },
        }
    )


def clear(client: Client):
    client.send({"id": "clear", "params": None})

def receive_buffer(client: Client, name: str):
    client.send(
        {
            "id": "received_buffer",
            "params": {
                "name": name,
            },
        }
    )


class Command:
    id: str
    client: Client

    def run(self, *args, **kwargs): ...


class SyncMesh(Command):
    id = "sync_mesh"

    def __init__(
        self,
        callback: Callable[[NDArray[float32], NDArray[int32], Path, Path, Any], None],
    ) -> None:
        self.callback = callback

    def run(
        self,
        positions_name: str,
        indices_name: str,
        vertices_length: int,
        indices_length: int,
        path: str,
        file_path: Path,
    ):
        positions_shared = SharedMemory(name=positions_name)
        indices_shared = SharedMemory(name=indices_name)
        positions = ndarray(
            vertices_length * 3,
            float32,
            positions_shared.buf,
        ).reshape(-1, 3)
        indices = ndarray(
            indices_length,
            int32,
            indices_shared.buf,
        )
        self.callback(
            positions,
            indices,
            Path(path),
            Path(file_path),
            (positions_shared, indices_shared),
        )
        receive_buffer(self.client, positions_shared.name)
        receive_buffer(self.client, indices_shared.name)

class SyncXform(Command):
    id = "sync_xform"

    def __init__(
        self,
        callback: Callable[
            [NDArray[float], NDArray[float], NDArray[float], Path, Path], None
        ],
    ) -> None:
        self.callback = callback

    def run(
        self,
        translation: tuple[float, ...],
        rotation: tuple[float, ...],
        scale: tuple[float, ...],
        path: str,
        file_path: Path,
    ):
        self.callback(
            array(translation),
            array(rotation),
            array(scale),
            Path(path),
            Path(file_path),
        )


def create_buffer(client: Client, size: int) -> SharedMemory | None:
    if size > 0:
        ret = SharedMemory(create=True, size=size)
        client.buffers[ret.name] = ret
        return ret
    else:
        return None


def release_buffer(client: Client, name: str):
    assert client.buffers.pop(name)


class RunCommands:
    def __init__(self, commands: Iterable[Command], client: Client) -> None:
        self.commands = dict((command.id, command) for command in commands)
        self.client = client

    def run(self, data: Any):
        id = data["id"]
        params = data["params"]
        if id == "received_buffer":
            release_buffer(**params)
        elif command := self.commands.get(id):
            command.client = self.client
            command.run(**params)
        else:
            print(f"unknown command id: {id}")
