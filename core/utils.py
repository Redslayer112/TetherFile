import hashlib
import os
from pathlib import Path
import shutil
import re
import unicodedata
from core import CONFIG

HASH_CHUNK_SIZE = CONFIG['HASH_CHUNK_SIZE']
HASH_ALGORITHM = CONFIG['HASH_ALGORITHM']


def sanitize_filename(filename):
    r"""
    Sanitize filename for cross-platform compatibility.
    Removes/replaces characters that are invalid on Windows but valid on Linux.

    Invalid Windows characters: < > : " / \ | ? *
    Also removes control characters (0-31) and leading/trailing dots and spaces.
    """
    filename = unicodedata.normalize("NFC", filename)
    if not filename:
        return "unnamed"
    
    # Replace invalid Windows characters with underscore
    # Keep the replacement readable: ? becomes _ not removed
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)
    
    # Remove control characters (ASCII 0-31)
    sanitized = re.sub(r'[\x00-\x1f]', '', sanitized)
    
    # Remove leading/trailing dots and spaces (invalid on Windows)
    sanitized = sanitized.strip('. ')
    
    # Ensure filename is not empty after sanitization
    if not sanitized:
        return "unnamed"
    
    # Prevent reserved Windows names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'
    }
    name_without_ext = os.path.splitext(sanitized)[0].upper()
    if name_without_ext in reserved_names:
        sanitized = '_' + sanitized
    
    # Limit length to 255 characters (common filesystem limit)
    if len(sanitized) > 255:
        name, ext = os.path.splitext(sanitized)
        max_name_len = 255 - len(ext)
        sanitized = name[:max_name_len] + ext
    
    return sanitized


def sanitize_path(path):
    """
    Sanitize a full path (with directories) for cross-platform compatibility.
    Sanitizes each component separately while preserving path structure.
    """
    if not path:
        return ""
    
    # Normalize path separators
    path = path.replace('\\', os.sep).replace('/', os.sep)
    
    # Split into components and sanitize each
    components = path.split(os.sep)
    sanitized_components = [sanitize_filename(comp) if comp else comp for comp in components]
    
    sanitized_path = os.sep.join(sanitized_components)

    if os.name == "nt":
        sanitized_path = os.path.normpath(sanitized_path)
        if len(sanitized_path) >= 240 and not sanitized_path.startswith("\\\\?\\"):
            sanitized_path = "\\\\?\\" + os.path.abspath(sanitized_path)

    return sanitized_path



def calculate_file_hash(filepath):
    """Calculate hash of file using algorithm set in config"""
    try:
        hash_func = hashlib.new(HASH_ALGORITHM)
    except ValueError:
        raise ValueError(f"Unsupported hash algorithm: {HASH_ALGORITHM}")

    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(HASH_CHUNK_SIZE), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()


def get_hash_digest_size(algorithm=None):
    """Return raw digest byte length for the given (or configured) hash algorithm."""
    algo = (algorithm or HASH_ALGORITHM)
    return hashlib.new(algo).digest_size


def exceeds_size_limit(size_bytes, limit_mb):
    """Return True if size_bytes exceeds the configured cap.
    A None / 0 / negative limit means unlimited.
    """
    if not limit_mb or limit_mb <= 0:
        return False
    return size_bytes > limit_mb * 1024 * 1024


def format_size(size):
    """Convert a file size in bytes to a human-readable string"""
    if size <= 0:
        return "0 B"
    
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    for unit in units:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} EB"


def collect_directory_files(dir_path):
    """Collect all files in directory with their info"""
    files_info = []
    total_size = 0
    base_path = Path(dir_path)
    
    for file_path in base_path.rglob('*'):
        if file_path.is_file():
            rel_path = file_path.relative_to(base_path)
            size = file_path.stat().st_size
            files_info.append({
                'path': str(rel_path),
                'full_path': str(file_path),
                'size': size
            })
            total_size += size

    files_info.sort(key=lambda item: item['path'])
    
    return files_info, total_size

def clean_path(path: str) -> str:
    if not path:
        return ""

    path = path.strip()

    # Handle PowerShell drag & drop that prepends "& "
    if path.startswith("& "):
        path = path[2:].lstrip()

    # Remove surrounding quotes if present
    if (path.startswith('"') and path.endswith('"')) or \
       (path.startswith("'") and path.endswith("'")):
        path = path[1:-1]

    # Normalize path format (e.g., slashes/backslashes)
    return os.path.normpath(path)


def get_disk_usage(path):
    """
    Get disk usage for a given path, with fallback handling.
    Returns (total, used, free) in bytes, or None if cannot determine.
    """
    
    # First ensure the directory exists
    try:
        ensure_directory(path)
    except Exception:
        # If we can't create the directory, try parent directories
        parent = path
        while parent and parent != os.path.dirname(parent):
            parent = os.path.dirname(parent)
            if os.path.exists(parent):
                path = parent
                break
        else:
            # Fallback to current directory
            path = '.'
    
    try:
        return shutil.disk_usage(path)
    except Exception:
        return None

def ensure_directory(path):
    """Ensure directory exists, create if it doesn't."""
    if not path:
        return
    path = os.path.normpath(path)
    os.makedirs(path, exist_ok=True)
    if not os.path.isdir(path):
        raise OSError(f"Path exists but is not a directory: {path}")