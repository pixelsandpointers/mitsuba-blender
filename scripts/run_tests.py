import sys
import os

import bpy
import pytest

# Blender 4.2+ loads the addon as an extension with a namespaced module name.
IS_EXTENSION = bpy.app.version >= (4, 2, 0)
ADDON_DIR_NAME = 'mitsuba_blender' if IS_EXTENSION else 'mitsuba-blender'
MODULE_NAME = 'bl_ext.user_default.mitsuba_blender' if IS_EXTENSION else 'mitsuba-blender'


class SetupPlugin:
    def __init__(self):
        mi_addon_root_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        self.mi_addon_dir = os.path.join(mi_addon_root_dir, 'mitsuba-blender')

        if IS_EXTENSION:
            self.bl_addon_dir = bpy.utils.user_resource('EXTENSIONS', path='user_default', create=True)
        else:
            self.bl_addon_dir = bpy.utils.user_resource('SCRIPTS', path='addons', create=True)

        bpy.utils.refresh_script_paths()
        self.bl_mi_addon_dir = os.path.join(self.bl_addon_dir, ADDON_DIR_NAME)

    def pytest_configure(self, config):
        if os.path.exists(self.bl_mi_addon_dir):
            os.remove(self.bl_mi_addon_dir)

        if sys.platform == 'win32':
            import _winapi
            _winapi.CreateJunction(str(self.mi_addon_dir), str(self.bl_mi_addon_dir))
        else:
            os.symlink(self.mi_addon_dir, self.bl_mi_addon_dir, target_is_directory=True)

        bpy.utils.refresh_script_paths()

        if bpy.ops.preferences.addon_enable(module=MODULE_NAME) != {'FINISHED'}:
            raise RuntimeError(f'Cannot enable addon module: {MODULE_NAME}')

        if not bpy.context.preferences.addons[MODULE_NAME].preferences.is_mitsuba_initialized:
            raise RuntimeError('Failed to initialize Mitsuba library')

    def pytest_unconfigure(self):
        bpy.ops.preferences.addon_disable(module=MODULE_NAME)
        os.remove(self.bl_mi_addon_dir)

    def pytest_runtest_setup(self, item):
        bpy.ops.wm.read_homefile(use_empty=True)
        if MODULE_NAME not in bpy.context.preferences.addons:
            raise RuntimeError('Plugin was disabled by test reset')


if __name__ == '__main__':
    pytest_args = ['tests']

    try:
        pytest_args += sys.argv[sys.argv.index('--') + 1:]
    except ValueError:
        pass

    try:
        exit_code = pytest.main(pytest_args, plugins=[SetupPlugin()])
    except Exception as e:
        print(e)
        exit_code = 1

    sys.exit(exit_code)
