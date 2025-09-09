from pathlib import Path
import bpy


def delete_object_recursive(obj: bpy.types.Object):
    for child in obj.children:
        if child:
            delete_object_recursive(child)
    if obj.name in bpy.data.objects:
        bpy.data.objects.remove(obj)


def delete_collection_recursive(
    collection: bpy.types.Collection, delete_self: bool = True
):
    for child_col in collection.children:
        if child_col:
            delete_collection_recursive(child_col)
    for obj in collection.objects:
        if obj:
            delete_object_recursive(obj)

    if delete_self:
        if collection.name in bpy.data.collections:
            bpy.data.collections.remove(collection)


def create_object_hierarchy_from_path(
    root: bpy.types.Collection, path: Path
) -> bpy.types.Object:
    parts = path.parts
    parent_obj = None

    length = len(parts)
    for i in range(length):
        name = ".".join(reversed(parts[: i + 1]))

        obj = bpy.data.objects.get(name)
        if obj is None:
            obj = bpy.data.objects.new(name, bpy.data.meshes.new("_"))
            root.objects.link(obj)

        # Set parent relationship
        if parent_obj:
            obj.parent = parent_obj

        parent_obj = obj

    assert parent_obj

    return parent_obj  # Return last object
