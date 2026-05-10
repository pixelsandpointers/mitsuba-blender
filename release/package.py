"""
Build a platform-specific Mitsuba-Blender extension zip.

Usage:
    python release/package.py --platform <platform>

Platforms: linux-x86_64, macos-arm64, windows-x86_64

The script downloads the mitsuba wheel for the target platform, injects
the wheels list into blender_manifest.toml, and produces a zip file
structured as Blender's extension system expects (files at the root).
"""

import argparse
import os
import subprocess
from zipfile import ZipFile

MITSUBA_VERSION = '3.8.0'
# Blender 5.0 ships Python 3.13.
PYTHON_VERSIONS = ['313', '312']

# pip platform tags to try, in order, for each target platform
PLATFORM_PIP_TAGS = {
    'linux-x86_64':   ['manylinux_2_28_x86_64', 'manylinux2014_x86_64'],
    'macos-arm64':    ['macosx_11_0_arm64', 'macosx_14_0_arm64'],
    'windows-x86_64': ['win_amd64'],
}


def download_wheel(platform, wheels_dir):
    os.makedirs(wheels_dir, exist_ok=True)
    for pyver in PYTHON_VERSIONS:
        for tag in PLATFORM_PIP_TAGS[platform]:
            result = subprocess.run(
                [
                    'pip3', 'download',
                    f'mitsuba=={MITSUBA_VERSION}',
                    '--dest', wheels_dir,
                    '--python-version', pyver,
                    '--platform', tag,
                    '--only-binary=:all:',
                    '--no-deps',
                ],
                capture_output=True,
            )
            if result.returncode == 0:
                wheels = [
                    f for f in os.listdir(wheels_dir)
                    if f.startswith('mitsuba') and f.endswith('.whl') and tag in f
                ]
                if wheels:
                    print(f'Downloaded: {wheels}')
                    return [os.path.join(wheels_dir, w) for w in wheels]
    raise RuntimeError(
        f'Could not download mitsuba=={MITSUBA_VERSION} wheel for {platform}. '
        f'Tried Python versions {PYTHON_VERSIONS} and pip tags: {PLATFORM_PIP_TAGS[platform]}'
    )


def build_manifest(base_manifest_path, wheel_files):
    with open(base_manifest_path, 'r') as f:
        content = f.read()
    entries = '\n'.join(
        f'    "./wheels/{os.path.basename(w)}",' for w in wheel_files
    )
    content += f'\nwheels = [\n{entries}\n]\n'
    return content


def main(args):
    base_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
    addon_dir = os.path.join(base_dir, 'mitsuba-blender')
    wheels_dir = os.path.join(addon_dir, 'wheels')
    manifest_path = os.path.join(addon_dir, 'blender_manifest.toml')

    platforms = list(PLATFORM_PIP_TAGS.keys()) if args.platform == 'all' else [args.platform]
    wheel_files = []
    for platform in platforms:
        wheel_files += download_wheel(platform, wheels_dir)

    manifest_content = build_manifest(manifest_path, wheel_files)

    output_name = 'mitsuba-blender.zip' if args.platform == 'all' else f'mitsuba-blender-{args.platform}.zip'

    with ZipFile(output_name, 'w') as archive:
        # Manifest with injected wheels section (at zip root)
        archive.writestr('blender_manifest.toml', manifest_content)

        # Miscellaneous top-level files
        for filename in ['README.md', 'LICENSE']:
            filepath = os.path.join(base_dir, filename)
            if os.path.exists(filepath):
                archive.write(filepath, filename)

        # Addon Python source files (preserve subdirectory structure, strip addon_dir prefix)
        for folder, subdirs, filenames in os.walk(addon_dir):
            # Skip cache and wheels directories
            subdirs[:] = [d for d in subdirs if d not in ('__pycache__', 'wheels')]
            for filename in filenames:
                if filename.endswith(('.py', '.json', '.toml')):
                    if filename == 'blender_manifest.toml':
                        continue  # already written above with wheels injected
                    filepath = os.path.join(folder, filename)
                    archive.write(filepath, os.path.relpath(filepath, addon_dir))

        # Wheels
        for wheel_path in wheel_files:
            archive.write(wheel_path, f'wheels/{os.path.basename(wheel_path)}')

    print(f'Created {output_name}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--platform',
        choices=list(PLATFORM_PIP_TAGS.keys()) + ['all'],
        default='all',
        help='Target platform (default: all — bundles every platform wheel into one zip)',
    )
    main(parser.parse_args())
