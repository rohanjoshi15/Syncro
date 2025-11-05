# Syncro — Scalable LAN Communication Suite

Syncro is a lightweight, LAN-first real-time communication app supporting multi-user video, audio, screen sharing, text chat, and file transfer. It is designed for low-latency local networks and simplicity of deployment.

This project contains both the server and the Qt desktop client (PyQt6). Recent updates focus on a unique, modern UI and robust file/screen sharing, including targeted file sends.

---

**Project By:**  
- Rohan Joshi 
- Abhishek M Kumar

---

## Features

- Multi-user video conferencing (UDP JPEG streaming)
- Multi-user audio conferencing (UDP PCM streaming)
- Screen sharing (entire screen on X11; Wayland guidance and fallbacks)
- Chat (TCP with sender echo for consistent history)
- File transfer (TCP, large files, single-user or broadcast)
- Participants list with live status indicators (📹, 🎤, 🖥️)
- Modern, distinct Syncro theme (not Zoom-like)
- Resilient client threading with a dedicated asyncio loop

---

## Architecture Overview

- Server (`server.py`)
  - TCP 9000: chat, control, and metadata (length-prefixed messages)
  - UDP 9001: media (video, audio, screen frames) with a minimal header
  - TCP 9002: file transfers (large file uploads/downloads)
  - Broadcasts user lists and status on changes (e.g., VIDEO/ AUDIO/ SCREEN on/off)
  - Routes file metadata to everyone or a single recipient (targeted sends)

- Client Core (`client_core.py`)
  - Persistent asyncio TCP client + UDP socket
  - Video/audio/screen streaming loops
  - File upload/download via port 9002
  - Emits GUI callbacks for frames, audio, chat, users, file progress

- Client UI (`client.py`)
  - PyQt6 desktop app
  - Video grid with dynamic layout for camera and screen tiles
  - Right panel: Participants and Chat
  - Chat panel includes recipient selector and “Send Files” button
  - Buttons for Mute, Start Video, Share Screen, Participants, Chat, Leave

---

## Protocols and Ports

- 9000/TCP — Chat, Control, and Metadata
  - Messages are UTF-8 strings with a 4-byte length prefix.
  - Examples: `CHAT:<text>`, `CONTROL:VIDEO_ON`, `FILE_META:{json}`
- 9001/UDP — Real-time Media
  - Packet: `[type:1][name_len:2][sender_name:var][payload:var]`
  - Types: 1 = video (JPEG), 2 = audio (raw PCM), 3 = screen (JPEG)
- 9002/TCP — Files
  - Upload: client connects, sends command=1, client_id, filename, size, then bytes.
  - Download: client connects, sends command=2, client_id, filename; server returns size+data.

---

## Setup

### Prerequisites
- Python 3.10+
- Recommended OS: Linux (tested on Ubuntu). Works on Windows/macOS with adjustments.
- Suggested packages:
  - `PyQt6`, `opencv-python`, `numpy`, `pyaudio`, `mss`

### Install dependencies
```bash
pip install pyqt6 opencv-python numpy pyaudio mss
```

On Ubuntu you may need system packages for audio/camera:
```bash
sudo apt update
sudo apt install -y portaudio19-dev python3-pyaudio v4l-utils ffmpeg
```

---

## Running

### 1) Start the server (Laptop A)
```bash
python3 server.py
```

Open firewall/ports if needed (Ubuntu ufw example):
```bash
sudo ufw allow 9000:9002/tcp
sudo ufw allow 9001:9002/udp
sudo ufw reload
```

Find your LAN IP (share this with clients):
```bash
hostname -I
# or
ip addr | grep -w inet | grep -v 127.0.0.1
```

### 2) Start the client (Laptop B)
```bash
python3 client.py
```
Click “Connect” and enter the server’s IP (e.g., `192.168.x.x`) and your username.

Connectivity checks (from client):
```bash
ping <server-ip>
nc -vz <server-ip> 9000
```

---

## Using the App

### Controls
- Mute: toggle microphone streaming
- Start Video: toggle webcam streaming
- Share Screen: toggle desktop or window/screen share depending on environment
- Participants: show/hide participants panel
- Chat: show/hide chat
- Leave: close client

