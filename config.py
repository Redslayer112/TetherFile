PORT = 8888
BUFFER_SIZE = 32 * 1024
SERVER_TIMEOUT = 1.0

RECEIVED_DIR = "received_files"
HASH_CHUNK_SIZE = 8192
HASH_ALGORITHM = "sha256"  # Can be 'sha256', 'md5', 'sha1', 'sha512', etc.

PROGRESS_UPDATE_INTERVAL = 0.05

TRANSFER_TYPES = {
    'FILE': 'file',
    'DIRECTORY': 'directory'
}