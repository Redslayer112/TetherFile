# 🔗 LAN File Transfer

A terminal-based application for transferring files and directories between laptops on a local network. Features real-time progress tracking, file integrity verification, and cross-platform network interface detection.

![Python Version](https://img.shields.io/badge/python-3.7+-blue.svg)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)

---

## 🌟 Features

### ⚡ **Direct Network Transfer**
Transfers files directly between laptops without requiring internet connectivity. Uses TCP sockets for reliable data transmission with 32KB buffering and multi-threaded processing for optimal performance.

### 🎨 **Terminal Interface**
Built with Python's curses library, providing:
- 🌈 Color-coded status indicators (green/red/blue/yellow)
- 📊 Real-time progress bars with transfer speeds and ETA
- 🖥️ Responsive design that adapts to terminal dimensions
- ⌨️ Keyboard shortcuts and single-key navigation

### 🔐 **File Integrity Verification**
Every file transfer includes SHA-256 checksum verification to ensure data integrity. Failed verifications are reported with detailed mismatch information.

### 🌐 **Smart Network Detection**
Automatically discovers and categorizes network interfaces:
- 📶 **WiFi Networks** - Wireless adapters and connections
- 🔌 **Ethernet Networks** - Wired network adapters
- 🔌 **USB Networks** - USB-to-Ethernet adapters
- 💻 **Virtual Networks** - VMware, VirtualBox, Docker interfaces
- 📱 **Mobile Networks** - Bluetooth PAN, mobile hotspots

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

## 🛠️ Installation

### Requirements
- Python 3.7 or higher
- psutil library for network interface detection

### Setup
```bash
# Clone repository
git clone https://github.com/yourusername/lan-file-transfer.git
cd lan-file-transfer

# Install dependencies
pip install psutil

# Run application
python main.py
```

---

## 🎮 Usage

### Starting the Application
Run `python main.py` to launch the interface. The application will scan for available network interfaces and present them for selection:

```
🌐 Found 3 network interface(s):
1. 📶 WiFi Network - wlp3s0 - 192.168.1.105
2. 🔌 Ethernet Network - enp2s0 - 10.0.0.15  
3. 💻 Virtual Network - docker0 - 172.17.0.1

Select interface (1-3): 1
✅ Selected: WiFi Network - wlp3s0 (192.168.1.105)
```

### Main Menu Options
- **Send File** - Transfer a single file to target IP
- **Send Directory** - Transfer entire folder with all contents
- **Start Receiving Mode** - Listen for incoming transfers
- **Change Network Settings** - Switch to different network interface
- **Exit** - Close application

### Receiving Files
1. Select "Start Receiving Mode" from main menu
2. Note the displayed IP address and port
3. Share this information with the sender
4. Press 'Q' to stop receiving mode
5. Files are saved to `received_files/` directory

### Sending Files
1. Ensure target device is in receiving mode
2. Select "Send File" or "Send Directory"
3. Enter target IP address when prompted
4. Provide file/directory path (supports drag-and-drop)
5. Monitor transfer progress in real-time

---

## ⚙️ Configuration

The `config.py` file contains customizable settings:

```python
# Network Settings
PORT = 8888                    # Transfer port (default: 8888)
                              # Examples: 9999, 5000, 12345, 8080
BUFFER_SIZE = 32 * 1024       # Transfer buffer size (default: 32KB)
                              # Examples: 16*1024 (16KB - slower, more stable)
                              #          64*1024 (64KB - faster, needs good network) 
                              #          128*1024 (128KB - maximum speed)
                              #          256*1024 (256KB - high-performance networks)
SERVER_TIMEOUT = 1.0          # Server socket timeout (default: 1 second)
                              # Examples: 0.5 (more responsive)
                              #          2.0 (more patient with slow networks)
                              #          5.0 (very slow/unstable networks)

# File Storage
RECEIVED_DIR = "received_files"  # Download directory (default: received_files)
                                # Examples: "Downloads"
                                #          "~/Desktop/Transfers"
                                #          "/tmp/lan_transfers"
                                #          "C:\\Users\\Username\\Downloads"

# File Verification
HASH_CHUNK_SIZE = 8192          # Hash calculation chunk size (default: 8KB)
                               # Examples: 4096 (4KB - slower but thorough)
                               #          16384 (16KB - faster hashing)
                               #          32768 (32KB - balanced performance)
HASH_ALGORITHM = "sha256"       # Hash algorithm (default: sha256)
                               # Examples: "md5" (fastest, less secure)
                               #          "sha1" (fast, moderate security)
                               #          "sha256" (recommended balance)
                               #          "sha512" (slowest, maximum security)

# User Interface
PROGRESS_UPDATE_INTERVAL = 0.05  # Progress bar update frequency (default: 50ms)
                                # Examples: 0.02 (50 FPS - very smooth)
                                #          0.1 (10 FPS - gentler on CPU)
                                #          0.2 (5 FPS - minimal CPU usage)

# Transfer Protocol
TRANSFER_TYPES = {
    'FILE': 'file',              # Single file transfer identifier
    'DIRECTORY': 'directory'     # Directory transfer identifier
}
```

---

## 🌍 Platform Support

### Windows
- PowerShell integration for network interface detection
- Support for Windows Terminal, Command Prompt, and PowerShell
- Native file path handling with drag-and-drop support
- Automatic firewall permission requests

### macOS
- Terminal.app and iTerm2 compatibility
- Network Setup command integration for interface information
- Finder drag-and-drop file path support
- Native Unix socket handling

### Linux
- System network interface detection via `/sys/class/net`
- ethtool integration for detailed adapter information
- Support for all major terminal emulators
- Native performance on Unix systems

---

## 🆘 Troubleshooting

### Network Interface Issues
**"No network interfaces found"**
- Verify network connections are active (WiFi/Ethernet connected)
- Check if network adapters are enabled in system settings
- Try running with elevated permissions (sudo/administrator)
- Restart network services if necessary

### Connection Problems
**"Connection refused"**
- Verify target IP address is correct
- Ensure receiving device is in active receive mode
- Check firewall settings - allow traffic on configured port (default: 8888)
- Confirm both devices are on the same network subnet

### Transfer Issues
**"File integrity check failed"**
- Check available disk space on receiving device
- Verify network stability - consider using wired connection
- Retry the transfer - temporary network issues may cause corruption
- Check if original file is accessible and not corrupted

### Performance Issues
**Slow transfer speeds**
- Use Ethernet connection instead of WiFi when possible
- Close bandwidth-intensive applications (streaming, downloads)
- Adjust `BUFFER_SIZE` in config.py:
  - Increase to 64KB or 128KB for faster networks
  - Decrease to 16KB for unstable connections
- Check network equipment (router, switch) performance

---

## 🏗️ Architecture

### File Structure
```
├── main.py          # Application entry point and main menu system
├── ui.py            # Curses-based terminal user interface
├── network.py       # Network interface detection and validation
├── sender.py        # File and directory sending functionality
├── receiver.py      # File and directory receiving functionality
├── progress.py      # Real-time progress tracking and display
├── utils.py         # Utility functions (hashing, formatting, file operations)
└── config.py        # Configuration settings and constants
```

### Transfer Protocol
1. **Connection**: TCP socket connection established on specified port
2. **Metadata**: JSON metadata exchanged containing file information and checksums
3. **Data Transfer**: Binary data transmitted in configurable chunks with progress tracking
4. **Verification**: SHA-256 checksum validation ensures data integrity
5. **Completion**: Transfer status reported and connection closed

### Security Model
- No external network dependencies - operates entirely on local network
- File integrity verification using cryptographic checksums
- No persistent storage of connection data or file information
- Direct socket connections without intermediate servers or services

---

## 💡 Usage Tips

### Optimal Performance Configuration
For high-speed networks (Gigabit Ethernet):
```python
BUFFER_SIZE = 128 * 1024      # 128KB chunks
HASH_CHUNK_SIZE = 16384       # 16KB hash chunks
PROGRESS_UPDATE_INTERVAL = 0.1 # Less frequent updates
```

### Stable Connection Configuration
For wireless or unstable networks:
```python
BUFFER_SIZE = 16 * 1024       # 16KB chunks
SERVER_TIMEOUT = 3.0          # Longer timeout
PROGRESS_UPDATE_INTERVAL = 0.2 # Reduced CPU usage
```

### Security-Focused Configuration
For maximum file verification:
```python
HASH_ALGORITHM = "sha512"     # Stronger hash algorithm
HASH_CHUNK_SIZE = 4096        # More thorough verification
```

---

*A Python terminal application for local network file transfers*