"""Image retrieval and storage helpers.
"""

import os
import secrets
from typing import IO
from urllib.parse import urlparse

import pillow_heif
import requests
from PIL import Image, ImageOps
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

# Register HEIF plugin with Pillow globally at module load time
pillow_heif.register_heif_opener()


def optimize_and_save_image_stream(stream: IO[bytes],
                                   filename_base: str,
                                   target_folder: str,
                                   prefix: str = "manual",
                                   max_width: int = 1200,
                                   quality: int =75):
    """Optimize a file image for local storage.
    
    Takes an in-memory file/bytes stream, auto-rotates, 
    converts HEIC/PNG/JPG to RGB, downscales to 1200px, 
    and exports a lightweight WebP.
    """
    random_hex = secrets.token_hex(4)
    clean_base = secure_filename(filename_base).rsplit('.', 1)[0]
    clean_base = clean_base.replace(' ', '_').replace('-', '_').lower()
    
    # Force a unique, clean, standard .webp file name target layout
    target_filename = f"{prefix}_{clean_base}_{random_hex}.webp"
    full_dest_path = os.path.join(target_folder, target_filename)

    try:
        # Pillow handles HEIC natively using registered wrapper above
        with Image.open(stream) as img:
            # Correct camera skews/rotation using EXIF parameters
            img = ImageOps.exif_transpose(img)
            
            # Unify palette configurations to clean RGB channel space
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            else:
                img = img.convert('RGB')

            # Downscale dimensions proportionally to prevent canvas bloat
            original_width, original_height = img.size
            if original_width > max_width:
                ratio = max_width / float(original_width)
                target_height = int(float(original_height) * float(ratio))
                img = img.resize((max_width, target_height),
                                 Image.Resampling.LANCZOS)

            # Save with WebP compression and drop redundant metadata
            img.save(full_dest_path, 'WEBP', quality=quality, optimize=True)
            return target_filename
            
    except Exception as exc:
        print(f"Image optimization pipeline crashed: {exc}")
        return None


def handle_image_upload(file_storage: FileStorage,
                        target_folder: str,
                        prefix="manual"):
    """Process a direct user form upload."""
    if not file_storage or file_storage.filename == '':
        return None
    
    # Simply pass the file stream into our centralized optimization core
    return optimize_and_save_image_stream(
        stream=file_storage.stream, 
        filename_base=file_storage.filename, 
        target_folder=target_folder,
        prefix=prefix,
    )


def download_and_cache_image(external_img_url: str,
                             target_folder: str,
                             title: str = ""):
    """Download an external image link and store locally.
    
    Routes it directly through memory optimization and discards raw file 
    footprint chunks.
    """
    if not external_img_url or not target_folder:
        return None
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'
        }
        # Use stream=True to verify status codes without dumping massive 
        # buffers immediately
        response = requests.get(external_img_url, 
                                headers=headers, 
                                timeout=10, 
                                stream=True)
        response.raise_for_status()
        
        # Pull the filename core base out of the active URL string parameters
        parsed_url = urlparse(external_img_url)
        url_filename = os.path.basename(parsed_url.path) or "scraped_image"
        
        base_title = title if title else url_filename

        # Convert the incoming network response stream directly into a 
        # Pillow-readable memory file
        from io import BytesIO
        image_memory_stream = BytesIO(response.content)

        return optimize_and_save_image_stream(
            stream=image_memory_stream,
            filename_base=base_title,
            target_folder=target_folder,
            prefix="scraped",
        )
    except Exception as e:
        print(f"Failed to locally optimize and cache external link asset: {e}")
        return None
