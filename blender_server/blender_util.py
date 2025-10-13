from pathlib import Path
import bpy

def create_object_hierarchy_from_path(
    root: bpy.types.Collection,
    path: Path,
    file_path: Path,
    objects: dict[tuple[Path, Path], str],
    collections: dict[Path, str],
) -> bpy.types.Object:
    parts = path.parts

    if obj_name := objects.get((path, file_path)):
        return bpy.data.objects[obj_name]

    if len(parts) > 1:
        parent_path = path.parent
        parent = create_object_hierarchy_from_path(
            root, parent_path, file_path, objects, collections
        )
    else:
        parent = None

    name = "/".join(reversed(parts))

    obj = bpy.data.objects.new(name, bpy.data.meshes.new("_"))

    if collection_name := collections.get(file_path):
        collection = bpy.data.collections[collection_name]
    else:
        assert bpy.context.scene
        collection_name = "/".join(reversed(file_path.parts))
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)
        collections[file_path] = collection.name

    collection.objects.link(obj)
    objects[(path, file_path)] = obj.name

    if parent:
        obj.parent = parent

    return obj