### Participants
- Shows users and status icons
- Updates immediately when users toggle audio/video/screen or disconnect

### Chat
- Group chat with timestamp and sender (your own messages display as “You”)

### File Transfer
- In the chat panel:
  - Recipient dropdown: “Everyone” or select a specific user
  - “Send Files” button: pick one or more files (any type/size)
- Behavior:
  - Files are uploaded over TCP 9002.
  - A `FILE_META` message is sent over TCP 9000 with `{ filename, size, target }`.
  - Server routes metadata to everyone or a specific recipient and echoes to sender.
  - Recipients see a prompt to download; a progress dialog tracks download.

---

## Screen Sharing (X11 vs Wayland)

- X11 (Xorg): full-screen capture works via `mss`.
- Wayland: native screen capture may be restricted by the compositor.
  - Easiest fix: run client under XWayland for full-screen capture:
    ```bash
    QT_QPA_PLATFORM=xcb python3 /home/rajoshi/Documents/Rohan_Study/CN_project/client.py
    ```
  - Ensure portals are installed (depending on desktop):
    - GNOME/Ubuntu: `sudo apt install xdg-desktop-portal xdg-desktop-portal-gnome`
    - KDE: `sudo apt install xdg-desktop-portal xdg-desktop-portal-kde`
    - GTK: `sudo apt install xdg-desktop-portal xdg-desktop-portal-gtk`
  - If capture still fails, the compositor may block global grabs; use the XWayland command above.

Quick checks:
```bash
echo $XDG_SESSION_TYPE      # wayland or x11
systemctl --user status xdg-desktop-portal
```

---

## Performance Notes

- Video
  - JPEG quality ~60 for camera, ~50 for screen (adjust in client core)
  - 640×480 @ ~30 FPS camera defaults; screen scaled around 1280×720
- Audio
  - PCM 16-bit, mono, 16kHz; 1024-frame chunks
- Network
  - UDP for media minimizes latency; LAN recommended
  - Increase/decrease JPEG quality and frame sizes to tune bandwidth

---

## Security Considerations

- LAN-focused: no authentication/crypto is included by default
- Anyone on the network can connect if they know the server IP and ports
- For secure deployments:
  - Use a VPN or trusted LAN
  - Put server behind a firewall
  - Add authentication and TLS on TCP control/file channels (future work)

---

## Troubleshooting

- Camera not working
  - Run `python3 test_camera.py` to probe indices and preview
  - Ensure permissions and that no other app is using the webcam
- No audio
  - Check `pyaudio` installed and default input device
- Can’t connect from client
  - Verify IP, that server is running, and that ports 9000–9002 are open
  - `nc -vz <server-ip> 9000` should succeed
- Screen share fails (Wayland)
  - Run under XWayland: `QT_QPA_PLATFORM=xcb python3 client.py`
  - Install and restart portals, relogin if needed
- File transfer errors
  - Check that server created `server_file_uploads/` and has write permissions
  - Large files: ensure disk space and network stability

---

## Project Structure

```
/home/rajoshi/Documents/Rohan_Study/CN_project/
  ├── client.py                 # PyQt6 GUI client
  ├── client_core.py            # Networking core (TCP/UDP, file transfer)
  ├── server.py                 # Asyncio server
  ├── test_camera.py            # Camera diagnostic tool
  ├── server_file_uploads/      # Server-side uploaded files
  └── picture/                  # App images (icons, etc.)
```

---

## Recent Changes (Highlights)

- UI theme overhaul (purple/teal accent, refined components, removed Zoom branding)
- Participants and chat styling improvements
- Robust screen-share handling and improved status broadcasts
- File transfer: multi-file picker, recipient dropdown (Everyone or a single user)
- Server routes `FILE_META` to a specific user or all; clients prompt with progress
- Client core: added `send_screen_frame` to support GUI-driven capture paths

---

## Roadmap Ideas

- Optional E2E encryption for chat/control and files
- Multi-room support and basic access control
- Adaptive bitrate and resolution for video/screen
- Named file rooms or history panel for shared files
- Packaged executables for Linux/Windows/macOS

---

## Credits

- Built with Python, PyQt6, asyncio, OpenCV, NumPy, PyAudio, and MSS.
- Designed for simplicity, readability, and LAN-first performance.
