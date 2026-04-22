<div align="center">

# 🧩 TMMI
### Tuomi's Magisk Module Installer

![Vibe Coded](https://img.shields.io/badge/Vibe%20Coded-⚡-ff69b4)

A Windows desktop tool to browse, install and manage Magisk modules
on your Android device — over USB or WiFi — through a clean web UI.

![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python)
![Platform](https://img.shields.io/badge/Platform-Windows-blue?logo=windows)
![ADB](https://img.shields.io/badge/Requires-ADB-green)
![Magisk](https://img.shields.io/badge/Requires-Magisk-purple)

</div>

---

## Requirements

| Requirement | Notes |
|---|---|
| Windows 10/11 | Tested on Windows 11 |
| Python 3.8+ | [Download](https://www.python.org/downloads/) |
| ADB | [Platform Tools](https://developer.android.com/tools/releases/platform-tools) |
| Magisk | Installed on your Android device |
| USB Debugging | Enabled in Developer Options |

---

## Quick Start

### Option A — One command (recommended)
```bat
git clone https://github.com/yourusername/TMMI.git
cd TMMI
run.bat
```

### Option B — Manual
1. Download and extract this repo
2. Place `adb.exe`, `AdbWinApi.dll`, `AdbWinUsbApi.dll` in the folder  
   *(or have ADB in your system PATH)*
3. Double-click `run.bat`

---

## Features

- 🔍 Browse modules from Magisk repo
- 📦 One-click install via ADB
- 📡 USB or WiFi connection
- 🔋 Battery warning before install
- 💾 Remembers last device + settings
- 🐛 Debug mode (`run.bat debug`)

---

## Connection Modes

| Mode | How |
|---|---|
| USB → WiFi | Plug in once, goes wireless automatically |
| USB only | Stays wired |
| WiFi only | Enter device IP manually |

---

## Debug Mode

```bat
run.bat debug
```
Skips device detection — launches the UI instantly for development.

---

## Config

`tmmi.cfg` is created automatically on first run and saves:
- Last used IP
- Last connection mode  
- Port number
- Banner preference

---

## License

MIT © Tuomi
