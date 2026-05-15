"""Normalize project photos: apply EXIF orientation and cache under user_data_dir."""

import os
import uuid

from PIL import Image, ImageOps


def prepare_project_image(source_path, cache_dir):
    """
    Open image, apply EXIF rotation, save to cache_dir.
    Returns path to the normalized file.
    """
    os.makedirs(cache_dir, exist_ok=True)
    with Image.open(source_path) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        dest = os.path.join(cache_dir, f"project_{uuid.uuid4().hex}.jpg")
        img.save(dest, format="JPEG", quality=92)
    return dest
