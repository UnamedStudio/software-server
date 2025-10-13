from asyncio import StreamWriter
from dataclasses import dataclass
from math import pi
from multiprocessing.shared_memory import SharedMemory
from os import unlink
from pathlib import Path
from typing import Any

from numpy import float32, int32, ndarray, array
import bpy
import bmesh
from mathutils import Matrix

from .server_ import Connection

from . import blender_util

collection_name: str | None = None


@dataclass
class SyncedMesh:
    obj_name: str
    sync: bool


@dataclass
class SyncedXform:
    obj_name: str
    sync: bool


class Synced:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection
        self.meshes = dict[tuple[Path, Path], SyncedMesh]()
        self.xforms = dict[tuple[Path, Path], SyncedXform]()
        self.buffers = dict[str, SharedMemory]()
        self.objects = dict[tuple[Path, Path], str]()
        self.collections = dict[Path, str]()


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
        mesh = bpy.data.objects[synced_mesh.obj_name].evaluated_get(depsgraph).to_mesh()
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
                    "path": path[0].as_posix(),
                    "file_path": path[1].as_posix(),
                },
            }
        )

    for path, synced_xform in synced.xforms.items():
        if not synced_xform.sync:
            continue
        obj = bpy.data.objects[synced_xform.obj_name]
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
                    "path": path[0].as_posix(),
                    "file_path": path[1].as_posix(),
                },
            }
        )


def create_mesh(
    positions_name: str,
    triangles_name: str,
    vertices_length: int,
    triangles_length: int,
    path: Path,
    file_path: Path,
    sync: bool,
):
    mesh = bpy.data.meshes.new("Mesh")
    assert collection_name and synced
    collection = bpy.data.collections[collection_name]
    obj = blender_util.create_object_hierarchy_from_path(
        collection, path, file_path, synced.objects, synced.collections
    )

    if positions_name:
        positions_shared = SharedMemory(name=positions_name)
        verts = ndarray(
            (vertices_length, 3),
            float32,
            positions_shared.buf,
        )
    else:
        verts = []
    if triangles_name:
        triangles_shared = SharedMemory(name=triangles_name)
        faces = ndarray(
            (triangles_length, 3),
            int32,
            triangles_shared.buf,
        )
    else:
        faces = []

    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj.data = mesh

    synced.meshes[(path, file_path)] = SyncedMesh(obj.name, sync)

def create_cube(
    size: float,
    path: Path,
    file_path: Path,
):
    mesh = bpy.data.meshes.new("Mesh")
    assert collection_name and synced
    collection = bpy.data.collections[collection_name]
    obj = blender_util.create_object_hierarchy_from_path(
        collection, path, file_path, synced.objects, synced.collections
    )

    half_size = size / 2
    # Define vertices and faces
    verts = array(
        (
            (-1.0, -1.0, -1.0),
            (1.0, -1.0, -1.0),
            (1.0, 1.0, -1.0),
            (-1.0, 1.0, -1.0),
            (-1.0, -1.0, 1.0),
            (1.0, -1.0, 1.0),
            (1.0, 1.0, 1.0),
            (-1.0, 1.0, 1.0),
        )
    )
    verts *= half_size

    faces = [
        (0, 1, 2, 3),  # Bottom
        (4, 5, 6, 7),  # Top
        (0, 1, 5, 4),  # Front
        (2, 3, 7, 6),  # Back
        (1, 2, 6, 5),  # Right
        (3, 0, 4, 7),  # Left
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj.data = mesh

    synced.meshes[(path, file_path)] = SyncedMesh(obj.name, False)

def create_cylinder(
    radius: float,
    height: float,
    axis: str,
    path: Path,
    file_path: Path,
):
    mesh = bpy.data.meshes.new("Mesh")
    assert collection_name and synced
    collection = bpy.data.collections[collection_name]
    obj = blender_util.create_object_hierarchy_from_path(
        collection, path, file_path, synced.objects, synced.collections
    )

    matrix = Matrix.Identity(4)
    if axis == "X":
        matrix = Matrix.Rotation(pi / 2, 4, (0, 1, 0))
    elif axis == "Y":
        matrix = Matrix.Rotation(pi / 2, 4, (-1, 0, 0))
    b_mesh = bmesh.new()
    bmesh.ops.create_cone(
        b_mesh,
        cap_ends=True,
        cap_tris=False,
        segments=32,
        radius1=radius,
        radius2=radius,
        depth=height,
        matrix=matrix,
    )

    # Write the bmesh into the mesh
    b_mesh.to_mesh(mesh)  # type: ignore
    b_mesh.free()

    mesh.update()
    obj.data = mesh

    synced.meshes[(path, file_path)] = SyncedMesh(obj.name, False)


def receive_buffer(name: str):
    assert synced
    synced.connection.send(
        {
            "id": "recieved_buffer",
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
    assert collection_name and synced
    synced.meshes.clear()
    synced.xforms.clear()
    for obj_name in synced.objects.values():
        obj = bpy.data.objects[obj_name]
        bpy.data.objects.remove(obj, do_unlink=True)
    synced.objects.clear()
    for file_collection_name in synced.collections.values():
        collection = bpy.data.collections[file_collection_name]
        bpy.data.collections.remove(collection, do_unlink=True)
    synced.collections.clear()


def set_xform(
    translation: tuple[float, ...],
    rotation: tuple[float, ...],
    scale: tuple[float, ...],
    path: Path,
    file_path: Path,
    sync: bool,
):
    assert collection_name and synced
    collection = bpy.data.collections[collection_name]
    obj = blender_util.create_object_hierarchy_from_path(
        collection, path, file_path, synced.objects, synced.collections
    )
    obj.location = translation
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = (rotation[3], rotation[0], rotation[1], rotation[2])
    obj.scale = scale

    synced.xforms[(path, file_path)] = SyncedXform(obj.name, sync)


def run(data: Any):
    id = data["id"]
    params = data["params"]
    if params:
        if path := params.get("path"):
            params["path"] = Path(path)
        if path := params.get("file_path"):
            params["file_path"] = Path(path)

    def run_():
        match id:
            case "create_mesh":
                create_mesh(**params)
            case "create_cube":
                create_cube(**params)
            case "create_cylinder":
                create_cylinder(**params)
            case "clear":
                clear()
            case "set_xform":
                set_xform(**params)
            case "received_buffer":
                release_buffer(**params)
            case _:
                print(f"unknown command id {id}")

    bpy.app.timers.register(run_)
