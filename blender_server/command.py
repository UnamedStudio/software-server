from asyncio import StreamWriter
from dataclasses import dataclass
from multiprocessing.shared_memory import SharedMemory
from pathlib import Path
from typing import Any

from numpy import float32, int32, ndarray
import bpy
import bmesh

from .server_ import Connection

from . import blender_util

root: bpy.types.Collection | None = None


@dataclass
class SyncedMesh:
    obj: bpy.types.Object
    sync: bool


@dataclass
class SyncedXform:
    obj: bpy.types.Object
    sync: bool


class Synced:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self.meshes = dict[Path, SyncedMesh]()
        self.xforms = dict[Path, SyncedXform]()
        self.buffers = dict[str, SharedMemory]()
        self.objects = dict[Path, bpy.types.Object]()


synced: Synced | None = None


def sync_start(connection: Connection):
    global synced
    synced = Synced(connection)


def sync_end():
    global synced
    clear()
    synced = None


def sync():
    assert synced
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for path, synced_mesh in synced.meshes.items():
        if not synced_mesh.sync:
            continue
        mesh = synced_mesh.obj.evaluated_get(depsgraph).to_mesh()
        mesh.calc_loop_triangles()

        positions_shared = create_buffer(size=len(mesh.vertices) * 3 * 4)
        indices_shared = create_buffer(size=len(mesh.loop_triangles) * 3 * 4)

        positions = ndarray(
            shape=len(mesh.vertices) * 3,
            dtype=float32,
            buffer=positions_shared.buf,
        )

        indices = ndarray(
            shape=len(mesh.loop_triangles) * 3, dtype=int32, buffer=indices_shared.buf
        )

        mesh.vertices.foreach_get("co", positions)
        mesh.loop_triangles.foreach_get("vertices", indices)

        synced.connection.send(
            {
                "id": "sync_mesh",
                "params": {
                    "positions_name": positions_shared.name,
                    "indices_name": indices_shared.name,
                    "vertices_length": len(mesh.vertices),
                    "indices_length": len(mesh.loop_triangles) * 3,
                    "path": str(path),
                },
            }
        )

    for path, synced_xform in synced.xforms.items():
        if not synced_xform.sync:
            continue
        obj = synced_xform.obj
        obj = obj.evaluated_get(depsgraph)

        rotation = (
            obj.rotation_quaternion[1],
            obj.rotation_quaternion[2],
            obj.rotation_quaternion[3],
            obj.rotation_quaternion[0],
        )
        synced.connection.send(
            {
                "id": "sync_xform",
                "params": {
                    "translation": obj.location.to_tuple(),
                    "rotation": rotation,
                    "scale": obj.scale.to_tuple(),
                    "path": str(path),
                },
            }
        )


def create_mesh(
    positions_name: str,
    triangles_name: str,
    vertices_length: int,
    triangles_length: int,
    path: Path,
    sync: bool,
):
    mesh = bpy.data.meshes.new("Mesh")
    assert root and synced
    obj = blender_util.create_object_hierarchy_from_path(root, path, synced.objects)

    positions_shared = SharedMemory(name=positions_name)
    triangles_shared = SharedMemory(name=triangles_name)

    verts = ndarray(
        (vertices_length, 3),
        float32,
        positions_shared.buf,
    )
    faces = ndarray(
        (triangles_length, 3),
        int32,
        triangles_shared.buf,
    )
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj.data = mesh

    synced.meshes[path] = SyncedMesh(obj, sync)


def receive_buffer(name: str):
    assert synced
    synced.connection.send(
        {
            "id": "recieve_buffer",
            "params": {
                "name": name,
            },
        }
    )


def create_buffer(size: int) -> SharedMemory:
    assert synced
    ret = SharedMemory(create=True, size=size)
    synced.buffers[ret.name] = ret
    return ret


def release_buffer(name: str):
    assert synced
    assert synced.buffers.pop(name)


def clear():
    assert root and synced
    synced.meshes.clear()
    synced.xforms.clear()
    for obj in synced.objects.values():
        bpy.data.objects.remove(obj, do_unlink=True)
    synced.objects.clear()


def set_xform(
    translation: tuple[float, ...],
    rotation: tuple[float, ...],
    scale: tuple[float, ...],
    path: Path,
    sync: bool,
):
    assert root and synced
    obj = blender_util.create_object_hierarchy_from_path(root, path, synced.objects)
    obj.location = translation
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = (rotation[3], rotation[0], rotation[1], rotation[2])
    obj.scale = scale

    synced.xforms[path] = SyncedXform(obj, sync)


def run(data: Any):
    id = data["id"]
    params = data["params"]

    def run_():
        match id:
            case "create_mesh":
                params["path"] = Path(params["path"])
                create_mesh(**params)
            case "clear":
                clear()
            case "set_xform":
                params["path"] = Path(params["path"])
                set_xform(**params)
            case "received_buffer":
                release_buffer(**params)
            case _:
                print(f"unknown command id {id}")

    bpy.app.timers.register(run_)
