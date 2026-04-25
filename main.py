import sys
import os
from dotenv import load_dotenv

load_dotenv()

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QProgressBar, QSlider, 
                             QTextEdit, QFrame, QGroupBox, QSpinBox, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from narrator import process_narrator_batch, generate_scripts_from_prompt

class DragDropLabel(QLabel):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        self.setAcceptDrops(True)
        self.setStyleSheet("""
            QLabel {
                border: 2px dashed #aaa;
                border-radius: 5px;
                padding: 20px;
                background-color: #f0f0f0;
                color: #555;
            }
            QLabel:hover {
                background-color: #e0e0e0;
            }
        """)
        self.folder_path = None
        self.default_text = text

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [u.toLocalFile() for u in event.mimeData().urls()]
        # Check if first item is a folder
        if files and os.path.isdir(files[0]):
            self.folder_path = files[0]
            self.setText(f"Selected: {os.path.basename(self.folder_path)}")
            self.setStyleSheet("QLabel { border: 2px solid #4CAF50; background-color: #E8F5E9; }")
        else:
            self.setText("Please drop a FOLDER, not files.")

class WorkerThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal()
    
    def __init__(self, prompt_text, num_videos, gameplay_dir, output_dir, speed_factor=1.0):
        super().__init__()
        self.prompt_text = prompt_text
        self.num_videos = num_videos
        self.gameplay_dir = gameplay_dir
        self.output_dir = output_dir
        self.speed_factor = speed_factor

    def run(self):
        # 1. Generate scripts using Gemini API
        self.log_message("Requesting scripts from Gemini API...")
        scripts = generate_scripts_from_prompt(
            prompt_text=self.prompt_text,
            num_videos=self.num_videos,
            logger=self.log_message
        )
        
        if not scripts:
            self.log_message("Failed to generate scripts. Aborting.")
            self.finished_signal.emit()
            return

        # 2. Process Narrator Batch
        self.log_message(f"Starting Video Generation for {len(scripts)} scripts...")
        process_narrator_batch(
            scripts=scripts,
            gameplay_dir=self.gameplay_dir,
            output_dir=self.output_dir,
            use_openai=bool(os.getenv("OPENAI_API_KEY")),
            api_key=os.getenv("OPENAI_API_KEY"),
            speed_factor=self.speed_factor,
            logger=self.log_message
        )
            
        self.finished_signal.emit()

    def log_message(self, message):
        self.progress_signal.emit(message)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Narrator Automator")
        self.resize(800, 900)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Configuration Title
        title = QLabel("Narrator Video Automation")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 10px;")
        main_layout.addWidget(title)
        
        # Markdown Prompt Group
        prompt_group = QGroupBox("1. Markdown Configuration Prompt")
        prompt_layout = QVBoxLayout()
        self.script_input = QTextEdit()
        default_prompt = (
            "Create a highly engaging script for a short-form video (TikTok/Shorts).\n"
            "Topic: Fascinating psychology facts.\n"
            "Tone: Energetic, hook the viewer in the first 3 seconds.\n"
            "Constraints: No emojis, plain text only, keep it under 60 words.\n"
            "Formatting: Put each sentence or phrase on its own distinct line."
        )
        self.script_input.setPlainText(default_prompt)
        prompt_layout.addWidget(self.script_input)
        prompt_group.setLayout(prompt_layout)
        main_layout.addWidget(prompt_group, stretch=1)
        
        # Settings Group
        settings_group = QGroupBox("2. Generation Settings")
        settings_layout = QVBoxLayout()
        
        # Number of Videos
        count_layout = QHBoxLayout()
        count_layout.addWidget(QLabel("Number of Videos to Generate:"))
        self.video_count_spinner = QSpinBox()
        self.video_count_spinner.setRange(1, 50)
        self.video_count_spinner.setValue(1)
        count_layout.addWidget(self.video_count_spinner)
        count_layout.addStretch()
        settings_layout.addLayout(count_layout)
        
        # Speed Control
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Narration Speed:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(25, 300) # 0.25x to 3.0x
        self.speed_slider.setValue(100)
        self.speed_label = QLabel("1.00x")
        self.speed_slider.valueChanged.connect(lambda v: self.speed_label.setText(f"{v/100:.2f}x"))
        speed_layout.addWidget(self.speed_slider)
        speed_layout.addWidget(self.speed_label)
        settings_layout.addLayout(speed_layout)
        
        settings_group.setLayout(settings_layout)
        main_layout.addWidget(settings_group)
        
        # Gameplay Source Group
        source_group = QGroupBox("3. Gameplay Background")
        source_layout = QVBoxLayout()
        self.drop_gameplay = DragDropLabel("Drop Gameplay Folder (Background)\n[Source]")
        self.drop_gameplay.setMinimumHeight(120)
        source_layout.addWidget(self.drop_gameplay)
        source_group.setLayout(source_layout)
        main_layout.addWidget(source_group)
        
        # Start Button
        self.start_btn = QPushButton("Start Auto-Generation Batch")
        self.start_btn.setMinimumHeight(60)
        self.start_btn.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold; font-size: 16px;")
        self.start_btn.clicked.connect(self.start_processing)
        main_layout.addWidget(self.start_btn)
        
        # Log Area
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(200)
        main_layout.addWidget(self.log_area)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)
        
        self.worker = None

    def log(self, message):
        self.log_area.append(message)
        sb = self.log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def toggle_ui(self, enabled):
        self.start_btn.setEnabled(enabled)
        self.script_input.setEnabled(enabled)
        self.video_count_spinner.setEnabled(enabled)
        self.speed_slider.setEnabled(enabled)
        if enabled:
            self.progress_bar.hide()
        else:
            self.progress_bar.show()

    def start_processing(self):
        gameplay_dir = self.drop_gameplay.folder_path
        if not gameplay_dir:
            self.log("Error: Please drop a gameplay folder.")
            return
            
        prompt = self.script_input.toPlainText().strip()
        if not prompt:
            self.log("Error: Please provide a markdown prompt.")
            return
            
        if not os.getenv("GEMINI_API_KEY"):
             self.log("Warning: GEMINI_API_KEY environment variable is not set. It is required to generate scripts via the Gemini API.")
             
        num_videos = self.video_count_spinner.value()
        output_dir = os.path.join(os.path.dirname(gameplay_dir), "Narrated_Cuts")
        speed_factor = self.speed_slider.value() / 100.0
        
        self.log(f"Starting Job ({num_videos} videos), Speed: {speed_factor}x...\nOutput will be: {output_dir}")
        self.toggle_ui(False)
        
        self.worker = WorkerThread(
            prompt_text=prompt,
            num_videos=num_videos,
            gameplay_dir=gameplay_dir,
            output_dir=output_dir,
            speed_factor=speed_factor
        )
        self.worker.progress_signal.connect(self.log)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.start()

    def processing_finished(self):
        self.log("Batch processing finished!")
        self.toggle_ui(True)
        self.worker = None

if __name__ == "__main__":
    import youtube_uploader
    import glob
    
    # Initialize YouTube Auth before starting the main loop so it doesn't block background jobs later
    if glob.glob('client_secret_*.json') or os.path.exists('token.json'):
         print("Initializing YouTube Authentication...")
         youtube_uploader.initialize_youtube_auth(logger=print)
         
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
