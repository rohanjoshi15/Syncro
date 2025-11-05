"""
Client Core - Handles all networking for video, audio, screen sharing, chat, and files
FIXED: Local video preview now works correctly
## MODIFIED: Refactored to use a single, persistent asyncio event loop for all TCP comms
## MODIFIED: Added file transfer (upload/download) capabilities on a separate port
"""

import asyncio
import socket
import threading
import struct
import time
import json
import os  # ## MODIFIED: Import OS
from typing import Callable, Optional
from queue import Queue, Empty

class ScalableCommClient:
    """Main client handling all communication with server"""
    
    def __init__(self, server_ip='127.0.0.1', tcp_port=9000, udp_port=9001):
        self.server_ip = server_ip
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.file_port = udp_port + 1 # ## MODIFIED: File port is 9002
        
        # Network connections
        self.tcp_reader: Optional[asyncio.StreamReader] = None
        self.tcp_writer: Optional[asyncio.StreamWriter] = None
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4194304)
        
        # State
        self.connected = False
        self.client_id = None
        self.username = None
        
        # Callbacks for GUI updates
        self.on_video_frame: Optional[Callable] = None
        self.on_audio_chunk: Optional[Callable] = None
        self.on_screen_frame: Optional[Callable] = None
        self.on_chat_message: Optional[Callable] = None
        self.on_user_list: Optional[Callable] = None
        self.on_user_status: Optional[Callable] = None
        
        # ## MODIFIED: Add file transfer callbacks
        self.on_file_meta: Optional[Callable] = None
        self.on_file_download_progress: Optional[Callable] = None
        
        # Streaming flags
        self.video_streaming = False
        self.audio_streaming = False
        self.screen_streaming = False
        
        # Threads
        self.udp_thread = None
        
        print("🔧 Client initialized")
    
    async def connect(self, username):
        """Connect to server"""
        self.username = username
        
        try:
            # TCP connection
            print(f"📡 Connecting to {self.server_ip}:{self.tcp_port}...")
            self.tcp_reader, self.tcp_writer = await asyncio.wait_for(
                asyncio.open_connection(self.server_ip, self.tcp_port),
                timeout=10.0
            )
            
            # Send username (handshake)
            self.tcp_writer.write(username.encode())
            await self.tcp_writer.drain()
            
            # Receive response
            length_data = await asyncio.wait_for(self.tcp_reader.readexactly(4), timeout=5.0)
            msg_length = struct.unpack('I', length_data)[0]
            data = await asyncio.wait_for(self.tcp_reader.readexactly(msg_length), timeout=5.0)
            
            response = data.decode()
            
            if response.startswith("CONNECTED:"):
                parts = response.split(":")
                self.client_id = parts[1]
                self.connected = True
                
                print(f"✅ Connected as {username} (ID: {self.client_id})")
                
                self.udp_thread = threading.Thread(target=self.receive_udp_loop, daemon=True)
                self.udp_thread.start()
                
                return True
            else:
                print("❌ Connection failed: Invalid response")
                return False
        
        except asyncio.TimeoutError:
            print("❌ Connection timeout")
            return False
        except Exception as e:
            print(f"❌ Connection error: {e}")
            return False
    
    def start_video(self, camera_index=0):
        """Start video streaming"""
        if not self.connected:
            print("❌ Not connected to server")
            return False
        
        if self.video_streaming:
            print("⚠️ Video already streaming")
            return False
        
        self.video_streaming = True
        threading.Thread(target=self._video_stream_loop, args=(camera_index,), daemon=True).start()
        print("📹 Video streaming started")
        return True
    
    def stop_video(self):
        """Stop video streaming"""
        self.video_streaming = False
        print("📹 Video streaming stopped")
    
    def start_audio(self):
        """Start audio streaming"""
        if not self.connected:
            print("❌ Not connected to server")
            return False
        
        if self.audio_streaming:
            print("⚠️ Audio already streaming")
            return False
        
        self.audio_streaming = True
        threading.Thread(target=self._audio_stream_loop, daemon=True).start()
        print("🎤 Audio streaming started")
        return True
    
    def stop_audio(self):
        """Stop audio streaming"""
        self.audio_streaming = False
        print("🎤 Audio streaming stopped")
    
    def start_screen_share(self):
        """Start screen sharing"""
        if not self.connected:
            print("❌ Not connected to server")
            return False
        
        if self.screen_streaming:
            print("⚠️ Screen already sharing")
            return False

        # verify that mss (or another capture backend) is available before starting
        try:
            from mss import mss  # noqa: F401
        except Exception as e:
            print("❌ Screen share backend not available (mss missing):", e)
            return False
        
        self.screen_streaming = True
        threading.Thread(target=self._screen_share_loop, daemon=True).start()
        print("🖥️ Screen sharing started")
        return True
    
    def stop_screen_share(self):
        """Stop screen sharing"""
        self.screen_streaming = False
        print("🖥️ Screen sharing stopped")
    
    def _video_stream_loop(self, camera_index):
        """Video capture and streaming loop - FIXED VERSION"""
        cap = None
        try:
            import cv2
            
            time.sleep(0.5)
            
            if not self.on_video_frame:
                print("⚠️ Warning: on_video_frame callback not set!")
            
            working_camera = None
            for idx in range(5):  # Try cameras 0-4
                test_cap = cv2.VideoCapture(idx)
                if test_cap.isOpened():
                    ret, _ = test_cap.read()
                    if ret:
                        working_camera = idx
                        test_cap.release()
                        print(f"✅ Found working camera at index {idx}")
                        break
                test_cap.release()
            
            if working_camera is None:
                print("❌ No working camera found!")
                self.video_streaming = False
                return
            
            cap = cv2.VideoCapture(working_camera)
            
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            cap.set(cv2.CAP_PROP_FPS, 30)
            
            if not cap.isOpened():
                print("❌ Failed to open camera")
                self.video_streaming = False
                return
            
            print(f"📹 Video capture started (Camera {working_camera})")
            print(f"📹 Username for preview: {self.username}")
            
            frame_count = 0
            preview_errors = 0
            
            while self.video_streaming and self.connected:
                ret, frame = cap.read()
                if not ret:
                    print("⚠️ Failed to read frame")
                    time.sleep(0.1)
                    continue
                
                frame_count += 1
                
                preview_frame = cv2.flip(frame, 1)
                
                if self.on_video_frame and self.username:
                    try:
                        self.on_video_frame(self.username, preview_frame.copy())
                        
                        if frame_count == 1:
                            print(f"✅ Sent first preview frame for user: {self.username}")
                    
                    except Exception as e:
                        preview_errors += 1
                        if preview_errors <= 3:
                            print(f"⚠️ Preview error #{preview_errors}: {e}")
                
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 60]
                success, encoded = cv2.imencode('.jpg', frame, encode_param)
                
                if success:
                    packet = self.create_udp_packet(1, encoded.tobytes())
                    if packet:
                        try:
                            self.udp_socket.sendto(packet, (self.server_ip, self.udp_port))
                        except Exception as e:
                            if frame_count % 100 == 0:
                                print(f"⚠️ UDP send error: {e}")
                
                time.sleep(0.033)
            
            print(f"📹 Video capture stopped (sent {frame_count} frames, {preview_errors} preview errors)")
        
        except Exception as e:
            print(f"❌ Video error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.video_streaming = False
            if cap:
                cap.release()
    
    def _audio_stream_loop(self):
        """Audio capture and streaming loop"""
        try:
            import pyaudio
            
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=1024
            )
            
            print("🎤 Audio capture started")
            
            while self.audio_streaming and self.connected:
                audio_data = stream.read(1024, exception_on_overflow=False)
                
                packet = self.create_udp_packet(2, audio_data)
                try:
                    self.udp_socket.sendto(packet, (self.server_ip, self.udp_port))
                except:
                    pass
            
            stream.stop_stream()
            stream.close()
            p.terminate()
            print("🎤 Audio capture stopped")
        
        except Exception as e:
            print(f"❌ Audio error: {e}")
            self.audio_streaming = False
    
    def _screen_share_loop(self):
        """Screen capture and sharing loop"""
        try:
            import cv2
            import numpy as np
            from mss import mss
            
            sct = mss()
            monitor = sct.monitors[1]
            
            print("🖥️ Screen capture started")
            
            while self.screen_streaming and self.connected:
                screenshot = sct.grab(monitor)
                frame = np.array(screenshot)
                
                frame = cv2.resize(frame, (1280, 720))
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 50]
                success, encoded = cv2.imencode('.jpg', frame, encode_param)
                
                if success:
                    packet = self.create_udp_packet(3, encoded.tobytes())
                    try:
                        self.udp_socket.sendto(packet, (self.server_ip, self.udp_port))
                    except:
                        pass
                
                time.sleep(0.066)
            
            print("🖥️ Screen capture stopped")
        
        except Exception as e:
            print(f"❌ Screen share error: {e}")
            self.screen_streaming = False
    
    async def send_chat_message(self, message):
        """Send chat message via TCP (Async version)"""
        if not self.connected:
            return False
        
        try:
            msg = f"CHAT:{message}"
            await self._send_tcp_message(msg)
            return True
        except Exception as e:
            print(f"❌ Chat send error: {e}")
            return False
    
    async def send_control(self, control):
        """Send control message (Async version)"""
        if not self.connected:
            return
        
        try:
            msg = f"CONTROL:{control}"
            await self._send_tcp_message(msg)
        except Exception as e:
            print(f"❌ Control send error: {e}")
    
    ## MODIFIED: Renamed from _send_tcp_data to _send_tcp_message
    async def _send_tcp_message(self, message):
        """Send TCP message with length prefix"""
        try:
            data = message.encode('utf-8')
            length = struct.pack('I', len(data))
            self.tcp_writer.write(length + data)
            await self.tcp_writer.drain()
        except Exception as e:
            print(f"❌ TCP send error: {e}")
            self.connected = False # Connection is likely broken

    ## MODIFIED: New function to upload file
    async def upload_file(self, file_path):
        """Uploads a file to the server's file port"""
        if not self.connected:
            return
        
        try:
            filename = os.path.basename(file_path)
            file_size = os.path.getsize(file_path)
            
            # 1. Connect to file port
            reader, writer = await asyncio.open_connection(
                self.server_ip, self.file_port
            )
            
            # 2. Send command (1=Upload)
            writer.write(struct.pack('B', 1))
            
            # 3. Send client ID
            id_bytes = self.client_id.encode()
            writer.write(struct.pack('H', len(id_bytes)))
            writer.write(id_bytes)
            
            # 4. Send filename
            name_bytes = filename.encode()
            writer.write(struct.pack('I', len(name_bytes)))
            writer.write(name_bytes)
            
            # 5. Send file size
            writer.write(struct.pack('Q', file_size))
            
            # 6. Send file data
            with open(file_path, 'rb') as f:
                while chunk := f.read(65536):
                    writer.write(chunk)
            
            await writer.drain()
            print(f"📁 File '{filename}' uploaded")
            
            # 7. Close file connection
            writer.close()
            await writer.wait_closed()
            
            # 8. Send metadata on MAIN chat port
            meta = json.dumps({'filename': filename, 'size': file_size})
            await self._send_tcp_message(f"FILE_META:{meta}")

        except Exception as e:
            print(f"❌ File upload error: {e}")

    ## MODIFIED: New function to download file
    async def download_file(self, filename, save_path):
        """Downloads a file from the server's file port"""
        if not self.connected:
            return
            
        try:
            # 1. Connect to file port
            reader, writer = await asyncio.open_connection(
                self.server_ip, self.file_port
            )
            
            # 2. Send command (2=Download)
            writer.write(struct.pack('B', 2))
            
            # 3. Send client ID
            id_bytes = self.client_id.encode()
            writer.write(struct.pack('H', len(id_bytes)))
            writer.write(id_bytes)
            
            # 4. Send filename
            name_bytes = filename.encode()
            writer.write(struct.pack('I', len(name_bytes)))
            writer.write(name_bytes)
            
            await writer.drain()
            # We are done writing, but the server will now write back
            
            # 5. Read file size from server
            size_data = await reader.readexactly(8)
            file_size = struct.unpack('Q', size_data)[0]
            
            if file_size == 0:
                print(f"❌ File not found on server: {filename}")
                if self.on_file_download_progress:
                    self.on_file_download_progress(filename, 0, -1) # Signal error
                return
            
            # 6. Read file data and save
            bytes_received = 0
            with open(save_path, 'wb') as f:
                while bytes_received < file_size:
                    chunk_size = min(65536, file_size - bytes_received)
                    chunk = await reader.readexactly(chunk_size)
                    f.write(chunk)
                    bytes_received += len(chunk)
                    
                    if self.on_file_download_progress:
                        self.on_file_download_progress(filename, bytes_received, file_size)
            
            print(f"📁 File '{filename}' downloaded to {save_path}")
            
        except Exception as e:
            print(f"❌ File download error: {e}")
            if self.on_file_download_progress:
                self.on_file_download_progress(filename, 0, -1) # Signal error
        finally:
            writer.close()
            await writer.wait_closed()


    async def receive_tcp_loop_async(self):
        """Receive TCP messages (Async version)"""
        print("📥 Async TCP receiver started")
        
        while self.connected:
            try:
                length_data = await asyncio.wait_for(self.tcp_reader.readexactly(4), timeout=310.0)
                msg_length = struct.unpack('I', length_data)[0]
                
                data = await asyncio.wait_for(self.tcp_reader.readexactly(msg_length), timeout=30.0)
                
                message = data.decode('utf-8')
                
                self._process_tcp_message_sync(message)
            
            except asyncio.TimeoutError:
                print("⏰ TCP connection timed out")
                self.connected = False
            except (asyncio.IncompleteReadError, ConnectionResetError):
                print("🔌 Server disconnected")
                self.connected = False
            except Exception as e:
                if self.connected:
                    print(f"❌ Async TCP receive error: {e}")
                self.connected = False
        
        print("📥 Async TCP receiver stopped")
    
    def _process_tcp_message_sync(self, message):
        """Process received TCP message (synchronous version)"""
        try:
            if message.startswith("CHAT:"):
                parts = message[5:].split(":", 1)
                if len(parts) == 2 and self.on_chat_message:
                    self.on_chat_message(parts[0], parts[1])
            
            elif message.startswith("USERS:"):
                users_json = message[6:]
                users = json.loads(users_json)
                if self.on_user_list:
                    self.on_user_list(users)
            
            elif message.startswith("STATUS:"):
                status_json = message[7:]
                status = json.loads(status_json)
                if self.on_user_status:
                    self.on_user_status(status)
            
            ## MODIFIED: Handle file meta broadcast
            elif message.startswith("FILE_META:"):
                parts = message[10:].split(":", 1)
                if len(parts) == 2 and self.on_file_meta:
                    self.on_file_meta(parts[0], parts[1])
            
            elif message == "PONG":
                pass
        
        except Exception as e:
            print(f"❌ Message processing error: {e}")
    
    def receive_udp_loop(self):
        """Receive UDP streams"""
        print("📥 UDP receiver started")
        
        while self.connected:
            try:
                data, addr = self.udp_socket.recvfrom(65536)
                
                if len(data) < 3:
                    continue
                
                packet_type = data[0]
                sender_len = struct.unpack('H', data[1:3])[0]
                
                if len(data) < 3 + sender_len:
                    continue
                
                sender = data[3:3+sender_len].decode()
                payload = data[3+sender_len:]
                
                if packet_type == 1 and self.on_video_frame:
                    import cv2
                    import numpy as np
                    
                    frame_data = np.frombuffer(payload, dtype=np.uint8)
                    frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        self.on_video_frame(sender, frame)
                
                elif packet_type == 2 and self.on_audio_chunk:
                    self.on_audio_chunk(sender, payload)
                
                elif packet_type == 3 and self.on_screen_frame:
                    import cv2
                    import numpy as np
                    
                    frame_data = np.frombuffer(payload, dtype=np.uint8)
                    frame = cv2.imdecode(frame_data, cv2.IMREAD_COLOR)
                    
                    if frame is not None:
                        # ## FIX: Add '_screen' suffix
                        self.on_screen_frame(f"{sender}_screen", frame)
            
            except Exception as e:
                if self.connected:
                    print(f"❌ UDP receive error: {e}")
        
        print("📥 UDP receiver stopped")
    
    def create_udp_packet(self, packet_type, payload):
        """Create UDP packet with header"""
        if not self.client_id:
            return None
        
        client_id_bytes = self.client_id.encode()
        client_id_len = len(client_id_bytes)
        
        packet = bytes([packet_type]) + struct.pack('H', client_id_len)
        packet += client_id_bytes + payload
        
        return packet
    
    def disconnect(self):
        """Disconnect from server"""
        if not self.connected: 
            return
            
        print("👋 Disconnecting...")
        
        self.connected = False 
        
        self.video_streaming = False
        self.audio_streaming = False
        self.screen_streaming = False
        
        try:
            if self.tcp_writer:
                self.tcp_writer.close()
        except Exception as e:
            print(f"Writer close error: {e}")
        
        try:
            self.udp_socket.settimeout(0.1)
            self.udp_socket.close()
        except Exception as e:
            print(f"UDP close error: {e}")
        
        print("✅ Disconnected")
    
    def __del__(self):
        """Cleanup on deletion"""
        self.disconnect()