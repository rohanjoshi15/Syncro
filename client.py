"""
Main GUI Application - FIXED Local Video Preview & Chat Synchronization
Key Fixes:
1. Local chat message display now relies on the server echo for synchronization.
2. The echoed chat message from the local user is displayed as "You" for consistency.
3. ## MODIFIED: Refactored to use a persistent asyncio loop in a dedicated thread
4. ## MODIFIED: UI colors updated to Google-style palette (Blue, Red, Green, Yellow)
5. ## MODIFIED: Static 3x3 grid replaced with a dynamic grid.
6. ## MODIFIED: Local user's box (blank) is now ONLY created *after* a successful connection.
7. ## MODIFIED: Screen Sharing functionality fully activated.
8. ## MODIFIED: File Sharing (upload/download) with pop-ups and progress bars.
"""

import sys
import asyncio
import cv2
import numpy as np
import pyaudio
from PyQt6.QtWidgets import *
from PyQt6.QtCore import *
from PyQt6.QtGui import *
from client_core import ScalableCommClient
import threading
import json  # ## MODIFIED: Import json
import os    # ## MODIFIED: Import os

class VideoWidget(QLabel):
    """Custom widget for displaying video streams"""
    
    def __init__(self):
        super().__init__()
        self.username = "" 
        self.setMinimumSize(320, 240)
        self.setMaximumSize(640, 480)
        self.setStyleSheet("""
            QLabel {
                background-color: #1e1e1e;
                border: 2px solid #3a3a3a;
                border-radius: 10px;
            }
        """)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText("") 
        self.setScaledContents(False)
    
    def update_frame(self, frame):
        """Update video frame"""
        try:
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_frame.shape
            bytes_per_line = ch * w
            qt_image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
            
            pixmap = QPixmap.fromImage(qt_image)
            scaled_pixmap = pixmap.scaled(
                self.size(), 
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            self.setPixmap(scaled_pixmap)
        except Exception as e:
            print(f"Frame update error: {e}")

class ChatWidget(QWidget):
    """Modern chat interface"""
    
    def __init__(self):
        super().__init__()
        self.init_ui()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)
        
        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #2b2b2b;
                color: #ffffff;
                border: none;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                font-family: 'Segoe UI', Arial;
            }
        """)
        
        # Input area
        input_layout = QHBoxLayout()
        
        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Type a message...")
        self.message_input.setStyleSheet("""
            QLineEdit {
                background-color: #3a3a3a;
                color: #ffffff;
                border: 2px solid #4a4a4a;
                border-radius: 20px;
                padding: 10px 15px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border: 2px solid #4285F4;
            }
        """)
        
        self.send_button = QPushButton("Send")
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #4285F4;
                color: white;
                border: none;
                border-radius: 20px;
                padding: 10px 25px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #3367D6;
            }
            QPushButton:pressed {
                background-color: #2A56C6;
            }
        """)
        
        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)
        
        layout.addWidget(self.chat_display)
        layout.addLayout(input_layout)
        
        self.setLayout(layout)
    
    def add_message(self, username, message):
        """Add message to chat"""
        timestamp = QTime.currentTime().toString("HH:mm")
        self.chat_display.append(
            f"<span style='color: #888;'>[{timestamp}]</span> "
            f"<b style='color: #4285F4;'>{username}:</b> {message}"
        )
    
    def add_system_message(self, message):
        """Add system message"""
        self.chat_display.append(f"<i style='color: #888;'>📢 {message}</i>")

