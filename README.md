# Syncro
**Project By:**  
- Rohan Joshi 
- Abhishek M Kumar


---

## 🧩 System Overview

**Syncro** is a scalable LAN-based video conferencing platform that supports:

- Multi-user video conferencing (up to 20+ concurrent users)
- Real-time audio streaming
- Screen sharing capabilities
- Group text chat
- File sharing and transfer

### Key Features

- ⚡ **Low latency:** UDP-based streaming for video/audio/screen  
- 🔒 **Reliability:** TCP-based control and chat messages  
- 📈 **Scalability:** Thread pool architecture with async I/O  
- 💻 **Cross-platform:** Works on Windows, Linux, and macOS  

---

## 🧠 System Architecture

### High-Level Architecture

*(Insert architecture diagram here)*

### Component Breakdown

#### 1. Server (`server.py`)

**Core Components**
- `SrvA` class: Main server handler  
- TCP server (port 9000): Control messages and chat  
- UDP listener (port 9001): Real-time media streams  
- File server (port 9002): File upload/download  

**Key Features**
- Asynchronous connection handling with `asyncio`  
- Thread pool for parallel processing (20 workers)  
- Client state management with connection tracking  
- Automatic cleanup of inactive clients (5-minute timeout)

---

#### 2. Client Core (`client_core.py`)

**Core Components**
- `ScalableCommClient` class: Network communication handler  
- Video capture thread (OpenCV)  
- Audio capture thread (PyAudio)  
- Screen capture thread (MSS)  
- UDP receiver thread  
- Async TCP receiver  

**Architecture Pattern**  
*(Diagram/flow can be added)*

---

#### 3. Client GUI (`client.py`)

**Components**
- `MainWindow`: Primary application window  
- `VideoWidget`: Custom video display widgets  
- `ChatWidget`: Chat interface  
- `UploadDialog`: File upload interface  
- `DownloadDialog`: File download manager  

**Threading Model**
- Main GUI thread: PyQt6 event loop  
- Client thread: asyncio event loop for network I/O  
- Signal-slot mechanism for thread-safe GUI updates  

---

## 🔗 Communication Protocols

### 1. TCP Protocol (Port 9000)

**Connection Flow:** *(illustration placeholder)*  
**Message Format:** *(example JSON placeholder)*  
**Message Types:** Control, Chat, Acknowledgment  

---

### 2. UDP Protocol (Port 9001)

**Packet Structure:** *(diagram placeholder)*  

#### Video Stream Specifications
- Resolution: 640x480  
- Codec: JPEG compression  
- Quality: 60%  
- Frame rate: ~30 FPS  
- Bandwidth: ~200–500 KB/s per stream  

#### Audio Stream Specifications
- Format: PCM 16-bit  
- Sample rate: 16 kHz  
- Channels: Mono  
- Buffer: 1024 frames  
- Bandwidth: ~32 KB/s  

#### Screen Share Specifications
- Resolution: 1280x720 (scaled)  
- Codec: JPEG compression  
- Quality: 50%  
- Frame rate: ~15 FPS  
- Bandwidth: ~300–800 KB/s  

---

### 3. File Transfer Protocol (Port 9002)

**Upload Flow** and **Download Flow** follow a JSON-based metadata format for file details and integrity verification.

---

## ⚙️ Installation Guide

### Prerequisites

**System Requirements:**
- Python 3.8 or higher  
- Webcam (for video conferencing)  
- Microphone (for audio)  
- Network Interface Card (LAN)

**Supported Operating Systems:**
- Linux (Ubuntu 20.04+, Debian 11+)  
- Windows 10/11  
- macOS 10.15+  

### Step 1: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 2: Linux-Specific Setup
Ensure proper permissions for video/audio devices and `v4l2loopback` if needed.

### Step 3: Test Camera
```bash
python3 test_camera.py
```

Expected Output:
```
✅ OpenCV Version: 4.x.x
📹 Found video devices: ['/dev/video0', '/dev/video2']
✅ Found 1 working camera(s): [0]
💡 Use camera index: 0
```

### Step 4: Configure Server
Edit `server.py` and set your server IP address.

---

## 🚀 User Guide

### Starting the Server
```bash
python3 server.py
```
Expected Output:
```
🚀 SCALABLE LAN COMMUNICATION SERVER
📡 TCP Port: 9000
📡 UDP Port: 9001
📂 FILE Port: 9002
✅ Server started successfully!
```

### Starting the Client
```bash
python3 client.py
```

### Connecting to a Meeting
1. Click “Connect” button.  
2. Enter the server IP (e.g., `192.168.1.100`).  
3. Enter your username.  
4. Click OK → ✅ Connected as [username].

### Using Video
- Click “Start Video” to begin.  
- Other users see your stream in real-time.  
- Troubleshooting: use `python3 test_camera.py` if issues arise.

### Using Audio
- Click “Mute” to toggle mic.  
- Supports 16-bit PCM @ 16kHz mono.  

### Screen Sharing
- Click “Share Screen” to broadcast.  
- Appears as “username (Screen)” in participants’ layout.  
- Stop sharing by clicking again.

### Text Chat
- Type a message → press Enter or click “Send”.  
- Messages appear with timestamps.

### File Sharing
**Upload:**
1. Click “Upload File” → choose file.  
2. Click “Start Upload”.  

**Download:**
1. Click “Downloads” → select a file → “Download”.  
2. Progress bar shows transfer status.

---

## ⚠️ Troubleshooting

### Camera Issues
- Ensure no other app uses the webcam.
- Check permissions or use diagnostic script.

### Connection Issues
- Verify server is running.  
- Check firewall (ports 9000–9002).

### Audio Issues
- Verify PyAudio installation and mic access.

### Screen Share Issues
- Wayland users: install `xdg-desktop-portal`.  
- macOS: enable screen recording permissions.

### Performance Issues
- Reduce frame rate or compression quality.  
- Close unused streams.  
- Prefer wired LAN for stability.

### File Transfer Issues
- Ensure server has storage space.  
- Check file port accessibility.

---

## 📊 Performance Metrics

| Metric | Typical Value |
|:--|:--|
| Video Latency | 50–100 ms |
| Audio Latency | 30–50 ms |
| Chat Latency | 10–20 ms |
| File Transfer | Depends on file size |

---

## 🔒 Security Considerations

**Designed for trusted LAN environments.**

**Current Limitations:**
- No encryption (TCP/UDP unencrypted)  
- No authentication or authorization  
- Files stored in plain text  
- No filename sanitization

**Recommended Deployment:**
1. Use on private LANs only.  
2. Firewall external access.  
3. Use VPN (WireGuard/OpenVPN) if remote.  
4. Keep dependencies updated.

### Future Enhancements
- TLS/SSL for TCP  
- DTLS for UDP  
- Token-based authentication  
- Input validation & ACLs  

---

## 🧱 Development

### Project Structure
```
syncup/
├── server.py              # Server core
├── client_core.py         # Client networking
├── client.py              # Client GUI
├── test_camera.py         # Camera diagnostic tool
├── requirements.txt       # Python dependencies
├── server_file_uploads/   # File storage
└── README.md              # Documentation
```

---

## 🖥️ Results & Features

- Modern GUI with PyQt6  
- Dynamic grid layout for participants  
- Group chat with timestamps  
- Real-time file upload/download  
- Screen sharing and dynamic role switching  

---

© 2025 SyncUp Project Team  
LAN-Based Collaboration Suite | Department of Computer Science
