bl_info = {
    "name": "Blender Server",
    "author": "whiting@1712428442",
    "version": (0, 1),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Server",
    "description": "Become a server that can be use by other process",
    "category": "Server",
}

import atexit
import importlib
from typing import get_type_hints
import bpy
from bpy.types import Context

from . import blender_util
from . import server_
from . import command

for submod in (server_, command, blender_util):
    importlib.reload(submod)

server: server_.Server | None = None


def unload():
    if server:
        server.end()


atexit.register(unload)

property_group_idname = "blender_server_property_group"


class PropertyGroup(bpy.types.PropertyGroup):
    port: bpy.props.IntProperty(name="port", default=8888)


class StartOperator(bpy.types.Operator):
    bl_idname = "blender_server.start_operator"
    bl_label = "Start"

    def execute(self, context: Context) -> ...:
        assert bpy.context.collection
        command.root = bpy.data.collections.new("Server")
        bpy.context.collection.children.link(command.root)
        assert server
        property_group: PropertyGroup = getattr(context.scene, property_group_idname)
        server.start(property_group.port)
        return {"FINISHED"}


class EndOperator(bpy.types.Operator):
    bl_idname = "blender_server.end_operator"
    bl_label = "End"

    def execute(self, context: Context) -> ...:
        if command.root:
            blender_util.delete_collection_recursive(command.root)
        assert server
        server.end()
        return {"FINISHED"}


class SyncOperator(bpy.types.Operator):
    bl_idname = "blender_server.sync_operator"
    bl_label = "Sync"

    def execute(self, context: Context) -> ...:
        command.sync()
        return {"FINISHED"}


class Pannel(bpy.types.Panel):
    bl_label = "Server"
    bl_idname = "blender_server.panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Server"

    def draw(self, context):
        layout = self.layout
        assert layout is not None
        property_group = getattr(context.scene, property_group_idname)
        for name in get_type_hints(PropertyGroup).keys():
            layout.prop(property_group, name)
        layout.operator(StartOperator.bl_idname, text="Start")
        layout.operator(EndOperator.bl_idname, text="End")
        layout.operator(SyncOperator.bl_idname, text="Sync")


classes = [PropertyGroup, StartOperator, EndOperator, SyncOperator, Pannel]


def register():
    global server
    server = server_.Server(command.run, command.sync_start, command.sync_end)
    for cls in classes:
        bpy.utils.register_class(cls)
    setattr(
        bpy.types.Scene,
        property_group_idname,
        bpy.props.PointerProperty(type=PropertyGroup),
    )


def unregister():
    assert server
    server.end()
    if command.root:
        blender_util.delete_collection_recursive(command.root)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    property_group = getattr(bpy.types.Scene, property_group_idname)
    del property_group


if __name__ == "__main__":
    register()
