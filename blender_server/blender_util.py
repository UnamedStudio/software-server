from pathlib import Path
import bpy

def create_object_hierarchy_from_path(
    root: bpy.types.Collection, path: Path, objects: dict[Path, bpy.types.Object]
) -> bpy.types.Object:
    parts = path.parts

    if obj := objects.get(path):
        return obj

    if len(parts) > 1:
        parent_path = path.parent
        parent = create_object_hierarchy_from_path(root, parent_path, objects)
    else:
        parent = None

    name = ".".join(reversed(parts))

    obj = bpy.data.objects.new(name, bpy.data.meshes.new("_"))
    root.objects.link(obj)
    objects[path] = obj

    if parent:
        obj.parent = parent

    return obj