class MainWindow(QMainWindow):
    """Main application window - FIXED VERSION"""
    
    # Signals for thread-safe GUI updates
    video_signal = pyqtSignal(str, object)
    audio_signal = pyqtSignal(str, bytes)
    chat_signal = pyqtSignal(str, str)
    users_signal = pyqtSignal(list)
    screen_signal = pyqtSignal(str, object)
    
    ## MODIFIED: Add file signals
    file_meta_signal = pyqtSignal(str, str)
    file_progress_signal = pyqtSignal(str, int, int)
    
    def __init__(self):
        super().__init__()
        
        # Client
        self.client = None
        self.audio_player = None
        self.audio_stream = None
        
        # FIX: Add persistent event loop and thread
        self.client_loop = None
        self.client_thread = None
        
        # Video widgets mapping
        self.video_widgets_map = {}  # username -> widget
        self.screen_widgets_map = {} # username_screen -> widget
        self.my_video_widget = None  # Widget for own video
        self.my_username = None
        
        ## MODIFIED: Add dialog storage
        self.download_dialogs = {} # filename -> QProgressDialog
        
        # Connect signals
        self.video_signal.connect(self.handle_video_frame_gui)
        self.audio_signal.connect(self.handle_audio_chunk_gui)
        self.chat_signal.connect(self.handle_chat_message_gui)
        self.users_signal.connect(self.handle_user_list_gui)
        self.screen_signal.connect(self.handle_screen_frame_gui)
        
        ## MODIFIED: Connect file signals
        self.file_meta_signal.connect(self.handle_file_meta_gui)
        self.file_progress_signal.connect(self.handle_file_progress_gui)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize a Zoom-style UI: top title, center video stage, right participants/chat panel, and bottom control bar."""
        self.setWindowTitle("Zoom 2.0")
        self.setGeometry(80, 80, 1280, 820)

        # Global stylesheet with refreshed theme, gradient background and richer controls
        self.setStyleSheet("""
            QMainWindow { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #071426, stop:1 #08101a); }
            QLabel { color: #e6eef8; font-family: 'Segoe UI', Arial; }
            QPushButton { color: #ffffff; font-weight: 600; }

            /* Main container (inner panel) */
            QWidget#mainContainer { 
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(6,14,22,0.75), stop:1 rgba(10,18,28,0.6));
                border-radius: 12px;
                padding: 6px;
            }

            /* Top bar */
            QWidget#topBar {
                background: rgba(255,255,255,0.03);
                border-radius: 8px;
            }
            QLabel#meetingTitle { font-size: 18px; font-weight: 700; color: #f1f7ff; }
            QLabel#meetingSub { color: #9fb4d9; }

            /* Video stage visual */
            QWidget#videoStage { background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(8,16,24,0.7), stop:1 rgba(6,12,20,0.9)); border-radius: 8px; }

            /* Buttons */
            QPushButton#btn_connect { background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #34d3ff, stop:1 #0ea5e9); color: #071020; padding: 8px 14px; border-radius: 8px; }
            QPushButton#btn_connect:hover { filter: brightness(1.1); }

            QPushButton#btn_mute, QPushButton#btn_video_toggle, QPushButton#btn_share,
            QPushButton#btn_participants, QPushButton#btn_chat, QPushButton#btn_leave {
                background-color: rgba(255,255,255,0.02);
                color: #e6eef8;
                border: 1px solid rgba(255,255,255,0.04);
                border-radius: 10px;
                padding: 8px 12px;
            }
            QPushButton#btn_mute:hover, QPushButton#btn_video_toggle:hover, QPushButton#btn_share:hover { background-color: rgba(255,255,255,0.03); }

            QPushButton#btn_share:checked { background-color: #fb923c; color: #071020; }
            QPushButton#btn_video_toggle:checked { background-color: #10b981; color: #071020; }
            QPushButton#btn_mute:checked { background-color: #ef4444; color: #071020; }
            QPushButton#btn_leave { background-color: #dc2626; }

            /* Chat and input */
            QTextEdit#chatDisplay { background: rgba(255,255,255,0.02); color: #e6eef8; border-radius: 8px; padding: 10px; }
            QLineEdit#chatInput { background: rgba(255,255,255,0.02); color: #e6eef8; border-radius: 20px; padding: 8px 12px; }
            QPushButton#sendButton { background: #4285F4; color: white; border-radius: 16px; padding: 8px 18px; }
            QPushButton#sendButton:hover { background: #356fd6; }

            QListWidget { background: rgba(12,18,24,0.6); color: #dfe9f3; border-radius: 8px; }

            /* Video widget style */
            QLabel { background-clip: padding; }
            QLabel.videoWidget { background-color: rgba(28,28,30,0.6); border: 1px solid rgba(255,255,255,0.03); border-radius: 10px; }
        """)

        # Ensure chat widget exists (compatibility with older code paths)
        if not hasattr(self, 'chat_widget') or self.chat_widget is None:
            self.chat_widget = ChatWidget()
            # default visible state
            self.chat_panel_visible = True

        # Backwards compatibility defaults for participant/chat visibility
        if not hasattr(self, 'participants_panel_visible'):
            self.participants_panel_visible = True
        if not hasattr(self, 'chat_panel_visible'):
            self.chat_panel_visible = True

        # Backwards compatibility for old button/widget names (set later after buttons created)
        try:
            self.audio_btn = getattr(self, 'btn_mute')
            self.video_btn = getattr(self, 'btn_video_toggle')
            self.screen_btn = getattr(self, 'btn_share')
        except Exception:
            pass

        # Top bar: meeting title and info
        top_bar = QWidget()
        top_layout = QHBoxLayout()
        top_layout.setContentsMargins(12, 8, 12, 8)
        top_bar.setLayout(top_layout)
        top_bar.setFixedHeight(64)
        top_bar.setStyleSheet('background-color: rgba(10,20,30,0.6); border-radius: 6px;')

        self.meeting_title = QLabel('Meeting — Zoom 2.0')
        self.meeting_title.setStyleSheet('font-size: 18px; font-weight: 700; padding-left: 8px;')

        self.meeting_sub = QLabel('Participants: 0 — Audio: Off — Video: Off')
        self.meeting_sub.setStyleSheet('color: #9fb4d9; margin-left: 18px;')

        # Add Zoom logo (if available) to the left of the top bar
        try:
            logo_label = QLabel()
            logo_path = os.path.join(os.path.dirname(__file__), 'picture', 'zoom_logo.jpeg')
            if os.path.exists(logo_path):
                logo_pix = QPixmap(logo_path).scaled(42, 42, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                logo_label.setPixmap(logo_pix)
                logo_label.setFixedSize(46, 46)
                logo_label.setStyleSheet('margin-right: 8px;')
                top_layout.addWidget(logo_label)
        except Exception as e:
            print('Logo load error:', e)

        top_layout.addWidget(self.meeting_title)
        top_layout.addWidget(self.meeting_sub)

        # add Connect button to top bar (Zoom-style header)
        self.btn_connect = QPushButton('Connect')
        self.btn_connect.setFixedHeight(36)
        self.btn_connect.setStyleSheet('background-color: #0ea5e9; color: #071020; font-weight: 700; border-radius: 6px; padding: 6px 12px;')
        self.btn_connect.clicked.connect(self.show_connect_dialog)
        top_layout.addWidget(self.btn_connect)

        top_layout.addStretch()

        # Center area: video stage
        center_widget = QWidget()
        center_layout = QVBoxLayout()
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_widget.setLayout(center_layout)

        self.video_stage = QWidget()
        self.video_stage_layout = QGridLayout()
        self.video_stage_layout.setSpacing(10)
        self.video_stage.setLayout(self.video_stage_layout)
        self.video_stage.setStyleSheet('background-color: #07101a; border-radius: 8px; padding: 8px;')

        center_layout.addWidget(self.video_stage, 1)

        # Bottom control bar
        control_bar = QWidget()
        control_bar.setFixedHeight(90)
        control_layout = QHBoxLayout()
        control_layout.setContentsMargins(20, 8, 20, 8)
        control_layout.setSpacing(16)
        control_bar.setLayout(control_layout)

        # Mute
        self.btn_mute = QPushButton('Mute')
        self.btn_mute.setCheckable(True)
        self.btn_mute.setFixedSize(140, 56)
        self.btn_mute.clicked.connect(lambda checked: self.toggle_audio(checked))
        self.btn_mute.setStyleSheet('background-color: #1f2937; border-radius: 8px;')

        # Try to set mic-mute icon from picture folder (common extensions)
        try:
            mic_set = False
            for ext in ('png', 'jpg', 'jpeg', 'svg'):
                mic_path = os.path.join(os.path.dirname(__file__), 'picture', f'mic_mute.{ext}')
                if os.path.exists(mic_path):
                    mic_pix = QPixmap(mic_path).scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                    self.btn_mute.setIcon(QIcon(mic_pix))
                    self.btn_mute.setIconSize(QSize(20, 20))
                    mic_set = True
                    break
            if not mic_set:
                # attempt to fall back to loading from mic_mute.html (embedded external link) by parsing if present
                html_path = os.path.join(os.path.dirname(__file__), 'picture', 'mic_mute.html')
                if os.path.exists(html_path):
                    try:
                        with open(html_path, 'r', encoding='utf-8') as fh:
                            data = fh.read()
                            # naive extraction of first http(s) image URL
                            import re
                            m = re.search(r'https?://[^\"\'>]+\.(?:png|jpe?g|svg)', data)
                            if m:
                                url = m.group(0)
                                # try to load remote image into QPixmap (best-effort, may fail offline)
                                from urllib.request import urlopen
                                try:
                                    resp = urlopen(url, timeout=3)
                                    img_data = resp.read()
                                    pix = QPixmap()
                                    pix.loadFromData(img_data)
                                    pix = pix.scaled(20, 20, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                                    self.btn_mute.setIcon(QIcon(pix))
                                    self.btn_mute.setIconSize(QSize(20, 20))
                                except Exception:
                                    pass
                    except Exception:
                        pass
        except Exception as e:
            print('Mic icon load error:', e)

        # Video
        self.btn_video_toggle = QPushButton('Start Video')
        self.btn_video_toggle.setCheckable(True)
        self.btn_video_toggle.setFixedSize(140, 56)
        self.btn_video_toggle.clicked.connect(lambda checked: self.toggle_video(checked))
        self.btn_video_toggle.setStyleSheet('background-color: #1f2937; border-radius: 8px;')

        # Share screen
        self.btn_share = QPushButton('Share Screen')
        self.btn_share.setFixedSize(160, 56)
        # Make share button toggleable to match existing toggle_screen usage
        self.btn_share.setCheckable(True)
        self.btn_share.clicked.connect(lambda checked: self.toggle_screen(checked))
        self.btn_share.setStyleSheet('background-color: #2563eb; border-radius: 8px;')

        # Participants
        self.btn_participants = QPushButton('Participants')
        self.btn_participants.setFixedSize(140, 56)
        self.btn_participants.clicked.connect(self._toggle_participants)
        self.btn_participants.setStyleSheet('background-color: #1f2937; border-radius: 8px;')

        # Chat
        self.btn_chat = QPushButton('Chat')
        self.btn_chat.setFixedSize(120, 56)
        self.btn_chat.clicked.connect(self._toggle_chat)
        self.btn_chat.setStyleSheet('background-color: #1f2937; border-radius: 8px;')

        # Leave
        self.btn_leave = QPushButton('Leave')
        self.btn_leave.setFixedSize(120, 56)
        self.btn_leave.clicked.connect(self.close)
        self.btn_leave.setStyleSheet('background-color: #dc2626; border-radius: 8px;')

        control_layout.addStretch()
        control_layout.addWidget(self.btn_mute)
        control_layout.addWidget(self.btn_video_toggle)
        control_layout.addWidget(self.btn_share)
        control_layout.addWidget(self.btn_participants)
        control_layout.addWidget(self.btn_chat)
        control_layout.addWidget(self.btn_leave)
        control_layout.addStretch()

        center_layout.addWidget(control_bar, 0)

        # Right panel: participants + chat
        right_panel = QWidget()
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(8, 0, 0, 0)
        right_panel.setLayout(right_layout)
        right_panel.setFixedWidth(320)

        participants_label = QLabel('Participants')
        participants_label.setStyleSheet('font-size: 16px; font-weight: 700;')
        self.participants_list = QListWidget()
        self.participants_list.setFixedHeight(220)

        # Backwards compatibility: some code expects `user_list`
        self.user_list = self.participants_list

        chat_label = QLabel('Meeting Chat')
        chat_label.setStyleSheet('font-size: 14px; font-weight: 700; margin-top: 8px;')
        # keep a reasonable height for the chat widget
        self.chat_widget.setFixedHeight(420)

        right_layout.addWidget(participants_label)
        right_layout.addWidget(self.participants_list)
        right_layout.addWidget(chat_label)
        right_layout.addWidget(self.chat_widget)

        # Assemble main container
        container = QWidget()
        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(12, 12, 12, 12)
        container_layout.setSpacing(12)
        container.setLayout(container_layout)

        container_layout.addWidget(top_bar)

        body_layout = QHBoxLayout()
        body_layout.addWidget(center_widget, 1)
        body_layout.addWidget(right_panel, 0)

        container_layout.addLayout(body_layout)

        self.setCentralWidget(container)

        # Keep references for grid updates
        self.video_grid = self.video_stage_layout

        # after creating widgets assign object names so stylesheet selectors apply
        self.video_stage.setObjectName('videoStage')
        self.btn_mute.setObjectName('btn_mute')
        self.btn_video_toggle.setObjectName('btn_video_toggle')
        self.btn_share.setObjectName('btn_share')
        self.btn_participants.setObjectName('btn_participants')
        self.btn_chat.setObjectName('btn_chat')
        self.btn_leave.setObjectName('btn_leave')

        # Top bar object name for stylesheet
        top_bar.setObjectName('topBar')
        self.meeting_title.setObjectName('meetingTitle')
        self.meeting_sub.setObjectName('meetingSub')

        # connect button object name
        self.btn_connect.setObjectName('btn_connect')

        # after creating chat widget set object names so styles apply and wire send actions
        self.chat_widget.chat_display.setObjectName('chatDisplay')
        self.chat_widget.message_input.setObjectName('chatInput')
        self.chat_widget.send_button.setObjectName('sendButton')
        # wire send button and Enter key to send_chat
        try:
            self.chat_widget.send_button.clicked.connect(self.send_chat)
            self.chat_widget.message_input.returnPressed.connect(self.send_chat)
        except Exception:
            pass

        # Add a decorative background to the main container (subtle texture via gradient)
        container.setObjectName('mainContainer')
        container.setStyleSheet("""
            QWidget#mainContainer {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 rgba(3,7,12,0.5), stop:1 rgba(8,12,20,0.6));
                border-radius: 12px;
            }
        """)

        # Initialize audio player
        self.init_audio_player()
    
    def init_audio_player(self):
        """Initialize audio player for playback (creates pyaudio stream)."""
        try:
            self.audio_player = pyaudio.PyAudio()
            self.audio_stream = self.audio_player.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                output=True,
                frames_per_buffer=1024
            )
        except Exception as e:
            print(f"Audio player init error: {e}")
    
    def update_video_grid(self):
        """Clears and rebuilds the video grid with active widgets."""
        
        while self.video_grid.count():
            item = self.video_grid.takeAt(0)
            if item.widget():
                item.widget().setParent(None)
        
        col_count = 3
        i = 0
        
        # Add local user's video first
        if self.my_video_widget:
            row, col = divmod(i, col_count)
            self.video_grid.addWidget(self.my_video_widget, row, col)
            i += 1
            
        # Add all remote users' videos
        for username, widget in self.video_widgets_map.items():
            row, col = divmod(i, col_count)
            self.video_grid.addWidget(widget, row, col)
            i += 1
        
        # Add all screen shares
        for username, widget in self.screen_widgets_map.items():
            row, col = divmod(i, col_count)
            self.video_grid.addWidget(widget, row, col)
            i += 1
            
    def connect_to_server(self, server_ip, username):
        """Connect to server - FIXED VERSION"""
        if self.client and self.client.connected:
            self.disconnect()
            
        self.my_username = username
        self.client = ScalableCommClient(server_ip)
        
        # CRITICAL: Set up callbacks BEFORE connecting
        self.client.on_video_frame = lambda sender, frame: self.video_signal.emit(sender, frame)
        self.client.on_audio_chunk = lambda sender, chunk: self.audio_signal.emit(sender, chunk)
        self.client.on_chat_message = lambda sender, msg: self.chat_signal.emit(sender, msg)
        self.client.on_user_list = lambda users: self.users_signal.emit(users)
        self.client.on_screen_frame = lambda sender, frame: self.screen_signal.emit(sender, frame)
        
        ## MODIFIED: Set file callbacks
        self.client.on_file_meta = lambda sender, meta: self.file_meta_signal.emit(sender, meta)
        self.client.on_file_download_progress = lambda name, current, total: self.file_progress_signal.emit(name, current, total)

        
        def connect_thread_loop():
            try:
                self.client_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self.client_loop)
                
                result = self.client_loop.run_until_complete(self.client.connect(username))
                
                if result:
                    QTimer.singleShot(0, self.create_local_widget) 
                    QTimer.singleShot(0, lambda: self.statusBar().showMessage(f"✅ Connected as {username}"))
                    QTimer.singleShot(0, lambda: self.chat_widget.add_system_message(f"Connected to {server_ip}"))
                    self.client_loop.run_until_complete(self.client.receive_tcp_loop_async())
                else:
                    QTimer.singleShot(0, lambda: self.statusBar().showMessage("❌ Connection failed"))
                    QTimer.singleShot(0, lambda: QMessageBox.critical(self, "Connection Failed", "Could not connect to server"))
            
            except Exception as e:
                if self.client and self.client.connected:
                    print(f"Client thread error: {e}")
                    QTimer.singleShot(0, lambda: self.statusBar().showMessage("❌ Disconnected with error"))
            
            finally:
                if self.client_loop:
                    self.client_loop.close()
                self.client_loop = None
                print("Client event loop closed.")
        
        self.client_thread = threading.Thread(target=connect_thread_loop, daemon=True)
        self.client_thread.start()
    
    def create_local_widget(self):
        """Creates the local user's video widget and adds it to the grid."""
        if not self.my_username: 
            return
            
        self.my_video_widget = VideoWidget()
        self.my_video_widget.username = self.my_username
        self.my_video_widget.setStyleSheet(f"""
            QLabel {{
                background-color: #1e1e1e;
                border: 3px solid #4285F4;
                border-radius: 10px;
            }}
        """)
        
        self.update_video_grid()
        print(f"🎥 Created video widget for: {self.my_username}")

    def disconnect(self):
        """Disconnect from server"""
        if self.client:
            self.client.disconnect()
        
        if self.client_loop:
            try:
                self.client_loop.call_soon_threadsafe(self.client_loop.stop)
            except Exception as e:
                print(f"Error stopping loop: {e}")
        
        self.client = None
        self.statusBar().showMessage("Disconnected")
        self.chat_widget.add_system_message("Disconnected from server")
        
        if self.my_video_widget:
            self.my_video_widget.deleteLater()
            self.my_video_widget = None
        
        for widget in self.video_widgets_map.values():
            widget.deleteLater()
        self.video_widgets_map.clear()
        
        for widget in self.screen_widgets_map.values():
            widget.deleteLater()
        self.screen_widgets_map.clear()
        
        ## MODIFIED: Close any open progress dialogs
        for dialog in self.download_dialogs.values():
            dialog.cancel()
        self.download_dialogs.clear()
        
        self.update_video_grid()
        self.my_username = None
    
    def _get_button(self, logical_name):
        """Return the QPushButton instance for a logical name (video/audio/screen).
        Tries legacy and new attribute names.
        """
        mapping = {
            'video': ('video_btn', 'btn_video_toggle'),
            'audio': ('audio_btn', 'btn_mute'),
            'screen': ('screen_btn', 'btn_share')
        }
        for attr in mapping.get(logical_name, (logical_name,)):
            btn = getattr(self, attr, None)
            if btn is not None:
                return btn
        return None

    def toggle_video(self, checked):
        """Toggle video streaming - FIXED VERSION"""
        btn = self._get_button('video')
        if not self.client or not self.client.connected or not self.client_loop:
            if btn is not None:
                btn.setChecked(False)
            QMessageBox.warning(self, "Not Connected", "Please connect to server first")
            return
        
        if checked:
            if not self.my_video_widget:
                print("⚠️ my_video_widget not set, cannot start video")
                if btn is not None:
                    btn.setChecked(False)
                return
            
            if not self.client.on_video_frame:
                print("⚠️ Callback not set, setting now...")
                self.client.on_video_frame = lambda sender, frame: self.video_signal.emit(sender, frame)
            
            print(f"🎥 Starting video for: {self.my_username}")
            
            success = self.client.start_video(0)
            
            if success:
                asyncio.run_coroutine_threadsafe(self.client.send_control("VIDEO_ON"), self.client_loop)
                self.my_video_widget.setText(f"{self.my_username} (You)")
            else:
                if btn is not None:
                    btn.setChecked(False)
                QMessageBox.warning(
                    self, 
                    "Camera Error", 
                    "Failed to start camera.\n\n"
                    "Make sure:\n"
                    "• Camera is not in use by another app\n"
                    "• You have camera permissions"
                )
        else:
            self.client.stop_video()
            if self.my_video_widget:
                self.my_video_widget.clear()
                self.my_video_widget.setText("")
            asyncio.run_coroutine_threadsafe(self.client.send_control("VIDEO_OFF"), self.client_loop)

    def toggle_audio(self, checked):
        """Toggle audio streaming"""
        btn = self._get_button('audio')
        if not self.client or not self.client.connected or not self.client_loop:
            if btn is not None:
                btn.setChecked(False)
            QMessageBox.warning(self, "Not Connected", "Please connect to server first")
            return
        
        if checked:
            if self.client.start_audio():
                asyncio.run_coroutine_threadsafe(self.client.send_control("AUDIO_ON"), self.client_loop)
        else:
            self.client.stop_audio()
            asyncio.run_coroutine_threadsafe(self.client.send_control("AUDIO_OFF"), self.client_loop)
    
    def toggle_screen(self, checked):
        """Toggle screen sharing with a pre-capture test to catch XGetImage/Wayland issues early."""
        btn = self._get_button('screen')
        if not self.client or not self.client.connected or not self.client_loop:
            if btn is not None:
                btn.setChecked(False)
            QMessageBox.warning(self, "Not Connected", "Please connect to server first")
            return

        if checked:
            # Pre-check: try a quick local capture to detect XGetImage / backend errors
            try:
                import mss
                with mss.mss() as s:
                    # attempt a single grab of the primary monitor
                    _ = s.grab(s.monitors[0])
            except Exception as e:
                if btn is not None:
                    btn.setChecked(False)
                # Provide actionable guidance
                QMessageBox.critical(
                    self,
                    "Screen Capture Failed",
                    "Failed to capture the screen: {}\n\n".format(str(e)) +
                    "Common causes: running Wayland without a portal, missing permissions, or X server access denied.\n\n" +
                    "Possible fixes:\n" +
                    "• Run the application in an X11 (Xorg) session instead of Wayland.\n" +
                    "• Install/enable a screen-capture portal (e.g. xdg-desktop-portal and xdg-desktop-portal-gtk) for Wayland.\n" +
                    "• Ensure the 'mss' package is installed in this Python environment (pip install mss)."
                )
                print(f"Screen capture pre-test failed: {e}")
                return

            try:
                success = self.client.start_screen_share()
            except Exception as e:
                success = False
                print(f"Screen share start error: {e}")

            if success:
                asyncio.run_coroutine_threadsafe(self.client.send_control("SCREEN_ON"), self.client_loop)
            else:
                # Reset the toggle button and inform the user how to fix
                if btn is not None:
                    btn.setChecked(False)
                QMessageBox.warning(
                    self,
                    "Screen Share Unavailable",
                    "Screen sharing could not be started. If you saw an earlier error about XGetImage()," +
                    " it means your system's display server does not allow direct grabs. Try the suggestions in the previous dialog."
                )
        else:
            try:
                self.client.stop_screen_share()
            except Exception as e:
                print(f"Error stopping screen share: {e}")
            asyncio.run_coroutine_threadsafe(self.client.send_control("SCREEN_OFF"), self.client_loop)
    
    def send_chat(self):
        """Send chat message - FIXED to rely on server echo for synchronization"""
        if not self.client or not self.client.connected or not self.client_loop:
            QMessageBox.warning(self, "Not Connected", "Please connect to server first")
            return
        
        message = self.chat_widget.message_input.text().strip()
        if message:
            asyncio.run_coroutine_threadsafe(
                self.client.send_chat_message(message), 
                self.client_loop
            )
            self.chat_widget.message_input.clear()
    
    ## MODIFIED: Implement share_file
    def share_file(self):
        """Share file"""
        if not self.client or not self.client.connected or not self.client_loop:
            QMessageBox.warning(self, "Not Connected", "Please connect to server first")
            return
        
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File to Share")
        if file_path:
            filename = os.path.basename(file_path)
            self.chat_widget.add_system_message(f"Uploading '{filename}'...")
            # Start the upload in the client's thread
            asyncio.run_coroutine_threadsafe(
                self.client.upload_file(file_path), 
                self.client_loop
            )
    
    def handle_video_frame_gui(self, sender, frame):
        """Handle incoming video frame (GUI thread) - FIXED VERSION"""
        try:
            # Show YOUR OWN video
            if sender == self.my_username:
                if self.my_video_widget:
                    self.my_video_widget.update_frame(frame)
                return
            
            # Get or create widget for other users
            if sender not in self.video_widgets_map:
                widget = VideoWidget()
                widget.username = sender
                widget.setText(sender) 
                widget.setStyleSheet("""
                    QLabel {
                        background-color: #1e1e1e;
                        border: 2px solid #3a3a3a;
                        border-radius: 10px;
                    }
                """)
                self.video_widgets_map[sender] = widget
                print(f"✅ Created widget and adding to grid: {sender}")
                # Rebuild the grid layout
                self.update_video_grid()

            # Update frame for other users
            if sender in self.video_widgets_map:
                self.video_widgets_map[sender].update_frame(frame)
        
        except Exception as e:
            print(f"❌ Video frame handling error: {e}")
            import traceback
            traceback.print_exc()
    
    def handle_screen_frame_gui(self, sender_key, frame):
        """Handle incoming screen share frame (GUI thread)"""
        try:
            # Get or create widget for the screen share
            if sender_key not in self.screen_widgets_map:
                widget = VideoWidget()
                widget.username = sender_key
                
                original_username = sender_key.replace("_screen", "")
                widget.setText(f"{original_username} (Screen)") 
                
                widget.setStyleSheet("""
                    QLabel {
                        background-color: #1e1e1e;
                        border: 3px solid #34A853;
                        border-radius: 10px;
                    }
                """)
                self.screen_widgets_map[sender_key] = widget
                print(f"✅ Created widget for screen share: {sender_key}")
                self.update_video_grid()

            if sender_key in self.screen_widgets_map:
                self.screen_widgets_map[sender_key].update_frame(frame)
        
        except Exception as e:
            print(f"❌ Screen frame handling error: {e}")

    
    def handle_audio_chunk_gui(self, sender, chunk):
        """Handle incoming audio chunk (GUI thread)"""
        try:
            if self.audio_stream:
                self.audio_stream.write(chunk)
        except Exception as e:
            print(f"Audio playback error: {e}")
    
    def handle_chat_message_gui(self, sender, message):
        """Handle incoming chat message (GUI thread) - FIXED to display 'You' for own messages"""
        display_sender = sender
        if self.my_username and sender == self.my_username:
            display_sender = "You"
            
        self.chat_widget.add_message(display_sender, message)
    
    def handle_user_list_gui(self, users):
        """Handle user list update (GUI thread)"""
        # Participants list lives in the right panel (participants_list)
        try:
            self.participants_list.clear()
        except Exception:
            pass
        
        current_users = {user.get('username') for user in users}
        
        current_screen_sharers = {f"{user.get('username')}_screen" for user in users if user.get('screen')}
        stopped_screen_sharers = set(self.screen_widgets_map.keys()) - current_screen_sharers
        
        widget_removed = False
        
        for username_key in stopped_screen_sharers:
            if username_key in self.screen_widgets_map:
                widget = self.screen_widgets_map.pop(username_key)
                widget.deleteLater()
                widget_removed = True
                print(f"🧹 Destroyed widget for stopped screen share: {username_key}")

        disconnected_users = set(self.video_widgets_map.keys()) - current_users
        
        for username in disconnected_users:
            if username in self.video_widgets_map:
                widget = self.video_widgets_map.pop(username)
                widget.deleteLater() 
                widget_removed = True
                print(f"🧹 Destroyed video widget for disconnected user: {username}")
            
            username_key = f"{username}_screen"
            if username_key in self.screen_widgets_map:
                widget = self.screen_widgets_map.pop(username_key)
                widget.deleteLater()
                widget_removed = True
                print(f"🧹 Destroyed screen widget for disconnected user: {username}")
        
        if widget_removed:
            self.update_video_grid()

        # Re-populate user list
        for user in users:
            username = user.get('username', 'Unknown')
            status_icons = []
            if user.get('video'):
                status_icons.append('📹')
            if user.get('audio'):
                status_icons.append('🎤')
            if user.get('screen'):
                status_icons.append('🖥️')
            
            status = ' '.join(status_icons) if status_icons else '👤'
            try:
                self.participants_list.addItem(f"{username} {status}")
            except Exception:
                pass
    
    ## MODIFIED: New handler for file metadata
    def handle_file_meta_gui(self, sender, meta_json):
        """Handles incoming file share notifications"""
        try:
            meta = json.loads(meta_json)
            filename = meta['filename']
            size = meta['size']
            
            # This is the echo from our own upload
            if sender == self.my_username:
                self.chat_widget.add_system_message(f"✅ File '{filename}' uploaded and shared.")
                return

            # This is from a remote user, show pop-up
            size_mb = size / (1024 * 1024)
            reply = QMessageBox.question(
                self,
                "File Share Request",
                f"<b>{sender}</b> wants to send you the file:<br><br>"
                f"<b>{filename}</b> ({size_mb:.2f} MB)<br><br>"
                "Do you want to download it to your Downloads folder?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.start_download(filename)
                
        except Exception as e:
            print(f"❌ File meta error: {e}")
            
    ## MODIFIED: New handler for download logic
    def start_download(self, filename):
        """Initiates a file download and shows progress"""
        if filename in self.download_dialogs:
            QMessageBox.warning(self, "Download in Progress", "This file is already downloading.")
            return

        # Get user's Downloads folder
        try:
            downloads_path = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation)
            if not downloads_path:
                downloads_path = os.path.expanduser("~") # Fallback to home dir
        except Exception:
            downloads_path = os.path.expanduser("~")
            
        save_path = os.path.join(downloads_path, filename)

        # Check for overwrite
        if os.path.exists(save_path):
            reply = QMessageBox.warning(
                self,
                "File Exists",
                f"The file '{filename}' already exists in your Downloads. Overwrite it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self.chat_widget.add_system_message(f"Skipped download of '{filename}'.")
                return

        # Create progress dialog
        progress_dialog = QProgressDialog(f"Downloading {filename}...", "Cancel", 0, 100, self)
        progress_dialog.setWindowTitle("File Download")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setValue(0)
        
        # Store it so we can update it
        self.download_dialogs[filename] = progress_dialog
        
        self.chat_widget.add_system_message(f"⬇️ Starting download of '{filename}'...")

        # Tell client core to start download
        asyncio.run_coroutine_threadsafe(
            self.client.download_file(filename, save_path), 
            self.client_loop
        )

    ## MODIFIED: New handler for progress updates
    def handle_file_progress_gui(self, filename, current, total):
        """Updates the progress dialog for a file download"""
        if filename in self.download_dialogs:
            dialog = self.download_dialogs[filename]
            
            if total == -1: # Error signal
                dialog.cancel()
                del self.download_dialogs[filename]
                QMessageBox.critical(self, "Download Failed", f"Failed to download '{filename}'.")
                self.chat_widget.add_system_message(f"❌ Download failed for '{filename}'.")
                return

            if total > 0:
                percent = int((current / total) * 100)
                dialog.setValue(percent)
            
            if current == total:
                dialog.setValue(100)
                del self.download_dialogs[filename]
                self.chat_widget.add_system_message(f"✅ File '{filename}' downloaded.")
                QMessageBox.information(
                    self, 
                    "Download Complete", 
                    f"<b>{filename}</b> has been saved to your Downloads folder."
                )

    def show_about(self):
        """Show about dialog"""
        QMessageBox.about(
            self,
            "About ScaleComm",
            "<h2>ScaleComm</h2>"
            "<p>Highly Scalable LAN Communication Platform</p>"
            "<p><b>Features:</b></p>"
            "<ul>"
            "<li>Multi-user video conferencing</li>"
            "<li>Multi-user audio conferencing</li>"
            "<li>Screen sharing</li>"
            "<li>Group text chat</li>"
            "<li>File sharing</li>"
            "</ul>"
            "<p>Optimized for maximum efficiency and scalability.</p>"
        )
    
    def closeEvent(self, event):
        """Handle window close"""
        self.disconnect() 
        
        if self.audio_stream:
            self.audio_stream.stop_stream()
            self.audio_stream.close()
        
        if self.audio_player:
            self.audio_player.terminate()
        
        event.accept()

    def _toggle_participants(self):
        """Show/hide participants panel (toggle)."""
        visible = not getattr(self, 'participants_panel_visible', True)
        self.participants_panel_visible = visible
        try:
            self.participants_list.setVisible(visible)
        except Exception:
            pass

    def _toggle_chat(self):
        """Show/hide chat panel (toggle)."""
        visible = not getattr(self, 'chat_panel_visible', True)
        self.chat_panel_visible = visible
        try:
            self.chat_widget.setVisible(visible)
        except Exception:
            pass

    def show_connect_dialog(self):
        """Prompt for server IP and username and connect."""
        try:
            # Prompt server IP
            server_ip, ok1 = QInputDialog.getText(self, 'Connect', 'Server IP (host:port or IP):', QLineEdit.EchoMode.Normal, '127.0.0.1')
            if not ok1 or not server_ip:
                return

            # Prompt username
            username, ok2 = QInputDialog.getText(self, 'Connect', 'Username:', QLineEdit.EchoMode.Normal)
            if not ok2 or not username:
                return

            # If server_ip includes port, split
            host = server_ip
            # Call existing connect method
            self.connect_to_server(host, username)

            # Update UI button state
            self.btn_connect.setText('Disconnect')
        except Exception as e:
            QMessageBox.critical(self, 'Connect Error', f'Failed to start connection: {e}')

def main():
    app = QApplication(sys.argv)
    
    app.setStyle("Fusion")
    
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Base, QColor(43, 43, 43))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(58, 58, 58))
    palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Button, QColor(58, 58, 58))
    palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
    palette.setColor(QPalette.ColorRole.Link, QColor(66, 133, 244))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(66, 133, 244))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    app.setPalette(palette)
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()