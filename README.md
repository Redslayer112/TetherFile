# TetherFile

Fast, reliable peer-to-peer file and directory transfer over LAN or WAN with a modern terminal UI.

![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20Linux-lightgrey.svg)
![UI](https://img.shields.io/badge/UI-Textual-5f9ea0.svg)
![Transfer](https://img.shields.io/badge/modes-LAN%20%7C%20WAN-success.svg)

---

## Why TetherFile

TetherFile focuses on practical transfer workflows:

- Simple send/receive flow in your terminal.
- LAN and WAN transfer modes in the same interface.
- File and full-directory transfer support.
- Hash-based integrity checks by default.
- Live progress and transfer logs.

---

## Features

### UI and Workflow
- Textual terminal UI with LAN/WAN mode switching.
- Start/stop receiver directly from the TUI.
- Path paste and drag-drop handling for file/folder inputs.
- Built-in progress bar + event log view.


### 🛡️ High-Reliability Transfer (Unstable)
Prioritizes correctness and resilience over speed.

### Transfer Capabilities
- Send single file.
- Send entire directory recursively.
- Receive into configurable destination folder.
- Mismatch-safe handshake for transfer metadata and verification state.

### Networking
- LAN interface selection and local IPv4 helper display.
- WAN socket tuning options for better high-latency performance.

### Data Integrity and Safety
- SHA-256 integrity verification by default.
- Optional verification skip for trusted high-speed environments.
- Directory file-count safety limit.
- Optional file-size safety limit.

---

## Installation

### Option 1: Run from Source

Requirements:
- Python 3.9+
- Packages: textual, psutil

Install:

```bash
pip install textual psutil
```

Run:

```bash
python main.py
```

### Option 2: Prebuilt Packages

If release artifacts are available, use the packaged build for your platform.  
You can edit `config.json` beside the executable if needed (defaults work out of the box).

---

## Quick Start

### 1) Receiver Side
1. Launch TetherFile.
2. Select LAN or WAN mode.
3. Set port if needed (default: 8888).
4. Click Start Receiving.
5. Share the shown address details with sender.

### 2) Sender Side
1. Launch TetherFile.
2. Select matching mode (LAN or WAN).
3. Enter target host/IP and port.
4. Paste or select the field and drop file/folder.
5. Click Send File or Send Directory.

Received data is saved under RECEIVED_DIR (default: received_files).

---

## LAN vs WAN

### LAN Mode
- Best for same-network devices.
- Uses selected network interface.
- Target is typically local IPv4.

### WAN Mode
- For internet-routed transfers.
- Target may be IPv4, IPv6, or hostname.
- Includes WAN-specific socket tuning controls.

---

## Configuration

All behavior is controlled via config.json.

### Core Keys
- PORT: transfer port used by sender/receiver.
- WAN_BIND_IP: optional explicit bind address for WAN receiver.
- RECEIVED_DIR: destination folder for incoming transfers.
- BUFFER_SIZE: transfer chunk size.
- CONNECTION_TIMEOUT: sender connection/transfer timeout window.
- SERVER_TIMEOUT: receiver accept/poll timeout behavior.

### Verification Keys
- HASH_ALGORITHM: hashing algorithm used for verification.
- SKIP_HASH_VERIFICATION: true to prioritize speed over verification.
- HASH_CHUNK_SIZE: hashing chunk size for utility operations.

### Limits and Progress Keys
- MAX_FILE_SIZE_MB: optional hard limit (null disables size cap).
- MAX_DIRECTORY_FILES: maximum files allowed in directory transfer.
- PROGRESS_UPDATE_INTERVAL: time-based progress refresh interval.
- PROGRESS_BYTES_INTERVAL: byte-based progress refresh interval.

### WAN Tuning Keys
- WAN_SOCKET_BUFFER_BYTES: socket send/receive buffer tuning.
- WAN_USER_TIMEOUT_MS: Linux TCP user timeout tuning.
- KEEPALIVE_ENABLE: socket keepalive enable switch.

---

## Compatibility Notes

- Active transfer modes: LAN and WAN.
- Bluetooth is not active in the current production flow.
- If sender and receiver hash settings do not match and verification is enabled, the transfer is rejected.

---

## Troubleshooting

### Cannot connect
- Confirm receiver is running first.
- Verify both sides use the same port.
- Check firewall and router/network rules.
- In WAN mode, verify target host/IP is reachable.

### Slow transfers
- Increase BUFFER_SIZE for high-bandwidth links.
- Tune WAN_SOCKET_BUFFER_BYTES for WAN paths.
- Reduce progress update frequency if terminal rendering is heavy.

### Transfer rejected
- Ensure HASH_ALGORITHM matches on both devices.
- Keep SKIP_HASH_VERIFICATION false for correctness.
- Use true only when speed is preferred over end-to-end integrity checks.