import bpy
from bpy.props import StringProperty, BoolProperty
from bpy.types import AddonPreferences
from bpy.utils import register_class, unregister_class

import os
import sys

from . import io, engine

MITSUBA_VERSION = '3.8.0'

def get_addon_preferences(context):
    return context.preferences.addons[__package__].preferences

def _ensure_extensions_local_in_path():
    # Blender should add the extensions .local path automatically, but add it
    # explicitly as a fallback in case the addon loads before it's set up.
    # __file__ is .../extensions/user_default/mitsuba_blender/__init__.py
    # so three dirname calls reach .../extensions/
    tag = f'python{sys.version_info.major}.{sys.version_info.minor}'
    extensions_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
    local_site = os.path.join(extensions_dir, '.local', 'lib', tag, 'site-packages')
    if os.path.isdir(local_site) and local_site not in sys.path:
        sys.path.insert(0, local_site)

def init_mitsuba(context):
    try:
        _ensure_extensions_local_in_path()
        os.environ['DRJIT_NO_RTLD_DEEPBIND'] = 'True'
        should_reload = 'mitsuba' in sys.modules
        import mitsuba
        if should_reload:
            import importlib
            importlib.reload(mitsuba)
        mitsuba.set_variant('scalar_rgb')
        from mitsuba import ThreadEnvironment
        bpy.types.Scene.thread_env = ThreadEnvironment()
        return True
    except Exception as e:
        print(f'mitsuba-blender: failed to load Mitsuba: {e}')
        return False

def try_register_mitsuba(context):
    prefs = get_addon_preferences(context)
    prefs.mitsuba_status_message = ''

    could_init = False
    if prefs.using_mitsuba_custom_path:
        update_additional_custom_paths(prefs, context)
        could_init = init_mitsuba(context)
        if could_init:
            import mitsuba
            prefs.mitsuba_custom_version = mitsuba.__version__
            if prefs.has_valid_mitsuba_custom_version:
                prefs.mitsuba_status_message = f'Found custom Mitsuba v{prefs.mitsuba_custom_version}.'
            else:
                prefs.mitsuba_status_message = f'Found custom Mitsuba v{prefs.mitsuba_custom_version}. Supported version is v{MITSUBA_VERSION}.'
        else:
            prefs.mitsuba_status_message = 'Failed to load custom Mitsuba. Please verify the path to the build directory.'
    else:
        could_init = init_mitsuba(context)
        if could_init:
            import mitsuba
            prefs.mitsuba_status_message = f'Mitsuba v{mitsuba.__version__} ready.'
        else:
            prefs.mitsuba_status_message = 'Mitsuba not found. Try reinstalling the extension.'

    prefs.is_mitsuba_initialized = could_init

    if could_init:
        io.register()
        engine.register()

    return could_init

def try_unregister_mitsuba():
    try:
        io.unregister()
        engine.unregister()
        return True
    except RuntimeError:
        return False

def try_reload_mitsuba(context):
    try_unregister_mitsuba()
    if try_register_mitsuba(context):
        bpy.ops.wm.save_userpref()

def clean_additional_custom_paths(self, context):
    if self.additional_python_path in sys.path:
        sys.path.remove(self.additional_python_path)
    if self.additional_path and self.additional_path in os.environ['PATH']:
        items = os.environ['PATH'].split(os.pathsep)
        items.remove(self.additional_path)
        os.environ['PATH'] = os.pathsep.join(items)

def update_additional_custom_paths(self, context):
    build_path = bpy.path.abspath(self.mitsuba_custom_path)
    if len(build_path) > 0:
        clean_additional_custom_paths(self, context)
        self.additional_path = build_path
        if self.additional_path not in os.environ['PATH']:
            os.environ['PATH'] += os.pathsep + self.additional_path
        self.additional_python_path = os.path.join(build_path, 'python')
        if self.additional_python_path not in sys.path:
            sys.path.insert(0, self.additional_python_path)

def update_using_mitsuba_custom_path(self, context):
    self.require_restart = True
    if self.using_mitsuba_custom_path:
        update_mitsuba_custom_path(self, context)
    else:
        clean_additional_custom_paths(self, context)

def update_mitsuba_custom_path(self, context):
    if self.is_mitsuba_initialized:
        self.require_restart = True
    if self.using_mitsuba_custom_path and len(self.mitsuba_custom_path) > 0:
        update_additional_custom_paths(self, context)
        if not self.is_mitsuba_initialized:
            try_reload_mitsuba(context)

def update_mitsuba_custom_version(self, context):
    self.has_valid_mitsuba_custom_version = self.mitsuba_custom_version == MITSUBA_VERSION

class MitsubaPreferences(AddonPreferences):
    bl_idname = __package__

    is_mitsuba_initialized: BoolProperty(name='Is Mitsuba initialized')

    mitsuba_status_message: StringProperty(name='Status message', default='')

    require_restart: BoolProperty(name='Require a Blender restart')

    using_mitsuba_custom_path: BoolProperty(
        name='Using custom Mitsuba path',
        update=update_using_mitsuba_custom_path,
    )

    mitsuba_custom_path: StringProperty(
        name='Custom Mitsuba path',
        description='Path to the custom Mitsuba build directory',
        default='',
        subtype='DIR_PATH',
        update=update_mitsuba_custom_path,
    )

    mitsuba_custom_version: StringProperty(
        name='Custom Mitsuba build version',
        default='',
        update=update_mitsuba_custom_version,
    )

    has_valid_mitsuba_custom_version: BoolProperty(name='Has valid custom Mitsuba version')

    additional_path: StringProperty(name='Addition to PATH', default='', subtype='DIR_PATH')

    additional_python_path: StringProperty(name='Addition to sys.path', default='', subtype='DIR_PATH')

    def draw(self, context):
        layout = self.layout

        row = layout.row()
        if self.require_restart:
            row.alert = True
            row.label(text='A restart is required to apply the changes.', icon='ERROR')
        elif self.is_mitsuba_initialized and (not self.using_mitsuba_custom_path or self.has_valid_mitsuba_custom_version):
            row.label(text=self.mitsuba_status_message, icon='CHECKMARK')
        else:
            row.alert = True
            row.label(text=self.mitsuba_status_message, icon='ERROR')

        box = layout.box()
        box.label(text='Advanced Settings')
        box.prop(self, 'using_mitsuba_custom_path', text=f'Use custom Mitsuba path (supported version: v{MITSUBA_VERSION})')
        if self.using_mitsuba_custom_path:
            box.prop(self, 'mitsuba_custom_path')

classes = (MitsubaPreferences,)

def register():
    for cls in classes:
        register_class(cls)

    context = bpy.context
    prefs = get_addon_preferences(context)
    prefs.require_restart = False

    try_register_mitsuba(context)

def unregister():
    for cls in classes:
        unregister_class(cls)
    try_unregister_mitsuba()
