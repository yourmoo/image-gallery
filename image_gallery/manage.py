"""Console entry point, installed as `image-gallery-admin`.

Replaces the conventional top-level `manage.py` so the packaged wheel carries
its own admin command without shipping a source tree.
"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "image_gallery.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
