"""
Scalable LAN Communication Server
Handles TCP and UDP connections for multi-user video, audio, screen sharing, chat, and file transfer
FIXED: Chat and File Meta broadcasting now sends to all clients, including sender, for reliable chat history sync.
## MODIFIED: Added a second TCP server on port 9002 for file transfers.
"""

import asyncio
import socket
import threading
import struct
import time
import json
import os  # ## MODIFIED: Import OS
from dataclasses import dataclass
from typing import Dict, Set
from concurrent.futures import ThreadPoolExecutor

@dataclass
class Client:
    """Client connection information"""
    client_id: str
    username: str
    tcp_writer: asyncio.StreamWriter
    tcp_reader: asyncio.StreamReader
    udp_addr: tuple
    video_active: bool = False
    audio_active: bool = False
    screen_sharing: bool = False
    last_seen: float = 0

class ScalableCommServer:
    """Main server handling all communication"""
    
    ## MODIFIED: Added file_port and file storage
    def __init__(self, host='0.0.0.0', tcp_port=9000, udp_port=9001):
        self.host = host
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self.file_port = udp_port + 1  # ## MODIFIED: File port will be 9002
        
        # Client management
        self.clients: Dict[str, Client] = {}
        self.username_to_id: Dict[str, str] = {}
        self.rooms: Dict[str, Set[str]] = {'main': set()}
        
        # ## MODIFIED: File hosting
        self.file_upload_dir = "server_file_uploads"
        os.makedirs(self.file_upload_dir, exist_ok=True)
        self.hosted_files: Dict[str, str] = {} # filename -> filepath
        
        # Thread pool for parallel processing
        self.thread_pool = ThreadPoolExecutor(max_workers=20)
        
        # UDP socket for real-time streams
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4194304)  # 4MB buffer
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4194304)  # 4MB buffer
        self.udp_socket.bind((host, udp_port))
        
        # Statistics
        self.total_messages = 0
        self.total_bytes = 0
        
        print(f"🚀 Server initialized on {host}")
        print(f"📡 TCP Port: {tcp_port}")
        print(f"📡 UDP Port: {udp_port}")
        print(f"📁 FILE Port: {self.file_port}") # ## MODIFIED: Print file port
    
    async def start(self):
        """Start both TCP and UDP servers"""
        # Start TCP server (Chat/Control)
        tcp_server = await asyncio.start_server(
            self.handle_tcp_client, 
            self.host, 
            self.tcp_port
        )
        
        # ## MODIFIED: Start File Server
        file_server = await asyncio.start_server(
            self.handle_file_client,
            self.host,
            self.file_port
        )
        
        # Start UDP handler in separate thread
        udp_thread = threading.Thread(target=self.handle_udp_streams, daemon=True)
        udp_thread.start()
        
        # Start cleanup task
        asyncio.create_task(self.cleanup_inactive_clients())
        
        print(f"✅ Server started successfully!")
        print(f"👥 Waiting for clients to connect...")
        
        ## MODIFIED: Run both servers
        async with tcp_server, file_server:
            await asyncio.gather(
                tcp_server.serve_forever(), 
                file_server.serve_forever()
            )
            
    ## MODIFIED: New handler for the file server (port 9002)
    async def handle_file_client(self, reader, writer):
        """Handles file uploads and downloads on the file port"""
        addr = writer.get_extra_info('peername')
        print(f"📁 File client connected from {addr}")
        
        try:
            # 1. Read command (1 byte: 1=Upload, 2=Download)
            command_data = await reader.readexactly(1)
            command = command_data[0]
            
            # 2. Read client ID (prefix-len)
            id_len_data = await reader.readexactly(2)
            id_len = struct.unpack('H', id_len_data)[0]
            client_id = (await reader.readexactly(id_len)).decode()
            
            # 3. Read filename (prefix-len)
            name_len_data = await reader.readexactly(4)
            name_len = struct.unpack('I', name_len_data)[0]
            filename = (await reader.readexactly(name_len)).decode()
            
            if command == 1:  # UPLOAD
                print(f"   Receiving '{filename}' from {client_id}...")
                # 4. Read file size (8 bytes)
                size_data = await reader.readexactly(8)
                file_size = struct.unpack('Q', size_data)[0]
                
                # 5. Read file data and save
                save_path = os.path.join(self.file_upload_dir, filename)
                bytes_received = 0
                
                with open(save_path, 'wb') as f:
                    while bytes_received < file_size:
                        chunk_size = min(65536, file_size - bytes_received)
                        chunk = await reader.readexactly(chunk_size)
                        f.write(chunk)
                        bytes_received += len(chunk)
                
                self.hosted_files[filename] = save_path
                print(f"   ✅ Stored '{filename}' ({file_size} bytes)")
            
            elif command == 2:  # DOWNLOAD
                print(f"   Serving '{filename}' to {client_id}...")
                
                file_path = self.hosted_files.get(filename)
                
                if file_path and os.path.exists(file_path):
                    file_size = os.path.getsize(file_path)
                    
                    # 4. Send file size (8 bytes)
                    writer.write(struct.pack('Q', file_size))
                    
                    # 5. Send file data
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(65536):
                            writer.write(chunk)
                    await writer.drain()
                    print(f"   ✅ Sent '{filename}' ({file_size} bytes)")
                else:
                    # File not found, send size 0
                    writer.write(struct.pack('Q', 0))
                    print(f"   ❌ File not found: {filename}")

        except (asyncio.IncompleteReadError, ConnectionResetError):
            print(f"📁 File client {addr} disconnected abruptly")
        except Exception as e:
            print(f"❌ File server error: {e}")
        finally:
            writer.close()
            await writer.wait_closed()
            print(f"📁 File client {addr} connection closed")

    async def handle_tcp_client(self, reader, writer):
        """Handle TCP connection for chat, file transfer, and control"""
        client_id = None
        addr = writer.get_extra_info('peername')
        
        try:
            # Receive username (handshake)
            data = await asyncio.wait_for(reader.read(1024), timeout=10.0)
            username = data.decode().strip()
            
            if not username:
                writer.close()
                await writer.wait_closed()
                return
            
            # Create unique client ID
            client_id = f"{username}_{int(time.time() * 1000)}"
            
            # Store client
            self.clients[client_id] = Client(
                client_id=client_id,
                username=username,
                tcp_writer=writer,
                tcp_reader=reader,
                udp_addr=(addr[0], self.udp_port),
                last_seen=time.time()
            )
            self.username_to_id[username] = client_id
            self.rooms['main'].add(client_id)
            
            # Send welcome message with client ID
            await self.send_tcp_message(writer, f"CONNECTED:{client_id}:{username}")
            
            print(f"✅ {username} connected from {addr[0]} (ID: {client_id})")
            
            # Notify all clients about new user
            await self.broadcast_user_list()
            
            # Handle incoming messages
            while True:
                try:
                    # Read message length prefix (4 bytes)
                    length_data = await asyncio.wait_for(reader.readexactly(4), timeout=300.0)
                    msg_length = struct.unpack('I', length_data)[0]
                    
                    # Read actual message
                    data = await asyncio.wait_for(reader.readexactly(msg_length), timeout=30.0)
                    
                    # Update last seen
                    self.clients[client_id].last_seen = time.time()
                    
                    # Process message
                    await self.process_tcp_message(client_id, data)
                    
                except asyncio.TimeoutError:
                    print(f"⏰ Client {username} timed out")
                    break
                except asyncio.IncompleteReadError:
                    print(f"🔌 Client {username} disconnected")
                    break
                except Exception as e:
                    print(f"❌ Error handling {username}: {e}")
                    break
        
        except Exception as e:
            print(f"❌ Connection error: {e}")
        
        finally:
            # Cleanup
            if client_id and client_id in self.clients:
                username = self.clients[client_id].username
                del self.clients[client_id]
                if username in self.username_to_id:
                    del self.username_to_id[username]
                self.rooms['main'].discard(client_id)
                print(f"👋 {username} disconnected")
                await self.broadcast_user_list()
            
            writer.close()
            await writer.wait_closed()
    
    def handle_udp_streams(self):
        """Handle UDP packets for video/audio/screen sharing"""
        print("📡 UDP stream handler started")
        
        while True:
            try:
                data, addr = self.udp_socket.recvfrom(65536)  # Max UDP size
                
                if len(data) < 3:
                    continue
                
                # Parse packet: [type:1][client_id_len:2][client_id:var][payload:var]
                packet_type = data[0]
                client_id_len = struct.unpack('H', data[1:3])[0]
                
                if len(data) < 3 + client_id_len:
                    continue
                
                client_id = data[3:3+client_id_len].decode()
                payload = data[3+client_id_len:]
                
                # Update client UDP address
                if client_id in self.clients:
                    self.clients[client_id].udp_addr = addr
                
                # Broadcast to other clients (UDP streams skip sender)
                self.broadcast_udp(payload, client_id, packet_type)
                
                self.total_bytes += len(data)
                
            except Exception as e:
                print(f"❌ UDP Error: {e}")
    
    def broadcast_udp(self, data, sender_id, packet_type):
        """Efficiently broadcast UDP packets to all clients except sender"""
        sender_name = self.clients[sender_id].username if sender_id in self.clients else "Unknown"
        sender_bytes = sender_name.encode()

        packet = bytes([packet_type]) + struct.pack('H', len(sender_bytes)) + sender_bytes + data

        for client_id, client in self.clients.items():
            if client_id != sender_id:
                try:
                    self.udp_socket.sendto(packet, client.udp_addr)
                except Exception:
                    continue  # skip failed sends

    async def process_tcp_message(self, client_id, data):
        """Process TCP messages (chat, file, control)"""
        try:
            message = data.decode('utf-8')
            
            if message.startswith("CHAT:"):
                # Chat message
                chat_content = message[5:]
                await self.broadcast_chat(client_id, chat_content)
                self.total_messages += 1
            
            elif message.startswith("FILE_META:"):
                # File metadata
                meta_json = message[10:]
                # ## MODIFIED: Broadcast meta AFTER upload is complete
                await self.broadcast_file_meta(client_id, meta_json)
            
            elif message.startswith("CONTROL:"):
                # Control message (mute, unmute, etc)
                control = message[8:]
                await self.handle_control(client_id, control)
            
            elif message == "PING":
                # Heartbeat
                client = self.clients.get(client_id)
                if client:
                    await self.send_tcp_message(client.tcp_writer, "PONG")
        
        except Exception as e:
            print(f"❌ Error processing message: {e}")
    
    async def broadcast_chat(self, sender_id, message):
        """Broadcast chat message to all clients - FIXED to broadcast to all clients, including sender, for reliable chat history sync."""
        sender = self.clients.get(sender_id)
        if not sender:
            return
        
        formatted_msg = f"CHAT:{sender.username}:{message}"
        
        tasks = []
        for client in self.clients.values():
            # NOTE: We include the sender to echo the message for chat synchronization
            task = self.send_tcp_message(client.tcp_writer, formatted_msg)
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def broadcast_file_meta(self, sender_id, meta_json):
        """Broadcast file metadata - FIXED to broadcast to all clients, including sender."""
        sender = self.clients.get(sender_id)
        if not sender:
            return
        
        formatted_msg = f"FILE_META:{sender.username}:{meta_json}"
        
        tasks = []
        for client in self.clients.values():
            # NOTE: We include the sender to echo the message for synchronization
            task = self.send_tcp_message(client.tcp_writer, formatted_msg)
            tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def handle_control(self, client_id, control):
        """Handle control messages"""
        client = self.clients.get(client_id)
        if not client:
            return
        
        if control == "VIDEO_ON":
            client.video_active = True
        elif control == "VIDEO_OFF":
            client.video_active = False
        elif control == "AUDIO_ON":
            client.audio_active = True
        elif control == "AUDIO_OFF":
            client.audio_active = False
        elif control == "SCREEN_ON":
            client.screen_sharing = True
        elif control == "SCREEN_OFF":
            client.screen_sharing = False
        
        # Notify all clients about status change
        await self.broadcast_user_status(client_id)
    
    async def broadcast_user_status(self, client_id):
        """Broadcast user status change"""
        client = self.clients.get(client_id)
        if not client:
            return
        
        status = {
            'username': client.username,
            'video': client.video_active,
            'audio': client.audio_active,
            'screen': client.screen_sharing
        }
        
        msg = f"STATUS:{json.dumps(status)}"
        
        tasks = []
        for cid, c in self.clients.items():
            if cid != client_id:
                task = self.send_tcp_message(c.tcp_writer, msg)
                tasks.append(task)
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def broadcast_user_list(self):
        """Send updated user list to all clients"""
        users = []
        for client in self.clients.values():
            users.append({
                'username': client.username,
                'video': client.video_active,
                'audio': client.audio_active,
                'screen': client.screen_sharing
            })
        
        message = f"USERS:{json.dumps(users)}"
        
        tasks = [self.send_tcp_message(client.tcp_writer, message) 
                 for client in self.clients.values()]
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def send_tcp_message(self, writer, message):
        """Send TCP message with length prefix"""
        try:
            msg_bytes = message.encode('utf-8')
            length = struct.pack('I', len(msg_bytes))
            writer.write(length + msg_bytes)
            await writer.drain()
        except Exception as e:
            print(f"❌ Send error: {e}")
    
    async def cleanup_inactive_clients(self):
        """Remove inactive clients periodically"""
        while True:
            await asyncio.sleep(60)  # Check every minute
            
            current_time = time.time()
            inactive = []
            
            for client_id, client in self.clients.items():
                if current_time - client.last_seen > 300:  # 5 minutes
                    inactive.append(client_id)
            
            for client_id in inactive:
                print(f"🧹 Removing inactive client: {client_id}")
                if client_id in self.clients:
                    del self.clients[client_id]
            
            if inactive:
                await self.broadcast_user_list()

# Run server
if __name__ == "__main__":
    print("=" * 60)
    print("🚀 SCALABLE LAN COMMUNICATION SERVER")
    print("=" * 60)
    
    server = ScalableCommServer()
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n👋 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")