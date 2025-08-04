# 🛰️ TetherFile

**TetherFile** is a terminal-based, high-speed file transfer application built for **direct connectivity** — starting with **LAN/Ethernet cable**

It offers a stylish curses UI and allows **file/folder transfers between two machines** with no need for the internet or third-party services. Built in Python, optimized for terminal enthusiasts and practical geeks.

Can also trasfer over **Wifi LAN**.

> 💡 _Built for **offline**, direct, raw speed file transfers between laptops_  
> 🎯 _Designed with LAN, but future-ready for any kind of tethering or peer-to-peer protocol_

---

## 🚀 Features

- 🔌 **LAN-first**: Sends files over wired Ethernet even if Wi-Fi is active
- 📁 Transfer **folders** or **individual files** — drag & drop supported
- 🎨 **Curses UI**: Smooth terminal-based UI with color, animations & boxes
- 📦 **SHA-256 validation** ensures integrity on both ends
- 📄 Shows transfer stats: speed, ETA, size, and live progress bar
- 🧠 Auto-detects IP interfaces and supports **manual override**
- 🧾 Receives files into `received_files/` folder (auto-created)
- 🧪 Modular design: future extensions like USB-C, Bluetooth, local Wi-Fi Direct coming soon
- 💥 Cross-platform (tested on Linux & Windows)

---


## 📦 Getting Started

### 🔧 Requirements

- Python 3.7+
- [`netifaces`](https://pypi.org/project/netifaces/)
- A direct LAN cable connection between two laptops  
  _(or set static IPs manually if no DHCP)_

Install Python deps:
```bash
pip install netifaces
```
> ### Note: netifaces package requires **visual studio (purple icon) with desktop development with C++**

## ▶️ Running TetherFile
```bash
git clone https://github.com/yourusername/tetherfile.git
cd tetherfile
python3 main.py
```

## 🧭 How It Works
Connect both laptops with a LAN cable

Run main.py on both systems

On receiver, choose 📥 Start Receiving Mode

On sender, pick 📤 Send File or 📁 Send Folder, enter receiver's IP

Watch the smooth progress UI until done!

📁 All received content is stored in received_files/


## 📂 Project Structure
```bash
📁 tetherfile/
├── main.py              # Main application
├── README.md            # You're reading it
├── Updates.txt          # Features Updated in this version
└── received_files/      # Auto-created on receive
```

