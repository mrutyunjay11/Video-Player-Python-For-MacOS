import sys
import os
import platform
import subprocess
import json
import vlc
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QSlider, QFileDialog, QLabel,
    QWidget, QHBoxLayout, QVBoxLayout, QGridLayout, QTabWidget, QCheckBox, 
    QComboBox, QSizePolicy, QStyle, QListWidget, QListWidgetItem, QMessageBox,
    QAction, QMenu, QInputDialog, QStatusBar, QShortcut, QLineEdit, QScrollArea, QGroupBox, QFormLayout  # Add QGroupBox, QFormLayout
)
from PyQt5.QtCore import Qt, QTimer, QUrl, QMimeData, QStandardPaths
from PyQt5.QtGui import QIcon, QKeySequence, QDragEnterEvent, QDropEvent
from PyQt5.QtWebEngineWidgets import QWebEngineView  # Add QWebEngineView
from urllib.parse import urlparse
import re
import pafy  # For YouTube support
import yt_dlp  # For other streaming sites

class SleepPreventer:
    def __init__(self):
        self.caffeinate_proc = None
        self.inhibit_proc = None
        self.current_os = platform.system()
        self.enabled = True

    def prevent_sleep(self):
        if not self.enabled:
            return

        try:
            if self.current_os == "Windows":
                self._prevent_windows_sleep()
            elif self.current_os == "Darwin":
                self._prevent_macos_sleep()
            elif self.current_os == "Linux":
                self._prevent_linux_sleep()
        except Exception as e:
            print(f"Sleep prevention error: {str(e)}")
            self.enabled = False

    def allow_sleep(self):
        try:
            if self.current_os == "Windows":
                self._allow_windows_sleep()
            elif self.current_os == "Darwin":
                self._allow_macos_sleep()
            elif self.current_os == "Linux":
                self._allow_linux_sleep()
        except Exception as e:
            print(f"Sleep allowance error: {str(e)}")

    def _prevent_windows_sleep(self):
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ES_SYSTEM_REQUIRED = 0x00000001
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)

    def _allow_windows_sleep(self):
        import ctypes
        ES_CONTINUOUS = 0x80000000
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    def _prevent_macos_sleep(self):
        if self.caffeinate_proc is None:
            self.caffeinate_proc = subprocess.Popen(['caffeinate'])

    def _allow_macos_sleep(self):
        if self.caffeinate_proc:
            self.caffeinate_proc.terminate()
            self.caffeinate_proc = None

    def _prevent_linux_sleep(self):
        if self.inhibit_proc is None:
            self.inhibit_proc = subprocess.Popen([
                'systemd-inhibit',
                '--why=Media playback',
                '--what=handle-lid-switch',
                '--mode=block',
                'sleep',
                'infinity'
            ])

    def _allow_linux_sleep(self):
        if self.inhibit_proc:
            self.inhibit_proc.terminate()
            self.inhibit_proc = None

