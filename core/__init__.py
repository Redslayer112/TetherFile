import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / 'config.json'

with CONFIG_PATH.open(encoding='utf-8') as _f:
    CONFIG = json.load(_f)
