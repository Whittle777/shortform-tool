import sys
import os
import csv
from dotenv import load_dotenv

load_dotenv()

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QPushButton, QProgressBar, QFileDialog, QSlider, QComboBox, 
                             QTextEdit, QFrame, QGroupBox, QTabWidget, QMessageBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from processor import process_batch
from processor import process_batch
from narrator import process_narrator_batch
from hook_mode import process_hook_batch

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
    
    def __init__(self, mode, **kwargs):
        super().__init__()
        self.mode = mode
        self.kwargs = kwargs

    def run(self):
        if self.mode == 'split':
            process_batch(
                self.kwargs['source_a'], 
                self.kwargs['source_b'], 
                self.kwargs['output_dir'], 
                self.kwargs['split_ratio'], 
                self.kwargs['max_duration'], 
                logger=self.log_message
            )
        elif self.mode == 'narrator':
            process_narrator_batch(
                self.kwargs['scripts'],
                self.kwargs['gameplay_dir'],
                self.kwargs['output_dir'],
                use_openai=bool(os.getenv("OPENAI_API_KEY")),
                api_key=os.getenv("OPENAI_API_KEY"),
                speed_factor=self.kwargs.get('speed_factor', 1.0),
                logger=self.log_message
            )
        elif self.mode == 'hook':
            process_hook_batch(
                self.kwargs['viral_dir'],
                self.kwargs['gameplay_dir'],
                self.kwargs['output_dir'],
                hook_duration=self.kwargs.get('hook_duration', 5.0),
                logger=self.log_message
            )
            
        self.finished_signal.emit()

    def log_message(self, message):
        self.progress_signal.emit(message)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Pro Video Automation Tool")
        self.resize(700, 800)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        
        # Tabs
        self.tabs = QTabWidget()
        self.tab_split = QWidget()
        self.tab_narrator = QWidget()
        
        self.tab_hook = QWidget()
        
        self.tabs.addTab(self.tab_split, "Split Screen Mode")
        self.tabs.addTab(self.tab_narrator, "Narrator Mode")
        self.tabs.addTab(self.tab_hook, "Viral Hook Mode")
        
        main_layout.addWidget(self.tabs)
        
        # Setup Tabs
        self.setup_split_tab()
        self.setup_narrator_tab()
        self.setup_hook_tab()
        
        # Shared Log Area (Bottom)
        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)
        self.log_area.setMaximumHeight(200)
        main_layout.addWidget(self.log_area)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.hide()
        main_layout.addWidget(self.progress_bar)
        
        self.worker = None

    def setup_split_tab(self):
        layout = QVBoxLayout()
        
        # Zones
        dnd_layout = QHBoxLayout()
        self.drop_a = DragDropLabel("Drop Viral Clips Folder (Top)\n[Source A]")
        self.drop_b = DragDropLabel("Drop Gameplay Folder (Bottom)\n[Source B]")
        dnd_layout.addWidget(self.drop_a)
        dnd_layout.addWidget(self.drop_b)
        layout.addLayout(dnd_layout)
        
        # Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        
        ratio_layout = QHBoxLayout()
        ratio_layout.addWidget(QLabel("Split Ratio (Top Height %):"))
        self.ratio_slider = QSlider(Qt.Orientation.Horizontal)
        self.ratio_slider.setRange(10, 90)
        self.ratio_slider.setValue(50)
        self.ratio_label = QLabel("50%")
        self.ratio_slider.valueChanged.connect(lambda v: self.ratio_label.setText(f"{v}%"))
        ratio_layout.addWidget(self.ratio_slider)
        ratio_layout.addWidget(self.ratio_label)
        settings_layout.addLayout(ratio_layout)
        
        duration_layout = QHBoxLayout()
        duration_layout.addWidget(QLabel("Max Duration:"))
        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["Shortest Video", "15 Seconds", "30 Seconds", "60 Seconds"])
        duration_layout.addWidget(self.duration_combo)
        settings_layout.addLayout(duration_layout)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Start
        self.start_split_btn = QPushButton("Start Split-Screen Batch")
        self.start_split_btn.setMinimumHeight(50)
        self.start_split_btn.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold;")
        self.start_split_btn.clicked.connect(self.start_split_processing)
        layout.addWidget(self.start_split_btn)
        
        self.tab_split.setLayout(layout)

    def setup_narrator_tab(self):
        layout = QVBoxLayout()
        
        # Input Script
        layout.addWidget(QLabel("Enter Script (One video per run) OR Import CSV:"))
        self.script_input = QTextEdit()
        self.script_input.setPlaceholderText("Type your script here for a single video...")
        layout.addWidget(self.script_input)
        
        # CSV Import
        self.csv_btn = QPushButton("Import Scripts from CSV")
        self.csv_btn.clicked.connect(self.import_csv)
        layout.addWidget(self.csv_btn)
        
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
        layout.addLayout(speed_layout)
        
        # Gameplay Source
        self.drop_gameplay_narrator = DragDropLabel("Drop Gameplay Folder (Background)\n[Source]")
        self.drop_gameplay_narrator.setMinimumHeight(150)
        layout.addWidget(self.drop_gameplay_narrator)
        
        # Start
        self.start_narrator_btn = QPushButton("Start Narrator Batch")
        self.start_narrator_btn.setMinimumHeight(50)
        self.start_narrator_btn.setStyleSheet("background-color: #9C27B0; color: white; font-weight: bold;")
        self.start_narrator_btn.clicked.connect(self.start_narrator_processing)
        layout.addWidget(self.start_narrator_btn)
        
        self.tab_narrator.setLayout(layout)
        
        self.csv_scripts = []

    def setup_hook_tab(self):
        layout = QVBoxLayout()
        
        # Zones
        dnd_layout = QHBoxLayout()
        self.drop_viral_hook = DragDropLabel("Drop Viral Folder (Hook Source)\n[Source A]")
        self.drop_gameplay_hook = DragDropLabel("Drop Gameplay Folder (Body)\n[Source B]")
        dnd_layout.addWidget(self.drop_viral_hook)
        dnd_layout.addWidget(self.drop_gameplay_hook)
        layout.addLayout(dnd_layout)
        
        # Settings
        settings_group = QGroupBox("Settings")
        settings_layout = QVBoxLayout()
        
        hook_layout = QHBoxLayout()
        hook_layout.addWidget(QLabel("Hook Seg Duration (s):"))
        self.hook_slider = QSlider(Qt.Orientation.Horizontal)
        self.hook_slider.setRange(1, 10) # 1s to 10s
        self.hook_slider.setValue(5)
        self.hook_label = QLabel("5s")
        self.hook_slider.valueChanged.connect(lambda v: self.hook_label.setText(f"{v}s"))
        hook_layout.addWidget(self.hook_slider)
        hook_layout.addWidget(self.hook_label)
        settings_layout.addLayout(hook_layout)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Start
        self.start_hook_btn = QPushButton("Start Viral Hook Batch")
        self.start_hook_btn.setMinimumHeight(50)
        self.start_hook_btn.setStyleSheet("background-color: #FF5722; color: white; font-weight: bold;")
        self.start_hook_btn.clicked.connect(self.start_hook_processing)
        layout.addWidget(self.start_hook_btn)
        
        self.tab_hook.setLayout(layout)

    def log(self, message):
        self.log_area.append(message)
        sb = self.log_area.verticalScrollBar()
        sb.setValue(sb.maximum())

    def import_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open CSV", "", "CSV Files (*.csv)")
        if path:
            try:
                scripts = []
                with open(path, 'r', encoding='utf-8') as f:
                    reader = csv.reader(f)
                    for row in reader:
                        if row: scripts.append(row[0].strip().strip('"').strip("'")) # Assume first column
                self.csv_scripts = scripts
                self.log(f"Loaded {len(scripts)} scripts from CSV.")
                self.script_input.setPlainText(f"[Loaded {len(scripts)} scripts from CSV. Manual input ignored.]")
                self.script_input.setDisabled(True)
            except Exception as e:
                self.log(f"Error reading CSV: {e}")

    def toggle_ui(self, enabled):
        self.start_split_btn.setEnabled(enabled)
        self.start_narrator_btn.setEnabled(enabled)
        self.start_hook_btn.setEnabled(enabled)
        if enabled:
            self.progress_bar.hide()
        else:
            self.progress_bar.show()

    def start_split_processing(self):
        source_a = self.drop_a.folder_path
        source_b = self.drop_b.folder_path
        
        if not source_a or not source_b:
            self.log("Error: Please select both source folders.")
            return

        output_dir = os.path.join(os.path.dirname(source_a), "Finished_Cuts")
        split_ratio = self.ratio_slider.value()
        
        duration_text = self.duration_combo.currentText()
        if "Seconds" in duration_text:
            max_duration = duration_text.split(" ")[0]
        else:
            max_duration = "shortest"

        self.log(f"Starting Split Batch...\nOutput: {output_dir}")
        self.toggle_ui(False)
        
        self.worker = WorkerThread(
            mode='split',
            source_a=source_a,
            source_b=source_b,
            output_dir=output_dir,
            split_ratio=split_ratio,
            max_duration=max_duration
        )
        self.worker.progress_signal.connect(self.log)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.start()

    def start_narrator_processing(self):
        gameplay_dir = self.drop_gameplay_narrator.folder_path
        if not gameplay_dir:
            self.log("Error: Please drop a gameplay folder.")
            return
            
        # Determine scripts
        scripts = []
        if self.csv_scripts:
            scripts = self.csv_scripts
        else:
            text = self.script_input.toPlainText().strip()
            if text:
                scripts = [text]
        
        if not scripts:
            self.log("Error: No scripts found. Type text or load CSV.")
            return
            
        output_dir = os.path.join(os.path.dirname(gameplay_dir), "Narrated_Cuts")
        
        speed_factor = self.speed_slider.value() / 100.0
        
        self.log(f"Starting Narrator Batch ({len(scripts)} videos) at {speed_factor}x speed...\nOutput: {output_dir}")
        self.toggle_ui(False)
        
        self.worker = WorkerThread(
            mode='narrator',
            scripts=scripts,
            gameplay_dir=gameplay_dir,
            output_dir=output_dir,
            speed_factor=speed_factor
        )
        self.worker.progress_signal.connect(self.log)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.start()

    def start_hook_processing(self):
        viral_dir = self.drop_viral_hook.folder_path
        gameplay_dir = self.drop_gameplay_hook.folder_path
        
        if not viral_dir or not gameplay_dir:
            self.log("Error: Please select both source folders.")
            return

        output_dir = os.path.join(os.path.dirname(viral_dir), "Hook_Cuts")
        hook_duration = self.hook_slider.value()

        self.log(f"Starting Hook Batch...\nOutput: {output_dir}")
        self.toggle_ui(False)
        
        self.worker = WorkerThread(
            mode='hook',
            viral_dir=viral_dir,
            gameplay_dir=gameplay_dir,
            output_dir=output_dir,
            hook_duration=hook_duration
        )
        self.worker.progress_signal.connect(self.log)
        self.worker.finished_signal.connect(self.processing_finished)
        self.worker.start()

    def processing_finished(self):
        self.log("Processing finished!")
        self.toggle_ui(True)
        self.worker = None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
