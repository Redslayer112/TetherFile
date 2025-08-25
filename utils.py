"""Utility functions for file operations and formatting"""

import hashlib
import os
from pathlib import Path
from config import HASH_CHUNK_SIZE, HASH_ALGORITHM


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
    
    return files_info, total_size


def clean_path(path):
    """Clean up file path (remove quotes)"""
    if path.startswith('"') and path.endswith('"'):
        return path[1:-1]
    return path


def ensure_directory(path):
    """Ensure directory exists"""
    os.makedirs(path, exist_ok=True)