class MediaPlayer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Advanced Media Player")
        self.setGeometry(100, 100, 1280, 720)
        self.setAcceptDrops(True)
        
        self.current_os = platform.system()

        # VLC Configuration
        vlc_args = [
            '--no-xlib',
            '--aout=directx',
            '--avcodec-hw=dxva2',
            '--audio-resampler=soxr',
            '--network-caching=1500',
            '--file-caching=5000',  # Increase file caching
            '--disc-caching=5000',  # Increase disc caching
            '--clock-jitter=0',     # Reduce clock jitter
            '--clock-synchro=0',    # Disable clock synchro
            '--no-drop-late-frames',# Don't drop late frames
            '--no-skip-frames'      # Don't skip frames
        ]
        self.instance = vlc.Instance(vlc_args)
        self.media_player = self.instance.media_player_new()
        self.equalizer = vlc.AudioEqualizer()
        self.media_player.set_equalizer(self.equalizer)

        # Player State
        self.playlist = []
        self.current_index = -1
        self.loop_modes = ["single", "playlist", "none"]
        self.current_loop_mode = 0  # 0: No Loop, 1: Loop Single, 2: Loop All
        self.loop_button = QPushButton("🔁")
        self.loop_button.setCheckable(True)
        self.loop_button.clicked.connect(self.toggle_loop_mode)
        self.loop_button.setToolTip("Loop Mode (No Loop)")
        self.is_dark_theme = False
        self.volume_before_mute = 100
        self.sleep_preventer = SleepPreventer()
        self.config_path = os.path.join(
            QStandardPaths.writableLocation(QStandardPaths.ConfigLocation),
            "media_player_settings.json"
        )

        # Video Adjustments
        self.video_filters = {
            'brightness': 1.0,
            'contrast': 1.0,
            'hue': 0,
            'saturation': 1.0,
            'gamma': 1.0
        }

        self.init_ui()
        self.setup_playlist_context_menu()
        self.init_effects()
        self.load_settings()

        # Setup timer and shortcuts
        self.timer = QTimer(self)
        self.timer.setInterval(250)  # Update every 250ms
        self.timer.timeout.connect(self.update_ui)
        self.timer.start()
        self.setup_shortcuts()

        self.sleep_preventer.prevent_sleep()
        self.ab_repeat_timer = QTimer(self)
        self.ab_repeat_timer.timeout.connect(self.check_ab_repeat)
        
        # Set default publisher ID
        self.publisher_id.setText("pub-9105010442621690")
        self.ad_slot_id.setText("AUTO")  # Use auto-ads by default

    def init_ui(self):
        main_widget = QWidget(self)
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Create theme toggle before setting up tabs
        self.theme_toggle = QCheckBox("Dark Theme")
        self.theme_toggle.setChecked(self.is_dark_theme)
        self.theme_toggle.stateChanged.connect(self.toggle_theme)

        self.tab_widget = QTabWidget()
        self.setup_video_tab()
        self.setup_playlist_tab()
        self.setup_effects_tab()
        self.setup_equalizer_tab()
        self.setup_shortcuts_tab()  # Add this line
        self.setup_ad_tab()  # Add this line
        self.setup_sponsorship_tab()  # Add this line

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)

        layout.addWidget(self.tab_widget)

        # Apply initial theme
        self.toggle_theme(self.is_dark_theme)

    def setup_video_tab(self):
        # First create the video frame
        self.video_frame = QWidget()
        self.video_frame.setStyleSheet("background-color: black;")
        self.video_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.set_video_output()

        # Create URL input and play button first
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("Enter YouTube URL or stream URL")
        self.url_play_button = QPushButton("Play URL")
        self.url_play_button.clicked.connect(lambda: self.play_url(self.url_input.text()))

        # Create URL input widget with initial hidden state
        self.url_widget = QWidget()
        url_layout = QHBoxLayout(self.url_widget)
        url_layout.setContentsMargins(0, 0, 0, 0)
        url_layout.addWidget(self.url_input)
        url_layout.addWidget(self.url_play_button)
        self.url_widget.hide()

        # Create all control buttons and widgets
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        self.play_button.clicked.connect(self.toggle_playback)
        self.play_button.setToolTip("Play/Pause (Space)")

        self.stop_button = QPushButton()
        self.stop_button.setIcon(self.style().standardIcon(QStyle.SP_MediaStop))
        self.stop_button.clicked.connect(self.stop)
        self.stop_button.setToolTip("Stop")

        self.prev_button = QPushButton("⏮")
        self.prev_button.clicked.connect(self.prev_track)
        self.prev_button.setToolTip("Previous Track (Ctrl+Left)")

        self.next_button = QPushButton("⏭")
        self.next_button.clicked.connect(self.next_track)
        self.next_button.setToolTip("Next Track (Ctrl+Right)")

        # Create fullscreen and URL toggle buttons first
        self.fullscreen_button = QPushButton("⛶")
        self.fullscreen_button.setToolTip("Toggle Fullscreen (F)")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)
        self.fullscreen_button.setObjectName("fullscreen_button")

        self.url_toggle_button = QPushButton("🔗")
        self.url_toggle_button.setToolTip("Toggle URL Input")
        self.url_toggle_button.setCheckable(True)
        self.url_toggle_button.clicked.connect(self.toggle_url_input)
        self.url_toggle_button.setObjectName("url_toggle_button")

        # 5-second skip buttons
        self.skip_back_5s_btn = QPushButton("⏪")
        self.skip_back_5s_btn.clicked.connect(self.skip_backward_5s)
        self.skip_back_5s_btn.setToolTip("Skip Back 5s (Left Arrow)")
        
        self.skip_forward_5s_btn = QPushButton("⏩")
        self.skip_forward_5s_btn.clicked.connect(self.skip_forward_5s)
        self.skip_forward_5s_btn.setToolTip("Skip Forward 5s (Right Arrow)")

        # Volume slider with boost up to 1000
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 1000)  # Allow up to 1000% volume boost
        self.volume_slider.setValue(100)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.volume_slider.setToolTip("Volume Control (0-1000%)")

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 1000)
        self.position_slider.sliderMoved.connect(self.set_position)
        self.position_slider.setObjectName("position_slider")

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setAlignment(Qt.AlignCenter)

        # Update control layout
        control_layout = QHBoxLayout()
        control_layout.addWidget(self.skip_back_5s_btn)
        control_layout.addWidget(self.prev_button)
        control_layout.addWidget(self.play_button)
        control_layout.addWidget(self.stop_button)
        control_layout.addWidget(self.next_button)
        control_layout.addWidget(self.skip_forward_5s_btn)
        control_layout.addWidget(self.loop_button)
        control_layout.addWidget(QLabel("🔊"))
        control_layout.addWidget(self.volume_slider)
        control_layout.addWidget(self.url_toggle_button)
        control_layout.addWidget(self.fullscreen_button)
        
        # Replace the speed slider with a combo box
        self.speed_label = QLabel("Speed: 1.0x")
        self.speed_combo = QComboBox()
        self.speed_combo.addItems(["0.25x", "0.5x", "0.75x", "1.0x", "1.25x", "1.5x", "1.75x", "2.0x", "2.5x", "3.0x", "4.0x"])
        self.speed_combo.setCurrentText("1.0x")
        self.speed_combo.currentTextChanged.connect(self.change_playback_speed)
        
        # Add aspect ratio control
        self.aspect_combo = QComboBox()
        self.aspect_combo.addItems(["Default", "16:9", "4:3", "1:1", "2.35:1"])
        self.aspect_combo.currentTextChanged.connect(self.change_aspect_ratio)
        
        # Add A-B repeat controls
        self.point_a_button = QPushButton("A")
        self.point_b_button = QPushButton("B")
        self.point_a_button.clicked.connect(self.set_point_a)
        self.point_b_button.clicked.connect(self.set_point_b)
        
        # Add screenshot button
        self.screenshot_button = QPushButton("📷")
        self.screenshot_button.clicked.connect(self.take_screenshot)
        
        # Create a container for the video frame
        self.video_container = QWidget()
        video_container_layout = QVBoxLayout(self.video_container)
        video_container_layout.addWidget(self.video_frame)
        video_container_layout.setContentsMargins(0, 0, 0, 0)
        
        # Move dark theme toggle next to screenshot button in advanced controls
        advanced_controls = QHBoxLayout()
        advanced_controls.addWidget(QLabel("Speed:"))
        advanced_controls.addWidget(self.speed_combo)
        advanced_controls.addWidget(self.speed_label)
        advanced_controls.addWidget(QLabel("Aspect:"))
        advanced_controls.addWidget(self.aspect_combo)
        advanced_controls.addWidget(self.point_a_button)
        advanced_controls.addWidget(self.point_b_button)
        advanced_controls.addWidget(self.screenshot_button)
        advanced_controls.addWidget(self.theme_toggle)  # Move theme toggle here

        # Create a widget to hold all controls
        self.controls_widget = QWidget()
        controls_layout = QVBoxLayout(self.controls_widget)
        controls_layout.addWidget(self.time_label)
        controls_layout.addWidget(self.position_slider)
        controls_layout.addLayout(control_layout)
        controls_layout.addLayout(advanced_controls)
        controls_layout.addWidget(self.url_widget)  # Add URL widget here

        self.video_layout = QVBoxLayout()
        self.video_layout.addWidget(self.video_container, 90)
        self.video_layout.addWidget(self.controls_widget)
        
        video_tab = QWidget()
        video_tab.setLayout(self.video_layout)
        self.tab_widget.addTab(video_tab, "🎥 Player")
        self.video_container.setObjectName("video_container")

    def set_video_output(self):
        video_widget = QWidget(self.video_frame)
        video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        if self.current_os == "Windows":
            self.media_player.set_hwnd(video_widget.winId())
        elif self.current_os == "Darwin":
            self.media_player.set_nsobject(int(video_widget.winId()))
        elif self.current_os == "Linux":
            self.media_player.set_xwindow(int(video_widget.winId()))
        else:
            print("Unsupported OS for video output.")
        
        layout = QVBoxLayout(self.video_frame)
        layout.addWidget(video_widget)
        layout.setContentsMargins(0, 0, 0, 0)

    def setup_playlist_tab(self):
        self.playlist_widget = QListWidget()
        self.playlist_widget.setDragDropMode(QListWidget.InternalMove)
        self.playlist_widget.model().rowsMoved.connect(self.update_playlist_order)
        self.playlist_widget.itemDoubleClicked.connect(self.play_selected_item)

        add_button = QPushButton("Add Files")
        add_button.clicked.connect(self.add_files)

        clear_button = QPushButton("Clear Playlist")
        clear_button.clicked.connect(self.clear_playlist)

        save_button = QPushButton("Save Playlist")
        save_button.clicked.connect(self.save_playlist)

        load_button = QPushButton("Load Playlist")
        load_button.clicked.connect(self.load_playlist)

        button_layout = QHBoxLayout()
        button_layout.addWidget(add_button)
        button_layout.addWidget(clear_button)
        button_layout.addWidget(save_button)
        button_layout.addWidget(load_button)

        playlist_layout = QVBoxLayout()
        playlist_layout.addLayout(button_layout)
        playlist_layout.addWidget(self.playlist_widget)

        playlist_tab = QWidget()
        playlist_tab.setLayout(playlist_layout)
        self.tab_widget.addTab(playlist_tab, "📜 Playlist")

    def setup_effects_tab(self):
        """Enhanced effects tab with more filters and reset functionality"""
        effects_layout = QVBoxLayout()
        
        # Create sliders for various effects
        self.effect_sliders = {
            'brightness': (QSlider(Qt.Horizontal), "Brightness", 0, 200, 100),
            'contrast': (QSlider(Qt.Horizontal), "Contrast", 0, 200, 100),
            'hue': (QSlider(Qt.Horizontal), "Hue", 0, 360, 180),
            'saturation': (QSlider(Qt.Horizontal), "Saturation", 0, 200, 100),
            'gamma': (QSlider(Qt.Horizontal), "Gamma", 0, 200, 100),
            'sharpness': (QSlider(Qt.Horizontal), "Sharpness", 0, 100, 50)
        }
        
        # Create layout for each effect with label and value display
        for effect, (slider, label, min_val, max_val, default) in self.effect_sliders.items():
            slider.setRange(min_val, max_val)
            slider.setValue(default)
            slider.setObjectName(f"{effect}_slider")
            
            # Create horizontal layout for each effect
            effect_row = QHBoxLayout()
            
            # Add label
            effect_label = QLabel(label)
            effect_label.setMinimumWidth(100)
            
            # Add value label
            value_label = QLabel(str(default))
            value_label.setObjectName(f"{effect}_value")
            value_label.setMinimumWidth(50)
            
            # Connect slider to update function
            slider.valueChanged.connect(
                lambda val, e=effect, vl=value_label: self.update_effect(e, val, vl)
            )
            
            # Add widgets to layout
            effect_row.addWidget(effect_label)
            effect_row.addWidget(slider)
            effect_row.addWidget(value_label)
            
            effects_layout.addLayout(effect_row)
        
        # Add reset buttons
        buttons_layout = QHBoxLayout()
        
        # Reset individual effects
        reset_current = QPushButton("Reset Current")
        reset_current.clicked.connect(
            lambda: self.reset_effect(self.tab_widget.currentWidget())
        )
        
        # Reset all effects
        reset_all = QPushButton("Reset All")
        reset_all.clicked.connect(self.reset_all_effects)
        
        buttons_layout.addWidget(reset_current)
        buttons_layout.addWidget(reset_all)
        effects_layout.addLayout(buttons_layout)
        
        # Add some spacing
        effects_layout.addSpacing(20)
        
        # Create presets dropdown
        presets_layout = QHBoxLayout()
        presets_layout.addWidget(QLabel("Presets:"))
        self.presets_combo = QComboBox()
        self.presets_combo.addItems([
            "Default",
            "Cinema",
            "Vivid",
            "Warm",
            "Cool",
            "Black & White"
        ])
        self.presets_combo.currentTextChanged.connect(self.apply_preset)
        presets_layout.addWidget(self.presets_combo)
        
        effects_layout.addLayout(presets_layout)
        
        # Add to tab
        effects_tab = QWidget()
        effects_tab.setLayout(effects_layout)
        self.tab_widget.addTab(effects_tab, "🌈 Effects")

    def setup_equalizer_tab(self):
        """Setup equalizer tab with presets and 10-band controls"""
        equalizer_layout = QVBoxLayout()
        
        # Equalizer enable/disable
        self.eq_enabled = QCheckBox("Enable Equalizer")
        self.eq_enabled.setChecked(False)
        self.eq_enabled.stateChanged.connect(self.toggle_equalizer)
        
        # Presets combo box
        presets_layout = QHBoxLayout()
        presets_layout.addWidget(QLabel("Presets:"))
        self.eq_presets = QComboBox()
        self.eq_presets.addItems([
            "Flat",
            "Classical",
            "Club",
            "Dance",
            "Full Bass",
            "Full Bass & Treble",
            "Full Treble",
            "Headphones",
            "Large Hall",
            "Live",
            "Party",
            "Pop",
            "Reggae",
            "Rock",
            "Ska",
            "Soft",
            "Soft Rock",
            "Techno"
        ])
        self.eq_presets.currentTextChanged.connect(self.apply_eq_preset)
        presets_layout.addWidget(self.eq_presets)
        
        # Preamp control
        preamp_layout = QHBoxLayout()
        preamp_layout.addWidget(QLabel("Preamp:"))
        self.preamp_slider = QSlider(Qt.Horizontal)
        self.preamp_slider.setRange(-20, 20)
        self.preamp_slider.setValue(0)
        self.preamp_slider.valueChanged.connect(self.update_preamp)
        self.preamp_value = QLabel("0 dB")
        preamp_layout.addWidget(self.preamp_slider)
        preamp_layout.addWidget(self.preamp_value)
        
        # Frequency bands (10-band equalizer)
        bands_layout = QGridLayout()
        self.band_sliders = []
        frequencies = ["31", "63", "125", "250", "500", "1k", "2k", "4k", "8k", "16k"]
        
        for i, freq in enumerate(frequencies):
            # Create vertical slider for each band
            slider = QSlider(Qt.Vertical)
            slider.setRange(-20, 20)
            slider.setValue(0)
            slider.valueChanged.connect(lambda v, idx=i: self.update_band(idx, v))
            
            # Create labels
            freq_label = QLabel(f"{freq}Hz")
            value_label = QLabel("0 dB")
            value_label.setAlignment(Qt.AlignCenter)
            
            # Add to layout
            bands_layout.addWidget(freq_label, 0, i, Qt.AlignCenter)
            bands_layout.addWidget(slider, 1, i, Qt.AlignCenter)
            bands_layout.addWidget(value_label, 2, i, Qt.AlignCenter)
            
            # Store references
            self.band_sliders.append((slider, value_label))
        
        # Reset button
        reset_button = QPushButton("Reset All")
        reset_button.clicked.connect(self.reset_equalizer)
        
        # Add all components to main layout
        equalizer_layout.addWidget(self.eq_enabled)
        equalizer_layout.addLayout(presets_layout)
        equalizer_layout.addLayout(preamp_layout)
        equalizer_layout.addSpacing(20)
        equalizer_layout.addLayout(bands_layout)
        equalizer_layout.addSpacing(10)
        equalizer_layout.addWidget(reset_button)
        
        # Add to tab
        equalizer_tab = QWidget()
        equalizer_tab.setLayout(equalizer_layout)
        self.tab_widget.addTab(equalizer_tab, "🎚 Equalizer")

    def setup_shortcuts_tab(self):
        """Setup shortcuts help tab"""
        shortcuts_layout = QVBoxLayout()
        
        # Title
        title = QLabel("Keyboard Shortcuts")
        title.setStyleSheet("font-size: 16px; font-weight: bold; margin-bottom: 10px;")
        shortcuts_layout.addWidget(title)
        
        # Create a grid for shortcuts
        grid = QGridLayout()
        shortcuts = [
            ("Space", "Play/Pause"),
            ("F", "Toggle Fullscreen"),
            ("M", "Toggle Mute"),
            ("Left Arrow", "Skip Backward 5s"),
            ("Right Arrow", "Skip Forward 5s"),
            ("Ctrl + Left", "Previous Track"),
            ("Ctrl + Right", "Next Track"),
            ("[", "Decrease Speed (0.75x)"),
            ("]", "Increase Speed (1.25x)"),
            ("\\", "Reset Speed (1.0x)"),
            ("S", "Take Screenshot"),
            ("A", "Set A-B Repeat Point A"),
            ("B", "Set A-B Repeat Point B"),
            ("R", "Reset A-B Repeat")
        ]
        
        # Add shortcuts to grid
        for i, (key, action) in enumerate(shortcuts):
            key_label = QLabel(key)
            key_label.setStyleSheet("""
                background-color: #2d2d2d;
                color: #ffffff;
                padding: 5px 10px;
                border-radius: 4px;
                font-family: 'SF Mono', 'Menlo', 'Monaco', monospace;
            """)
            
            action_label = QLabel(action)
            action_label.setStyleSheet("padding-left: 10px;")
            
            grid.addWidget(key_label, i, 0)
            grid.addWidget(action_label, i, 1)
        
        # Add grid to layout
        grid_widget = QWidget()
        grid_widget.setLayout(grid)
        
        # Add scroll area in case there are many shortcuts
        scroll = QScrollArea()
        scroll.setWidget(grid_widget)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollBar {
                background-color: #2d2d2d;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle {
                background-color: #555555;
                border-radius: 4px;
                min-height: 30px;
            }
            QScrollBar::handle:hover {
                background-color: #666666;
            }
        """)
        
        shortcuts_layout.addWidget(scroll)
        
        # Add to tab
        shortcuts_tab = QWidget()
        shortcuts_tab.setLayout(shortcuts_layout)
        self.tab_widget.addTab(shortcuts_tab, "⌨️ Shortcuts")

    def setup_ad_tab(self):
        """Setup tab for displaying Google Ads with earnings tracking"""
        ad_tab = QWidget()
        layout = QVBoxLayout(ad_tab)
        
        # Stats Group
        stats_group = QGroupBox("Ad Statistics")
        stats_layout = QGridLayout()
        
        self.earnings_label = QLabel("$0.00")
        self.views_label = QLabel("0")
        self.cpm_label = QLabel("$2.00")
        
        stats_layout.addWidget(QLabel("Your Earnings (40%):"), 0, 0)  # Updated label
        stats_layout.addWidget(self.earnings_label, 0, 1)
        stats_layout.addWidget(QLabel("Ad Views:"), 1, 0)
        stats_layout.addWidget(self.views_label, 1, 1)
        stats_layout.addWidget(QLabel("Base CPM Rate:"), 2, 0)  # Updated label
        stats_layout.addWidget(self.cpm_label, 2, 1)
        
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)
        
        # Ad Settings Group
        settings_group = QGroupBox("Ad Configuration")
        settings_layout = QFormLayout()
        
        self.publisher_id = QLineEdit()
        self.ad_slot_id = QLineEdit()
        settings_layout.addRow("Publisher ID:", self.publisher_id)
        settings_layout.addRow("Ad Slot ID:", self.ad_slot_id)
        
        apply_button = QPushButton("Apply Settings")
        apply_button.clicked.connect(self.update_ad_settings)
        settings_layout.addRow(apply_button)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Ad Display
        ad_display_group = QGroupBox("Advertisement")
        ad_layout = QVBoxLayout()
        
        self.ad_view = QWebEngineView()
        self.ad_view.setMinimumHeight(250)
        
        # Initial ad HTML template
        self.update_ad_html()
        
        ad_layout.addWidget(self.ad_view)
        
        # Refresh button
        refresh_button = QPushButton("Refresh Advertisement")
        refresh_button.clicked.connect(self.refresh_ad)
        ad_layout.addWidget(refresh_button)
        
        ad_display_group.setLayout(ad_layout)
        layout.addWidget(ad_display_group)
        
        # Initialize tracking variables
        self.ad_views = 0
        self.ad_earnings = 0.0
        self.cpm_rate = 2.0  # $2 per thousand views
        
        # Start tracking timer
        self.ad_timer = QTimer()
        self.ad_timer.timeout.connect(self.update_ad_stats)
        self.ad_timer.start(1000)  # Update every second
        
        self.tab_widget.addTab(ad_tab, "📢 Ads")

    def setup_sponsorship_tab(self):
        """Setup tab for open-source sponsorship"""
        sponsorship_tab = QWidget()
        layout = QVBoxLayout(sponsorship_tab)

        # Add a description
        description = QLabel(
            "Support the development of this open-source media player! "
            "Your contributions help us improve and add new features."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        # Add buttons for sponsorship platforms
        github_button = QPushButton("Sponsor on GitHub")
        github_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://github.com/sponsors/your-username")))

        patreon_button = QPushButton("Support on Patreon")
        patreon_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://www.patreon.com/your-username")))

        open_collective_button = QPushButton("Contribute on Open Collective")
        open_collective_button.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://opencollective.com/your-project")))

        # Add buttons to layout
        layout.addWidget(github_button)
        layout.addWidget(patreon_button)
        layout.addWidget(open_collective_button)

        # Add the tab to the main tab widget
        self.tab_widget.addTab(sponsorship_tab, "❤️ Support Us")

    def setup_playlist_context_menu(self):
        self.playlist_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.playlist_widget.customContextMenuRequested.connect(self.show_playlist_context_menu)

    def show_playlist_context_menu(self, position):
        context_menu = QMenu()
        play_action = context_menu.addAction("Play")
        remove_action = context_menu.addAction("Remove")
        
        action = context_menu.exec_(self.playlist_widget.mapToGlobal(position))
        
        if action == play_action:
            self.play_selected_item(None)
        elif action == remove_action:
            self.remove_selected_item()

    def remove_selected_item(self):
        selected_row = self.playlist_widget.currentRow()
        if (selected_row >= 0):
            self.playlist_widget.takeItem(selected_row)
            self.playlist.pop(selected_row)
            if self.current_index >= selected_row:
                self.current_index -= 1

    def init_effects(self):
        self.media_player.video_set_adjust_int(vlc.VideoAdjustOption.Enable, 1)

    def update_brightness(self, value):
        self.video_filters['brightness'] = value / 100
        self.apply_video_filters()

    def update_contrast(self, value):
        self.video_filters['contrast'] = value / 100
        self.apply_video_filters()

    def apply_video_filters(self):
        """Apply video filters with expanded effects"""
        if self.media_player.is_playing():
            try:
                self.media_player.video_set_adjust_float(
                    vlc.VideoAdjustOption.Brightness, 
                    self.video_filters.get('brightness', 1.0)
                )
                self.media_player.video_set_adjust_float(
                    vlc.VideoAdjustOption.Contrast, 
                    self.video_filters.get('contrast', 1.0)
                )
                self.media_player.video_set_adjust_int(
                    vlc.VideoAdjustOption.Hue, 
                    int(self.video_filters.get('hue', 180))
                )
                self.media_player.video_set_adjust_float(
                    vlc.VideoAdjustOption.Saturation, 
                    self.video_filters.get('saturation', 1.0)
                )
                self.media_player.video_set_adjust_float(
                    vlc.VideoAdjustOption.Gamma, 
                    self.video_filters.get('gamma', 1.0)
                )
            except Exception as e:
                print(f"Error applying video filters: {e}")

    def toggle_playback(self):
        if self.media_player.is_playing():
            self.media_player.pause()
            self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            self.media_player.play()
            self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def stop(self):
        self.media_player.stop()
        self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

    def prev_track(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.play_item(self.current_index)

    def next_track(self):
        if self.current_index < len(self.playlist) - 1:
            self.current_index += 1
            self.play_item(self.current_index)

    def play_item(self, index):
        if 0 <= index < len(self.playlist):
            self.current_index = index
            self.load_media(self.playlist[index])
            self.playlist_widget.setCurrentRow(index)

    def optimize_playback(self):
        """Optimize playback settings to prevent buffer deadlocks"""
        try:
            # Set media options
            self.media_player.set_hardware_decoding(True)
            self.media_player.set_time_mode(vlc.MediaPlayerTimeMode.SystemTime)
            
            # Set media parameters
            media = self.media_player.get_media()
            if media:
                media.add_option(":network-caching=1500")
                media.add_option(":file-caching=5000")
                media.add_option(":disc-caching=5000")
                media.add_option(":clock-jitter=0")
                media.add_option(":clock-synchro=0")
        except Exception as e:
            print(f"Error optimizing playback: {e}")

    def load_media(self, media_path):
        """Updated load_media method with optimization"""
        try:
            media = self.instance.media_new(media_path)
            self.media_player.set_media(media)
            self.optimize_playback()  # Apply optimizations
            self.media_player.play()
            self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        except Exception as e:
            print(f"Error loading media: {e}")
            self.status_bar.showMessage("Failed to load media", 2000)

    def update_playlist_order(self):
        new_playlist = []
        for i in range(self.playlist_widget.count()):
            new_playlist.append(self.playlist_widget.item(i).text())
        self.playlist = new_playlist
        
        if self.current_index >= 0:
            current_item = self.playlist_widget.currentItem()
            if current_item:
                self.current_index = self.playlist_widget.row(current_item)

    def play_selected_item(self, item):
        selected_item = self.playlist_widget.currentRow()
        if selected_item >= 0:
            self.play_item(selected_item)

    def add_files(self):
        file_paths, _ = QFileDialog.getOpenFileNames(self, "Open Media Files", "", "Media Files (*.mp3 *.mp4 *.avi *.mkv *.flv)")
        if file_paths:
            self.playlist.extend(file_paths)
            for path in file_paths:
                self.playlist_widget.addItem(os.path.basename(path))
                
            if self.current_index == -1 and len(self.playlist) > 0:
                self.current_index = 0
                self.play_item(0)

    def clear_playlist(self):
        self.playlist.clear()
        self.playlist_widget.clear()
        self.current_index = -1
        self.media_player.stop()

    def save_playlist(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Playlist", "", "Playlist Files (*.json)")
        if file_path:
            with open(file_path, 'w') as f:
                json.dump(self.playlist, f)
            self.status_bar.showMessage(f"Playlist saved to {file_path}", 3000)

    def load_playlist(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Load Playlist", "", "Playlist Files (*.json)")
        if file_path and os.path.exists(file_path):
            with open(file_path, 'r') as f:
                self.playlist = json.load(f)
            self.playlist_widget.clear()
            for path in self.playlist:
                self.playlist_widget.addItem(os.path.basename(path))
            self.status_bar.showMessage(f"Playlist loaded from {file_path}", 3000)

    def set_volume(self, value):
        """
        Set the volume of the media player. Supports up to 1000% volume boost.
        """
        # Cap the volume at 200% for VLC, but apply gain for higher values
        if value <= 200:
            self.media_player.audio_set_volume(value)
            self.equalizer.set_preamp(0)  # No gain boost
        else:
            self.media_player.audio_set_volume(200)  # Max VLC volume
            gain = (value - 200) / 8  # Calculate gain boost (e.g., 800 -> +75 dB)
            self.equalizer.set_preamp(gain)
            self.media_player.set_equalizer(self.equalizer)

        if value > 0:
            self.volume_before_mute = value

    def set_position(self, position):
        """
        Set the playback position when the user moves the slider.
        """
        media_length = self.media_player.get_length()
        if media_length > 0:
            new_time = int((position / 1000.0) * media_length)
            self.media_player.set_time(new_time)

    def skip_forward_5s(self):
        """
        Skip forward 5 seconds in the currently playing media.
        """
        if self.media_player.is_playing():
            current_time = self.media_player.get_time()
            self.media_player.set_time(current_time + 5000)

    def skip_backward_5s(self):
        """
        Skip backward 5 seconds in the currently playing media.
        """
        if self.media_player.is_playing():
            current_time = self.media_player.get_time()
            self.media_player.set_time(max(0, current_time - 5000))

    def update_ui(self):
        """
        Update the UI elements such as the position slider and time label.
        """
        media_length = self.media_player.get_length()  # Total length of the media in ms
        current_time = self.media_player.get_time()  # Current playback time in ms

        if self.media_player.is_playing():
            if media_length > 0:
                # Update position slider only if the user is not dragging it
                if not self.position_slider.isSliderDown():
                    self.position_slider.setValue(int((current_time / media_length) * 1000))
                
                # Update time label
                self.time_label.setText(
                    f"{self.format_time(current_time)} / {self.format_time(media_length)}"
                )
        elif self.media_player.get_state() == vlc.State.Paused:
            # Keep the slider and time label at the paused position
            if media_length > 0:
                self.time_label.setText(
                    f"{self.format_time(current_time)} / {self.format_time(media_length)}"
                )
        else:
            # If media is stopped, reset the slider and time label
            self.position_slider.setValue(0)
            self.time_label.setText("00:00 / 00:00")

        # Handle media end
        if self.media_player.get_state() == vlc.State.Ended:
            self.handle_media_end()

    @staticmethod
    def format_time(ms):
        """
        Format time in milliseconds to HH:MM:SS or MM:SS format.
        """
        seconds = ms // 1000
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds = seconds % 60

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def handle_media_end(self):
        """
        Handle media end based on the current loop mode
        """
        if self.current_loop_mode == 1:  # Loop Single
            self.play_item(self.current_index)
        elif self.current_loop_mode == 2:  # Loop All
            if self.current_index < len(self.playlist) - 1:
                self.next_track()
            else:
                self.current_index = 0
                self.play_item(0)
        else:  # No Loop
            if self.current_index < len(self.playlist) - 1:
                self.next_track()
            else:
                self.stop()
                self.current_index = -1

    def toggle_theme(self, state):
        self.is_dark_theme = bool(state)
        self.setStyleSheet(self.get_dark_style() if self.is_dark_theme else self.get_light_style())

    def get_dark_style(self):
        return '''
    QMainWindow, QWidget {
        background-color: #121212;
        color: #e0e0e0;
        font-family: 'Segoe UI', 'Roboto', sans-serif;
        font-size: 13px;
    }

    QPushButton {
        background-color: #2a2a2a;
        color: #e0e0e0;
        border: 1px solid #3a3a3a;
        padding: 8px 15px;
        border-radius: 6px;
    }

    QPushButton:hover {
        background-color: #3d3d3d;
        border: 1px solid #5c8374;
    }

    QPushButton:pressed {
        background-color: #1e1e1e;
    }

    QSlider::groove:horizontal {
        background: #2d2d2d;
        height: 6px;
        border-radius: 3px;
    }

    QSlider::handle:horizontal {
        background: #5c8374;
        width: 14px;
        height: 14px;
        border-radius: 7px;
        margin: -4px 0;
    }

    QSlider::handle:horizontal:hover {
        background: #769e8c;
    }

    QTabWidget::pane {
        border: none;
        background-color: #121212;
    }

    QTabBar::tab {
        background-color: #222222;
        color: #aaaaaa;
        padding: 10px 20px;
        border: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        margin-right: 2px;
    }

    QTabBar::tab:selected {
        background-color: #5c8374;
        color: #ffffff;
        font-weight: bold;
    }

    QListWidget {
        background-color: #1c1c1c;
        color: #e0e0e0;
        border: 1px solid #2b2b2b;
        border-radius: 4px;
        padding: 5px;
    }

    QListWidget::item:selected {
        background-color: #5c8374;
        color: #ffffff;
    }

    QCheckBox::indicator:checked {
        background-color: #5c8374;
        border: 2px solid #5c8374;
    }

    QComboBox:hover {
        background-color: #3d3d3d;
        border: 1px solid #5c8374;
    }

    #volume_slider::groove:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                    stop:0 #5c8374, stop:1 #2a2a2a);
    }

    #position_slider::handle:horizontal {
        background: #5c8374;
    }

    #position_slider::handle:horizontal:hover {
        background: #769e8c;
    }

    #fullscreen_video {
        background-color: #000000;
        border: none;
        border-radius: 0px;
    }
    
    QPushButton#fullscreen_button {
        font-size: 16px;
        padding: 8px 12px;
        background-color: #2d2d2d;
    }
    
    QPushButton#url_toggle_button {
        font-size: 14px;
        padding: 8px 12px;
        background-color: #2d2d2d;
    }
    
    QPushButton#url_toggle_button:checked {
        background-color: #5c8374;
    }
    '''

    def get_light_style(self):
        return '''
    QMainWindow, QWidget {
        background-color: #f5f5f5;
        color: #212121;
        font-family: 'Segoe UI', 'Roboto', 'Arial';
        font-size: 13px;
    }

    QPushButton {
        background-color: #e0e0e0;
        color: #212121;
        border: 1px solid #cccccc;
        padding: 8px 15px;
        border-radius: 6px;
        font-weight: 500;
        transition: all 0.2s ease-in-out;
    }

    QPushButton:hover {
        background-color: #dcdcdc;
        border: 1px solid #2196F3;
    }

    QPushButton:pressed {
        background-color: #bdbdbd;
        box-shadow: inset 0 0 5px #aaaaaa;
    }

    QSlider::groove:horizontal {
        background: #e0e0e0;
        height: 6px;
        border-radius: 3px;
    }

    QSlider::handle:horizontal {
        background: #2196F3;
        width: 14px;
        height: 14px;
        border-radius: 7px;
        margin: -4px 0;
    }

    QSlider::handle:horizontal:hover {
        background: #1976D2;
    }

    QTabWidget::pane {
        border: none;
        background-color: #ffffff;
    }

    QTabBar::tab {
        background-color: #e0e0e0;
        color: #555555;
        padding: 10px 20px;
        border: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        margin-right: 2px;
    }

    QTabBar::tab:selected {
        background-color: #2196F3;
        color: #ffffff;
        font-weight: bold;
    }

    QListWidget {
        background-color: #ffffff;
        color: #212121;
        border: 1px solid #dddddd;
        border-radius: 6px;
        padding: 5px;
    }

    QListWidget::item {
        padding: 8px;
        border-radius: 4px;
    }

    QListWidget::item:selected {
        background-color: #2196F3;
        color: #ffffff;
    }

    QListWidget::item:hover {
        background-color: #f0f0f0;
    }

    QLabel {
        color: #212121;
        font-weight: 500;
    }

    QCheckBox {
        color: #212121;
        spacing: 8px;
    }

    QCheckBox::indicator {
        width: 18px;
        height: 18px;
        border-radius: 3px;
        border: 2px solid #bdbdbd;
    }

    QCheckBox::indicator:checked {
        background-color: #2196F3;
        border: 2px solid #2196F3;
    }

    QComboBox {
        background-color: #e0e0e0;
        color: #212121;
        border: 1px solid #cccccc;
        border-radius: 6px;
        padding: 6px 12px;
        min-width: 6em;
    }

    QComboBox:hover {
        background-color: #dcdcdc;
        border: 1px solid #2196F3;
    }

    QComboBox::drop-down {
        border: none;
    }

    QComboBox::down-arrow {
        image: none;
        border: none;
    }

    QStatusBar {
        background-color: #e0e0e0;
        color: #212121;
        border-top: 1px solid #cccccc;
    }

    #video_container {
        background-color: #000000;
        border-radius: 6px;
    }

    #controls_widget {
        background-color: rgba(255, 255, 255, 0.9);
        border-radius: 6px;
        padding: 8px;
    }

    #time_label {
        font-family: 'SF Mono', 'Menlo', 'Consolas', monospace;
        font-size: 14px;
        color: #212121;
        padding: 5px;
        border-radius: 4px;
    }

    #volume_slider::groove:horizontal {
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                  stop:0 #2196F3, stop:1 #e0e0e0);
        height: 6px;
        border-radius: 3px;
    }

    #position_slider::groove:horizontal {
        background: #dcdcdc;
        height: 4px;
        border-radius: 2px;
    }

    #position_slider::handle:horizontal {
        background: #2196F3;
        width: 12px;
        height: 12px;
        border-radius: 6px;
        margin: -4px 0;
    }

    #position_slider::handle:horizontal:hover {
        background: #1976D2;
        width: 16px;
        height: 16px;
        border-radius: 8px;
        margin: -6px 0;
    }

    #fullscreen_video {
        background-color: #000000;
        border: none;
        border-radius: 0px;
    }
    
    QPushButton#fullscreen_button {
        font-size: 16px;
        padding: 8px 12px;
        background-color: #e0e0e0;
    }
    
    QPushButton#url_toggle_button {
        font-size: 14px;
        padding: 8px 12px;
        background-color: #e0e0e0;
    }
    
    QPushButton#url_toggle_button:checked {
        background-color: #2196F3;
        color: #ffffff;
    }
    '''


    def setup_shortcuts(self):
        """Setup keyboard shortcuts for the player"""
        # Play/Pause
        self.play_shortcut = QShortcut(QKeySequence(Qt.Key_Space), self)
        self.play_shortcut.activated.connect(self.toggle_playback)
        
        # Previous/Next track
        self.prev_shortcut = QShortcut(QKeySequence(Qt.CTRL + Qt.Key_Left), self)
        self.prev_shortcut.activated.connect(self.prev_track)
        
        self.next_shortcut = QShortcut(QKeySequence(Qt.CTRL + Qt.Key_Right), self)
        self.next_shortcut.activated.connect(self.next_track)
        
        # Fullscreen
        self.fullscreen_shortcut = QShortcut(QKeySequence(Qt.Key_F), self)
        self.fullscreen_shortcut.activated.connect(self.toggle_fullscreen)
        
        # Mute
        self.mute_shortcut = QShortcut(QKeySequence(Qt.Key_M), self)
        self.mute_shortcut.activated.connect(self.toggle_mute)
        
        # Skip forward/backward
        QShortcut(QKeySequence(Qt.Key_Right), self).activated.connect(self.skip_forward_5s)
        QShortcut(QKeySequence(Qt.Key_Left), self).activated.connect(self.skip_backward_5s)
        
        # Speed control
        QShortcut(QKeySequence("["), self).activated.connect(
            lambda: self.speed_combo.setCurrentText("0.75x"))
        QShortcut(QKeySequence("]"), self).activated.connect(
            lambda: self.speed_combo.setCurrentText("1.25x"))
        QShortcut(QKeySequence("\\"), self).activated.connect(
            lambda: self.speed_combo.setCurrentText("1.0x"))
        
        # Screenshot
        QShortcut(QKeySequence("S"), self).activated.connect(self.take_screenshot)
        
        # A-B repeat
        QShortcut(QKeySequence("A"), self).activated.connect(self.set_point_a)
        QShortcut(QKeySequence("B"), self).activated.connect(self.set_point_b)
        QShortcut(QKeySequence("R"), self).activated.connect(self.reset_ab_repeat)

    def toggle_fullscreen(self):
        if self.isFullScreen():
            # Exit fullscreen
            self.showNormal()
            self.video_frame.setParent(self.video_container)
            self.video_container.setParent(None)
            self.video_layout.addWidget(self.video_container, 90)
            self.video_layout.addWidget(self.controls_widget)
            self.controls_widget.show()
            self.tab_widget.tabBar().show()
            
            # Restore normal layout
            layout = QVBoxLayout(self.video_frame)
            layout.setContentsMargins(0, 0, 0, 0)
            self.set_video_output()
            
        else:
            # Enter fullscreen
            self.showFullScreen()
            self.controls_widget.hide()
            self.tab_widget.tabBar().hide()
            
            # Make video frame fill the entire screen
            self.video_frame.setParent(self)
            self.video_frame.setGeometry(0, 0, self.width(), self.height())
            self.video_frame.show()
            self.video_frame.raise_()
            
            # Re-initialize video output for fullscreen
            self.set_video_output()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.isFullScreen():
            # Update video frame size when window is resized
            self.video_frame.setGeometry(0, 0, self.width(), self.height())

    def mouseMoveEvent(self, event):
        if self.isFullScreen():
            # Show controls when mouse moves near bottom of screen
            if event.pos().y() > self.height() - 100:
                self.controls_widget.setParent(self)
                self.controls_widget.setGeometry(
                    0, 
                    self.height() - self.controls_widget.height(),
                    self.width(),
                    self.controls_widget.height()
                )
                self.controls_widget.show()
                self.controls_widget.raise_()
                QTimer.singleShot(3000, self._hide_controls)
            else:
                self.controls_widget.hide()

    def _hide_controls(self):
        """Helper method to hide controls if in fullscreen"""
        if self.isFullScreen():
            self.controls_widget.hide()

    def toggle_mute(self):
        if self.media_player.audio_get_mute():
            self.media_player.audio_set_mute(False)
            self.media_player.audio_set_volume(self.volume_before_mute)
            self.volume_slider.setValue(self.volume_before_mute)
        else:
            self.volume_before_mute = self.media_player.audio_get_volume()
            self.media_player.audio_set_mute(True)
            self.volume_slider.setValue(0)

    def load_settings(self):
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r') as f:
                    settings = json.load(f)
                    self.is_dark_theme = settings.get('is_dark_theme', False)
                    self.media_player.audio_set_volume(settings.get('volume', 100))
                    self.volume_slider.setValue(settings.get('volume', 100))
                    
                    # Load and set loop mode
                    saved_loop_mode = settings.get('loop_mode', 0)
                    self.current_loop_mode = saved_loop_mode
                    if saved_loop_mode > 0:
                        self.loop_button.setChecked(True)
                        if saved_loop_mode == 1:
                            self.loop_button.setText("🔂")
                        else:
                            self.loop_button.setText("🔁")
                    self.ad_views = settings.get('ad_views', 0)
                    self.ad_earnings = settings.get('ad_earnings', 0.0)
                    self.publisher_id.setText(settings.get('publisher_id', ''))
                    self.ad_slot_id.setText(settings.get('ad_slot_id', ''))
        except Exception as e:
            print(f"Error loading settings: {str(e)}")

    def save_settings(self):
        try:
            settings = {
                'is_dark_theme': self.is_dark_theme,
                'volume': self.media_player.audio_get_volume(),
                'loop_mode': self.current_loop_mode,  # Save loop mode
                'ad_views': self.ad_views,
                'ad_earnings': self.ad_earnings,
                'publisher_id': self.publisher_id.text(),
                'ad_slot_id': self.ad_slot_id.text()
            }
            
            os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
            
            with open(self.config_path, 'w') as f:
                json.dump(settings, f)
        except Exception as e:
            print(f"Error saving settings: {str(e)}")

    def closeEvent(self, event):
        self.save_settings()
        self.sleep_preventer.allow_sleep()
        event.accept()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        for url in urls:
            file_path = url.toLocalFile()
            if os.path.isfile(file_path):
                self.playlist.append(file_path)
                self.playlist_widget.addItem(os.path.basename(file_path))
                
        if not self.media_player.is_playing() and self.current_index == -1 and len(self.playlist) > 0:
            self.current_index = len(self.playlist) - len(urls)
            self.play_item(self.current_index)

    def toggle_loop_mode(self):
        """
        Toggle between loop modes: No Loop -> Loop Single -> Loop All
        """
        self.current_loop_mode = (self.current_loop_mode + 1) % 3
        
        if self.current_loop_mode == 0:  # No Loop
            self.loop_button.setToolTip("Loop Mode (No Loop)")
            self.loop_button.setText("🔁")
            self.loop_button.setChecked(False)
        elif self.current_loop_mode == 1:  # Loop Single
            self.loop_button.setToolTip("Loop Mode (Loop Single)")
            self.loop_button.setText("🔂")
            self.loop_button.setChecked(True)
        else:  # Loop All
            self.loop_button.setToolTip("Loop Mode (Loop All)")
            self.loop_button.setText("🔁")
            self.loop_button.setChecked(True)
        
        self.status_bar.showMessage(f"Loop mode: {self.loop_modes[self.current_loop_mode]}", 2000)

    def change_aspect_ratio(self, ratio):
        """Change the video aspect ratio"""
        ratios = {
            "Default": None,  # Changed from 0 to None
            "16:9": "16:9",
            "4:3": "4:3",
            "1:1": "1:1",
            "2.35:1": "2.35:1"
        }
        
        if ratio in ratios:
            aspect = ratios[ratio]
            try:
                # Pass None to reset to default aspect ratio
                if (aspect is None):
                    self.media_player.video_set_aspect_ratio(None)
                else:
                    self.media_player.video_set_aspect_ratio(str(aspect))
                self.status_bar.showMessage(f"Aspect ratio changed to {ratio}", 2000)
            except Exception as e:
                print(f"Error setting aspect ratio: {e}")
                self.status_bar.showMessage("Failed to change aspect ratio", 2000)

    def take_screenshot(self):
        """Take a screenshot of the current frame"""
        if self.media_player.is_playing():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshots_dir = os.path.join(os.path.expanduser("~"), "Pictures", "Media Player Screenshots")
            os.makedirs(screenshots_dir, exist_ok=True)
            
            filename = os.path.join(screenshots_dir, f"screenshot_{timestamp}.png")
            self.media_player.video_take_snapshot(0, filename, 0, 0)
            self.status_bar.showMessage(f"Screenshot saved: {filename}", 3000)

    def set_point_a(self):
        """Set point A for A-B repeat"""
        if self.media_player.is_playing():
            self.point_a = self.media_player.get_time()
            self.point_a_button.setStyleSheet("background-color: #ff5555;")
            self.status_bar.showMessage("Point A set", 1000)

    def set_point_b(self):
        """Set point B for A-B repeat"""
        if self.media_player.is_playing() and hasattr(self, 'point_a'):
            self.point_b = self.media_player.get_time()
            self.point_b_button.setStyleSheet("background-color: #ff5555;")
            self.ab_repeat_timer.start(100)  # Check every 100ms
            self.status_bar.showMessage("A-B repeat enabled", 1000)

    def check_ab_repeat(self):
        """Check if we need to loop back to point A"""
        if hasattr(self, 'point_a') and hasattr(self, 'point_b'):
            current_time = self.media_player.get_time()
            if current_time > self.point_b:
                self.media_player.set_time(self.point_a)

    def reset_ab_repeat(self):
        """Reset A-B repeat points"""
        if hasattr(self, 'point_a'):
            delattr(self, 'point_a')
        if hasattr(self, 'point_b'):
            delattr(self, 'point_b')
        self.point_a_button.setStyleSheet("")
        self.point_b_button.setStyleSheet("")
        self.ab_repeat_timer.stop()
        self.status_bar.showMessage("A-B repeat disabled", 1000)

    def play_url(self, url):
        """Play media from URL (YouTube or other streaming sites)"""
        try:
            # Check if it's a YouTube URL
            if self.is_youtube_url(url):
                self.play_youtube(url)
            else:
                # Handle other streaming URLs
                self.play_stream(url)
                
            self.status_bar.showMessage(f"Playing online content", 2000)
        except Exception as e:
            print(f"Error playing URL: {e}")
            self.status_bar.showMessage("Failed to play online content", 2000)

    def is_youtube_url(self, url):
        """Check if the URL is a YouTube URL"""
        youtube_regex = (
            r'(https?://)?(www\.)?'
            r'(youtube|youtu|youtube-nocookie)\.(com|be)/'
            r'(watch\?v=|embed/|v/|.+\?v=)?([^&=%\?]{11})'
        )
        return bool(re.match(youtube_regex, url))

    def play_youtube(self, url):
        """Play YouTube video"""
        try:
            video = pafy.new(url)
            best = video.getbest()
            media = self.instance.media_new(best.url)
            self.media_player.set_media(media)
            self.media_player.play()
            self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            
            # Add to playlist
            self.playlist.append(url)
            self.playlist_widget.addItem(f"🎬 {video.title}")
            self.current_index = len(self.playlist) - 1
        except Exception as e:
            print(f"YouTube playback error: {e}")
            self.status_bar.showMessage("Failed to play YouTube video", 2000)

    def play_stream(self, url):
        """Play other streaming content"""
        try:
            # Configure yt-dlp
            ydl_opts = {
                'format': 'best',
                'quiet': True,
                'no_warnings': True
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                stream_url = info['url']
                
                media = self.instance.media_new(stream_url)
                self.media_player.set_media(media)
                self.media_player.play()
                self.play_button.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
                
                # Add to playlist
                self.playlist.append(url)
                self.playlist_widget.addItem(f"🎬 {info.get('title', url)}")
                self.current_index = len(self.playlist) - 1
        except Exception as e:
            print(f"Stream playback error: {e}")
            self.status_bar.showMessage("Failed to play stream", 2000)

    def update_effect(self, effect, value, value_label):
        """Update video effect and value label"""
        try:
            normalized_value = value / 100.0
            if effect == 'hue':
                normalized_value = value  # Hue uses degrees (0-360)
            
            self.video_filters[effect] = normalized_value
            value_label.setText(str(value))
            self.apply_video_filters()
        except Exception as e:
            print(f"Error updating {effect}: {e}")

    def reset_effect(self, current_tab):
        """Reset current effect to default"""
        try:
            effect = current_tab.objectName().replace('_slider', '')
            if effect in self.effect_sliders:
                slider, _, _, _, default = self.effect_sliders[effect]
                slider.setValue(default)
        except Exception as e:
            print(f"Error resetting effect: {e}")

    def reset_all_effects(self):
        """Reset all effects to default values"""
        try:
            for effect, (slider, _, _, default) in self.effect_sliders.items():
                slider.setValue(default)
            self.presets_combo.setCurrentText("Default")
        except Exception as e:
            print(f"Error resetting all effects: {e}")

    def apply_preset(self, preset_name):
        """Apply predefined effect presets"""
        presets = {
            "Default": {
                'brightness': 100,
                'contrast': 100,
                'hue': 180,
                'saturation': 100,
                'gamma': 100,
                'sharpness': 50
            },
            "Cinema": {
                'brightness': 90,
                'contrast': 120,
                'hue': 180,
                'saturation': 110,
                'gamma': 95,
                'sharpness': 60
            },
            "Vivid": {
                'brightness': 110,
                'contrast': 130,
                'hue': 180,
                'saturation': 150,
                'gamma': 105,
                'sharpness': 70
            },
            "Warm": {
                'brightness': 105,
                'contrast': 110,
                'hue': 190,
                'saturation': 120,
                'gamma': 95,
                'sharpness': 50
            },
            "Cool": {
                'brightness': 105,
                'contrast': 110,
                'hue': 170,
                'saturation': 120,
                'gamma': 95,
                'sharpness': 50
            },
            "Black & White": {
                'brightness': 100,
                'contrast': 120,
                'hue': 180,
                'saturation': 0,
                'gamma': 100,
                'sharpness': 60
            }
        }
        
        try:
            if preset_name in presets:
                preset = presets[preset_name]
                for effect, value in preset.items():
                    if effect in self.effect_sliders:
                        self.effect_sliders[effect][0].setValue(value)
        except Exception as e:
            print(f"Error applying preset {preset_name}: {e}")

    def toggle_equalizer(self, state):
        """Enable or disable the equalizer"""
        if state:
            self.media_player.set_equalizer(self.equalizer)
        else:
            self.media_player.set_equalizer(None)

    def update_preamp(self, value):
        """Update preamp value"""
        self.equalizer.set_preamp(value)
        self.preamp_value.setText(f"{value} dB")
        if self.eq_enabled.isChecked():
            self.media_player.set_equalizer(self.equalizer)

    def update_band(self, band, value):
        """Update equalizer band"""
        self.equalizer.set_amp_at_index(value, band)
        self.band_sliders[band][1].setText(f"{value} dB")
        if self.eq_enabled.isChecked():
            self.media_player.set_equalizer(self.equalizer)

    def reset_equalizer(self):
        """Reset equalizer to flat response"""
        self.preamp_slider.setValue(0)
        for slider, _ in self.band_sliders:
            slider.setValue(0)
        self.eq_presets.setCurrentText("Flat")

    def apply_eq_preset(self, preset_name):
        """Apply equalizer preset"""
        presets = {
            "Flat": [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            "Classical": [0, 0, 0, 0, 0, 0, -7, -7, -7, -9],
            "Club": [0, 0, 8, 5, 5, 5, 3, 0, 0, 0],
            "Dance": [9, 7, 2, 0, 0, -5, -7, -7, 0, 0],
            "Full Bass": [8, 9, 9, 5, 1, -4, -8, -10, -11, -11],
            "Full Bass & Treble": [7, 5, 0, -7, -4, 1, 8, 11, 12, 12],
            "Full Treble": [-9, -9, -9, -4, 2, 11, 16, 16, 16, 16],
            "Headphones": [4, 11, 5, -3, -2, 1, 4, 9, 12, 14],
            "Large Hall": [10, 10, 5, 5, 0, -4, -4, -4, 0, 0],
            "Live": [-4, 0, 4, 5, 5, 5, 4, 2, 2, 2],
            "Party": [7, 7, 0, 0, 0, 0, 0, 0, 7, 7],
            "Pop": [-1, 4, 7, 8, 5, 0, -2, -2, -1, -1],
            "Reggae": [0, 0, 0, -5, 0, 6, 6, 0, 0, 0],
            "Rock": [8, 4, -5, -8, -3, 4, 8, 11, 11, 11],
            "Ska": [-2, -4, -4, 0, 4, 5, 8, 9, 11, 9],
            "Soft": [4, 1, 0, -2, 0, 4, 8, 9, 11, 12],
            "Soft Rock": [4, 4, 2, 0, -4, -5, -3, 0, 2, 8],
            "Techno": [8, 5, 0, -5, -4, 0, 8, 9, 9, 8]
        }
        
        if preset_name in presets:
            values = presets[preset_name]
            for i, value in enumerate(values):
                self.band_sliders[i][0].setValue(value)

    def toggle_url_input(self, checked):
        """Toggle URL input visibility"""
        if checked:
            self.url_widget.show()
            self.url_input.setFocus()
        else:
            self.url_widget.hide()

    def change_playback_speed(self, speed_str):
        """Change media playback speed based on the combo box selection"""
        try:
            speed = float(speed_str.replace("x", ""))
            self.media_player.set_rate(speed)
            self.speed_label.setText(f"Speed: {speed_str}")
        except Exception as e:
            print(f"Error changing playback speed: {e}")
            self.status_bar.showMessage("Failed to change playback speed", 2000)

    def update_ad_settings(self):
        """Update Google AdSense settings"""
        pub_id = self.publisher_id.text()
        slot_id = self.ad_slot_id.text()
        
        if pub_id and slot_id:
            self.update_ad_html(pub_id, slot_id)
            QMessageBox.information(self, "Success", "Ad settings updated successfully!")
        else:
            QMessageBox.warning(self, "Error", "Please enter both Publisher ID and Ad Slot ID")

    def update_ad_html(self, pub_id=None, slot_id=None):
        """Update the ad HTML content with AdSense support"""
        publisher_id = pub_id or "pub-9105010442621690"
        
        ad_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <script async 
                src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-{publisher_id}"
                crossorigin="anonymous">
            </script>
            <style>
                body {{ 
                    margin: 0; 
                    padding: 0;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    min-height: 100vh;
                }}
                .ad-container {{ 
                    width: 100%;
                    max-width: 970px;
                    margin: auto;
                }}
            </style>
        </head>
        <body>
            <div class="ad-container">
                <!-- Horizontal Ad -->
                <ins class="adsbygoogle"
                    style="display:block"
                    data-ad-client="ca-{publisher_id}"
                    data-ad-slot="{slot_id or '8337557275'}"
                    data-ad-format="auto"
                    data-full-width-responsive="true"></ins>
                <script>
                    (adsbygoogle = window.adsbygoogle || []).push({{}});
                </script>
            </div>
            <!-- Vertical Ad -->
            <div class="ad-container">
                <ins class="adsbygoogle"
                    style="display:block"
                    data-ad-client="ca-{publisher_id}"
                    data-ad-slot="{slot_id or '3245544512'}"
                    data-ad-format="vertical"
                    data-full-width-responsive="false"></ins>
                <script>
                    (adsbygoogle = window.adsbygoogle || []).push({{}});
                </script>
            </div>
        </body>
        </html>
        """
        
        # Set default background color based on theme
        background_color = "#121212" if self.is_dark_theme else "#f5f5f5"
        self.ad_view.setStyleSheet(f"background-color: {background_color};")
        
        # Load the ad content
        self.ad_view.setHtml(ad_html, QUrl("https://www.google.com/adsense"))

    def refresh_ad(self):
        """Refresh the current advertisement"""
        self.update_ad_html()
        self.track_ad_view()

    def track_ad_view(self):
        """Track ad view and update earnings with 40% revenue share"""
        self.ad_views += 1
        total_earning = self.cpm_rate / 1000  # Convert CPM to per-view
        user_share = total_earning * 0.4  # Calculate 40% user share
        self.ad_earnings += user_share  # Add only user's share to earnings
        self.update_ad_stats()

    def update_ad_stats(self):
        """Update the ad statistics display with revenue share info"""
        self.earnings_label.setText(f"${self.ad_earnings:.2f} (40% share)")
        self.views_label.setText(str(self.ad_views))
        self.cpm_label.setText(f"${self.cpm_rate:.2f}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    player = MediaPlayer()
    player.show()
    sys.exit(app.exec_())

