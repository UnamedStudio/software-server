from pathlib import Path
import bpy

def create_object_hierarchy_from_path(
    root: bpy.types.Collection, path: Path, objects: dict[Path, str]
) -> bpy.types.Object:
    parts = path.parts

    if obj_name := objects.get(path):
        return bpy.data.objects[obj_name]

    if len(parts) > 1:
        parent_path = path.parent
        parent = create_object_hierarchy_from_path(root, parent_path, objects)
    else:
        parent = None

    name = ".".join(reversed(parts))

    obj = bpy.data.objects.new(name, bpy.data.meshes.new("_"))
    root.objects.link(obj)
    objects[path] = obj.name

    if parent:
        obj.parent = parent

    return obj
