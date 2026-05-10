import bpy
import tempfile
import os
import numpy as np
from ..io.exporter import SceneConverter

class MitsubaRenderEngine(bpy.types.RenderEngine):

    bl_idname = "MITSUBA"
    bl_label = "Mitsuba"
    bl_use_preview = False

    # Init is called whenever a new render engine instance is created. Multiple
    # instances may exist at the same time, for example for a viewport and final
    # render.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.scene_data = None
        self.draw_data = None
        self.converter = SceneConverter(render=True)

    # When the render engine instance is destroy, this is called. Clean up any
    # render engine data here, for example stopping running render threads.
    def __del__(self):
        pass

    # This is the method called by Blender for both final renders (F12) and
    # small preview for materials, world and lights.
    def render(self, depsgraph):
        import mitsuba as mi
        self.converter = SceneConverter(render=True)
        b_scene = depsgraph.scene
        variant = b_scene.mitsuba.variant
        # LLVM variants crash inside Blender: drjit's LLVM JIT conflicts with
        # Blender's embedded LLVM (used by Cycles/OSL). Fall back to scalar.
        # CUDA variants are unaffected and work correctly.
        if variant.startswith('llvm_'):
            scalar_variant = 'scalar_' + variant[len('llvm_'):]
            print(f"mitsuba-blender: variant '{variant}' is incompatible with Blender's LLVM. "
                  f"Falling back to '{scalar_variant}'.")
            variant = scalar_variant
        mi.set_variant(variant)

        scale = b_scene.render.resolution_percentage / 100.0
        self.size_x = int(b_scene.render.resolution_x * scale)
        self.size_y = int(b_scene.render.resolution_y * scale)

        with tempfile.TemporaryDirectory() as dummy_dir:
            filepath = os.path.join(dummy_dir, "scene.xml")
            self.converter.set_path(filepath)
            self.converter.scene_to_dict(depsgraph)
            mi.Thread.thread().file_resolver().prepend(dummy_dir)
            mts_scene = self.converter.dict_to_scene()
            # Render inside the temp dir context so mesh files remain accessible
            mi.render(mts_scene, sensor=0)

        sensor = mts_scene.sensors()[0]
        render_results = sensor.film().bitmap().split()

        blender_result = self.begin_result(0, 0, self.size_x, self.size_y)

        for result in render_results:
            render_pixels = np.array(result[1])
            n_channels = result[1].channel_count()
            # Pad to 4 channels (RGBA) — Blender's Combined pass always expects RGBA
            if n_channels == 2:
                render_pixels = np.dstack((render_pixels, np.zeros((*render_pixels.shape[:2], 2))))
            elif n_channels == 3:
                ones = np.ones((*render_pixels.shape[:2], 1), dtype=np.float32)
                render_pixels = np.dstack((render_pixels, ones))
            buf_name = result[0].replace("<root>", "Combined")
            layer = blender_result.layers[0].passes[buf_name]
            layer.rect = np.flip(render_pixels, 0).reshape((self.size_x * self.size_y, 4)).tolist()
        self.end_result(blender_result)
