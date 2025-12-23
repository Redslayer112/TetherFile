# 🔗 TetherFile

A terminal-based application for transferring files and directories between laptops on a local network. Features real-time progress tracking, file integrity verification, and cross-platform network interface detection.

![Python Version](https://img.shields.io/badge/python-3.7+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## 🌟 Features

### ⚡ **Direct Local Transfers**
Transfer files and directories directly over a local network without requiring internet connectivity. Uses reliable, blocking TCP communication with configurable buffering and retry behavior.

### 🎨 **Terminal User Interface**
Built using Python’s curses library:
- 🌈 Color-coded status indicators
- 📊 Real-time progress bars with speed and ETA
- 🖥️ Responsive layout that adapts to terminal size
- ⌨️ Simple keyboard-driven navigation

### 🔐 **Integrity Verification**
Transfers include cryptographic hash verification to ensure data integrity. Sender and receiver hashing logic is handled independently to correctly account for platform and timing differences.

### ⚙️ **JSON-Based Configuration**

All transfer behavior is controlled by a single `config.json` file.

- **Network tuning**: port selection, buffer sizes, keepalive, timeouts, and automatic retries for unstable connections.
- **Data integrity**: SHA-256 hashing with configurable chunk sizes, plus an option to skip verification when speed matters.
- **Safety limits**: hard caps on file size and directory contents to prevent accidental abuse.
- **Transfer modes**: explicit support for both file and directory transfers.
- **Progress feedback**: frequent, lightweight progress updates suitable for CLI or UI use.

This setup keeps the binary static and the behavior flexible, making deployment, tuning, and distribution refreshingly painless.

#### 🔧 Recommended `config.json` Presets

Below are a few practical presets you can drop in depending on what you care about today: raw speed, maximum safety, or not angering your network admin.

---

### 🚀 **High-Speed Transfer (LAN / Trusted Network)**
#### Optimized for throughput. Fewer checks, faster feedback.

```json
{
    "PORT": 8888,
    "BUFFER_SIZE": 262144,
    "HASH_CHUNK_SIZE": 262144,
    "SERVER_TIMEOUT": 2.0,
    "RECEIVED_DIR": "received_files",
    "HASH_ALGORITHM": "sha256",
    "SKIP_HASH_VERIFICATION": true,
    "TRANSFER_TYPES": {
        "FILE": "file",
        "DIRECTORY": "directory"
    },
    "CONNECTION_TIMEOUT": 60,
    "KEEPALIVE_ENABLE": true,
    "RETRY_ATTEMPTS": 1,
    "RETRY_DELAY": 1,
    "MAX_FILE_SIZE_MB": 4096,
    "MAX_DIRECTORY_FILES": 2000,
    "PROGRESS_UPDATE_INTERVAL": 0.25
}
```

### 🛡️ High-Reliability Transfer (Unstable / WAN)
#### Prioritizes correctness and resilience over speed.

```json
{
    "PORT": 8888,
    "BUFFER_SIZE": 32768,
    "HASH_CHUNK_SIZE": 32768,
    "SERVER_TIMEOUT": 5.0,
    "RECEIVED_DIR": "received_files",
    "HASH_ALGORITHM": "sha256",
    "SKIP_HASH_VERIFICATION": false,
    "TRANSFER_TYPES": {
        "FILE": "file",
        "DIRECTORY": "directory"
    },
    "CONNECTION_TIMEOUT": 300,
    "KEEPALIVE_ENABLE": true,
    "RETRY_ATTEMPTS": 5,
    "RETRY_DELAY": 5,
    "MAX_FILE_SIZE_MB": 1024,
    "MAX_DIRECTORY_FILES": 800,
    "PROGRESS_UPDATE_INTERVAL": 0.1
}
```

### ⚖️ Balanced (Default / Recommended)
#### A sensible middle ground for most environments.
```json
{
    "PORT": 8888,
    "BUFFER_SIZE": 65536,
    "HASH_CHUNK_SIZE": 65536,
    "SERVER_TIMEOUT": 2.0,
    "RECEIVED_DIR": "received_files",
    "HASH_ALGORITHM": "sha256",
    "SKIP_HASH_VERIFICATION": false,
    "TRANSFER_TYPES": {
        "FILE": "file",
        "DIRECTORY": "directory"
    },
    "CONNECTION_TIMEOUT": 120,
    "KEEPALIVE_ENABLE": true,
    "RETRY_ATTEMPTS": 3,
    "RETRY_DELAY": 2,
    "MAX_FILE_SIZE_MB": 1024,
    "MAX_DIRECTORY_FILES": 800,
    "PROGRESS_UPDATE_INTERVAL": 0.1
}
```

### 🧩 **Modular Transfer Architecture**
The internal structure is organized to support multiple transfer methods:
- Each transfer method lives in its own module
- Core utilities are shared and transport-agnostic
- LAN transfer remains the reference implementation
- Designed to support future BLE, USB, or other transfer modes

---

## 📸 Interface Examples

### Receiving Files
```
🔥 Receive Mode Active
🎯 Listening on 192.168.1.105:8888
💾 Files will be saved in 'received_files' folder
🔗 Ensure sender uses this IP to connect

📥 Connection from 192.168.1.108
📁 Receiving Directory: ProjectFiles
📊 127 files, 856.3 MB

📁 Receiving ProjectFiles
[██████████████████░░░░░░░░░░░░] 67.3%
576.2 MB/856.3 MB | 32.1 MB/s | ETA: 00:08

📄 [89/127] src/components/Dashboard.jsx
```

### Sending Files  
```
📤 Sending File: presentation.pdf
📁 Size: 12.4 MB
🎯 Target: 192.168.1.105
🔗 Connecting to 192.168.1.105...
🔍 Calculating file hash...

📤 Sending presentation.pdf
[████████████████████████████████] 100.0%
12.4 MB/12.4 MB | 8.7 MB/s | ETA: Complete!

✅ File sent successfully!
```

---

---

## 🛠️ Installation

### Option 1: Precompiled Executables
- Download the latest version from GitHub Releases page
- Edit `config.json` or leave it for default settings
- Run it.

No Python installation required.

---

### Option 2: From Source

#### Requirements
- Python 3.7 or higher
- `psutil` (for network interface detection)
- 

```bash
git clone https://github.com/yourusername/tetherfile.git
cd tetherfile
pip install psutil
python main.py
```

---

## 🎮 Usage

### Launch the application

### Connection Type Selection

On startup, the application first prompts you to choose the transfer method:
```
┌────────────────────────────────────────────┐
│        SELECT CONNECTION TYPE              │
│                                            │
│  1. LAN / WiFi Connection                  │
│  2. Bluetooth Connection (Coming Soon)     │
│  3. USB Wire Connection (Coming Soon)      │
│                                            │
│  Q. Quit                                   │
└────────────────────────────────────────────┘

Select connection type:
```

#### NOTE: The current version only supports LAN/WiFi transfers. Bluetooth and USB options are placeholders for future updates.

### Network Interface Selection

After selecting LAN / WiFi, the application scans for available network interfaces and displays them for selection:
```
🌐 Found 3 network interface(s):
1. 🔌 Ethernet Network - 192.168.86.1      
2. 📶 WiFi Network - 192.168.1.14

Select interface (or ESC to cancel)
```

### Main Menu Options

Once a network interface is selected, the main menu is displayed:

* **Send File** - Transfer a single file to a target device
* **Send Directory** - Transfer an entire folder recursively
* **Start Receiving Mode** - Listen for incoming transfers
* **Change Network Interface** - Switch to a different adapter
* **Exit** - Close the application

### Receiving Files

1. Select **Start Receiving Mode** from the main menu
2. Note the displayed IP address and port
3. Share this information with the sender
4. Press 'Q' to stop receiving mode
5. Files are saved to the configured receive directory

### Sending Files

1. Ensure the target device is already in receiving mode
2. Select **Send File** or **Send Directory**
3. Enter the target IP address when prompted
4. Provide the file or directory path (drag-and-drop paths are supported in most terminals)
5. Monitor transfer progress in real time
