import sys
import json
import os
from datetime import datetime, timedelta
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
import sqlite3
import traceback

# Database Manager
class DatabaseManager:
    def __init__(self):
        self.db_path = "school_erp.db"
        self.init_database()

    def ensure_valid_database(self):
        """Check if file is a valid SQLite DB, else recreate it"""
        import os, sqlite3
        if os.path.exists(self.db_path):
            try:
                # Try reading the first bytes to verify SQLite signature
                with open(self.db_path, "rb") as f:
                    header = f.read(16)
                if not header.startswith(b"SQLite format 3"):
                    raise sqlite3.DatabaseError("Not a valid SQLite file")
                # Also check if connection works
                conn = sqlite3.connect(self.db_path)
                conn.execute("PRAGMA integrity_check;")
                conn.close()
            except Exception:
                print("⚠️ Invalid or corrupted database. Recreating new one...")
                os.remove(self.db_path)
    
    def get_connection(self):
        return sqlite3.connect(self.db_path)
    
    def init_database(self):
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Settings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        ''')
        
        # Initialize default settings
        cursor.execute("INSERT OR IGNORE INTO settings VALUES ('school_name', 'School ERP')")
        cursor.execute("INSERT OR IGNORE INTO settings VALUES ('school_address', '')")
        cursor.execute("INSERT OR IGNORE INTO settings VALUES ('school_email', '')")
        cursor.execute("INSERT OR IGNORE INTO settings VALUES ('remember_me', 'false')")
        cursor.execute("INSERT OR IGNORE INTO settings VALUES ('saved_username', '')")
        cursor.execute("INSERT OR IGNORE INTO settings VALUES ('saved_password', '')")
        
        # Students table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_number TEXT UNIQUE,
                full_name TEXT,
                roll_number TEXT,
                class TEXT,
                section TEXT,
                parent_name TEXT,
                gender TEXT,
                dob TEXT,
                parent_number TEXT,
                address TEXT,
                session TEXT
            )
        ''')
        
        # Staff table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id TEXT UNIQUE,
                name TEXT,
                phone TEXT,
                email TEXT,
                designation TEXT,
                qualification TEXT,
                department TEXT,
                joining_date TEXT,
                salary REAL,
                address TEXT,
                session TEXT
            )
        ''')
        
        # Attendance table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS attendance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_number TEXT,
                class TEXT,
                section TEXT,
                month TEXT,
                year TEXT,
                working_days INTEGER,
                days_present INTEGER,
                percentage REAL,
                session TEXT,
                FOREIGN KEY (student_number) REFERENCES students(student_number)
            )
        ''')
        
        # Salary payments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS salary_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id TEXT,
                staff_name TEXT,
                amount REAL,
                payment_date TEXT,
                month TEXT,
                year TEXT,
                session TEXT,
                FOREIGN KEY (staff_id) REFERENCES staff(staff_id)
            )
        ''')
        
        # Fee payments table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS fee_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                receipt_number TEXT UNIQUE,
                student_number TEXT,
                student_name TEXT,
                class TEXT,
                section TEXT,
                parent_name TEXT,
                months TEXT,
                payment_date TEXT,
                tuition_fee REAL,
                lab_fee REAL,
                sport_fee REAL,
                computer_fee REAL,
                maintenance_fee REAL,
                exam_fee REAL,
                late_fee REAL,
                total_amount REAL,
                payment_mode TEXT,
                payment_status TEXT,
                session TEXT,
                FOREIGN KEY (student_number) REFERENCES students(student_number)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_setting(self, key):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def set_setting(self, key, value):
        conn = self.get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()

# Student Selection Popup Dialog
class StudentSelectionDialog(QDialog):
    def __init__(self, parent, db, current_session):
        super().__init__(parent)
        self.db = db
        self.current_session = current_session
        self.selected_student = None
        self.init_ui()
        self.load_students()
    
    def init_ui(self):
        self.setWindowTitle("Select Student")
        self.setModal(True)
        self.setFixedSize(800, 600)
        
        # Center on parent
        if self.parent():
            parent_geo = self.parent().geometry()
            x = parent_geo.x() + (parent_geo.width() - self.width()) // 2
            y = parent_geo.y() + (parent_geo.height() - self.height()) // 2
            self.move(x, y)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # Title
        title = QLabel("Select Student for Fee Collection")
        title.setStyleSheet("""
            font-size: 18px;
            font-weight: bold;
            color: #667eea;
            padding: 10px;
        """)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Search bar
        search_layout = QHBoxLayout()
        search_label = QLabel("🔍 Search:")
        search_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        search_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Type student name, number, class, or parent name...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background: white;
                border: 2px solid #667eea;
                border-radius: 8px;
                padding: 10px;
                font-size: 15px;
            }
            QLineEdit:focus {
                border: 2px solid #5a67d8;
            }
        """)
        self.search_input.textChanged.connect(self.filter_students)
        search_layout.addWidget(self.search_input)
        
        layout.addLayout(search_layout)
        
        # Students table
        self.students_table = QTableWidget()
        self.students_table.setColumnCount(5)
        self.students_table.setHorizontalHeaderLabels([
            "Student Number", "Name", "Class", "Section", "Parent Name"
        ])
        
        # Set column widths
        header = self.students_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.Stretch)
        
        self.students_table.setAlternatingRowColors(True)
        self.students_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.students_table.setSelectionMode(QAbstractItemView.SingleSelection)
        
        self.students_table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 12px 8px;
                border-bottom: 1px solid #f0f0f0;
            }
            QTableWidget::item:selected {
                background: #667eea;
                color: white;
            }
            QTableWidget::item:hover {
                background: #f0f4ff;
            }
            QHeaderView::section {
                background: #667eea;
                color: white;
                padding: 12px 8px;
                border: none;
                font-weight: bold;
                font-size: 15px;
            }
        """)
        
        # Double click to select
        self.students_table.doubleClicked.connect(self.select_student)
        
        layout.addWidget(self.students_table)
        
        # Info label
        self.info_label = QLabel("Double-click on a student to select, or use the Select button below.")
        self.info_label.setStyleSheet("""
            color: #666;
            font-style: italic;
            padding: 5px;
        """)
        self.info_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.info_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        select_btn = QPushButton("✓ Select Student")
        select_btn.setStyleSheet("""
            QPushButton {
                background: #667eea;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 15px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: #5a67d8;
            }
            QPushButton:pressed {
                background: #4c51bf;
            }
        """)
        select_btn.clicked.connect(self.select_student)
        button_layout.addWidget(select_btn)
        
        cancel_btn = QPushButton("✗ Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background: #6c757d;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 15px;
                min-width: 120px;
            }
            QPushButton:hover {
                background: #5a6268;
            }
            QPushButton:pressed {
                background: #495057;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        layout.addLayout(button_layout)
    
    def load_students(self):
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT student_number, full_name, class, section, parent_name 
                FROM students 
                WHERE session = ?
                ORDER BY class, section, full_name
            """, (self.current_session,))
            
            students = cursor.fetchall()
            conn.close()
            
            self.all_students = students
            self.display_students(students)
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load students:\n{str(e)}")
    
    def display_students(self, students):
        self.students_table.setRowCount(len(students))
        
        for row, student in enumerate(students):
            for col, data in enumerate(student):
                item = QTableWidgetItem(str(data))
                item.setData(Qt.UserRole, student)  # Store full student data
                self.students_table.setItem(row, col, item)
        
        # Update info label
        self.info_label.setText(f"Showing {len(students)} students. Double-click to select.")
    
    def filter_students(self):
        search_text = self.search_input.text().lower().strip()
        
        if not search_text:
            self.display_students(self.all_students)
            return
        
        filtered_students = []
        for student in self.all_students:
            # Search in all fields
            search_fields = [str(field).lower() for field in student]
            if any(search_text in field for field in search_fields):
                filtered_students.append(student)
        
        self.display_students(filtered_students)
    
    def select_student(self):
        current_row = self.students_table.currentRow()
        if current_row >= 0:
            item = self.students_table.item(current_row, 0)
            if item:
                self.selected_student = item.data(Qt.UserRole)
                self.accept()
        else:
            QMessageBox.warning(self, "No Selection", "Please select a student first!")

# Splash Screen
class SplashScreen(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(600, 400)
        
        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        
        self.progress = 0
        self.init_ui()
        
        # Timer for progress
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_progress)
        self.timer.start(30)
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Main container
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 20px;
            }
        """)
        
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(30)
        container_layout.setContentsMargins(40, 40, 40, 40)
        
        # Logo/Icon
        icon_label = QLabel("🏫")
        icon_label.setStyleSheet("font-size: 85px; background: transparent;")
        icon_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(icon_label)
        
        # Title
        title = QLabel("School ERP")
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: white;
            background: transparent;
            font-family: 'Segoe UI', Arial;
        """)
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        # Loading text
        self.loading_label = QLabel("Loading...")
        self.loading_label.setStyleSheet("""
            font-size: 16px;
            color: rgba(255, 255, 255, 0.9);
            background: transparent;
        """)
        self.loading_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(self.loading_label)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 10px;
                background-color: rgba(255, 255, 255, 0.2);
                height: 20px;
                text-align: center;
                color: white;
                font-weight: bold;
            }
            QProgressBar::chunk {
                border-radius: 10px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f093fb, stop:1 #f5576c);
            }
        """)
        self.progress_bar.setMaximum(100)
        container_layout.addWidget(self.progress_bar)
        
        container_layout.addStretch()
        
        # Designer credit
        credit = QLabel("Designed by Harsh Kumar\nwww.brandbaazi.com")
        credit.setStyleSheet("""
            font-size: 16px;
            color: rgba(255, 255, 255, 0.8);
            background: transparent;
        """)
        credit.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(credit)
        
        layout.addWidget(container)
        self.setLayout(layout)
    
    def update_progress(self):
        self.progress += 2
        self.progress_bar.setValue(self.progress)
        
        if self.progress >= 100:
            self.timer.stop()
            self.close()
            self.show_login()
    
    def show_login(self):
        self.login_window = LoginWindow()
        self.login_window.show()
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw shadow
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 20, 20)
        painter.fillPath(path, QColor(0, 0, 0, 100))

# Login Window
class LoginWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.setWindowTitle("School ERP - Login")
        self.setFixedSize(500, 600)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.move((screen.width() - self.width()) // 2, (screen.height() - self.height()) // 2)
        
        self.init_ui()
        self.load_saved_credentials()
    
    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Main container
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                border-radius: 20px;
            }
        """)
        
        container_layout = QVBoxLayout(container)
        container_layout.setSpacing(20)
        container_layout.setContentsMargins(50, 50, 50, 50)
        
        # Close button
        close_btn = QPushButton("×")
        close_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                color: white;
                font-size: 30px;
                border: none;
                padding: 0;
                max-width: 30px;
                max-height: 30px;
            }
            QPushButton:hover {
                color: #ff6b6b;
            }
        """)
        close_btn.clicked.connect(self.close)
        close_layout = QHBoxLayout()
        close_layout.addStretch()
        close_layout.addWidget(close_btn)
        container_layout.addLayout(close_layout)
        
        # Logo
        icon_label = QLabel("🔐")
        icon_label.setStyleSheet("font-size: 40px; background: transparent;")
        icon_label.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(icon_label)
        
        # Title
        title = QLabel("School ERP")
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: white;
            background: transparent;
        """)
        title.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(title)
        
        subtitle = QLabel("Admin Login")
        subtitle.setStyleSheet("""
            font-size: 16px;
            color: rgba(255, 255, 255, 0.8);
            background: transparent;
        """)
        subtitle.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(subtitle)
        
        container_layout.addSpacing(20)
        
        # Username field
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Username")
        self.username_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.9);
                border: none;
                border-radius: 10px;
                padding: 15px;
                font-size: 14px;
                color: #333;
            }
            QLineEdit:focus {
                background: white;
            }
        """)
        container_layout.addWidget(self.username_input)
        
        # Password field
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("Password")
        self.password_input.setEchoMode(QLineEdit.Password)
        self.password_input.setStyleSheet("""
            QLineEdit {
                background: rgba(255, 255, 255, 0.9);
                border: none;
                border-radius: 10px;
                padding: 15px;
                font-size: 14px;
                color: #333;
            }
            QLineEdit:focus {
                background: white;
            }
        """)
        self.password_input.returnPressed.connect(self.login)
        container_layout.addWidget(self.password_input)
        
        # Remember me checkbox
        self.remember_checkbox = QCheckBox("Remember Me")
        self.remember_checkbox.setStyleSheet("""
            QCheckBox {
                color: white;
                background: transparent;
                font-size: 14px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 20px;
                height: 20px;
                border-radius: 5px;
                background: rgba(255, 255, 255, 0.3);
                border: 2px solid white;
            }
            QCheckBox::indicator:checked {
                background: white;
                image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTYiIGhlaWdodD0iMTYiIHZpZXdCb3g9IjAgMCAxNiAxNiIgZmlsbD0ibm9uZSIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj4KPHBhdGggZD0iTTEzLjMzMzMgNEw2IDExLjMzMzNMMi42NjY2NyA4IiBzdHJva2U9IiM2NjdlZWEiIHN0cm9rZS13aWR0aD0iMiIgc3Ryb2tlLWxpbmVjYXA9InJvdW5kIiBzdHJva2UtbGluZWpvaW49InJvdW5kIi8+Cjwvc3ZnPgo=);
            }
        """)
        container_layout.addWidget(self.remember_checkbox)
        
        # Login button
        login_btn = QPushButton("Login")
        login_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f093fb, stop:1 #f5576c);
                color: white;
                border: none;
                border-radius: 7px;
                padding: 15px;
                font-size: 14px;
                font-weight: bold;
                
            }
            QPushButton:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #f5576c, stop:1 #f093fb);
                border-radius: 10px;
                padding: 14px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:pressed {
                padding-top: 17px;
                padding-bottom: 13px;
            }
        """)
        login_btn.clicked.connect(self.login)
        container_layout.addWidget(login_btn)
        
        container_layout.addStretch()
        
        # Footer
        footer = QLabel("www.brandbaazi.com")
        footer.setStyleSheet("""
            font-size: 15px;
            color: rgba(255, 255, 255, 0.7);
            background: transparent;
        """)
        footer.setAlignment(Qt.AlignCenter)
        container_layout.addWidget(footer)
        
        layout.addWidget(container)
        self.setLayout(layout)
    
    def load_saved_credentials(self):
        remember = self.db.get_setting('remember_me')
        if remember == 'true':
            username = self.db.get_setting('saved_username')
            password = self.db.get_setting('saved_password')
            self.username_input.setText(username)
            self.password_input.setText(password)
            self.remember_checkbox.setChecked(True)
    
    def login(self):
        username = self.username_input.text()
        password = self.password_input.text()
        
        if username == "admin" and password == "admin123":
            # Save credentials if remember me is checked
            if self.remember_checkbox.isChecked():
                self.db.set_setting('remember_me', 'true')
                self.db.set_setting('saved_username', username)
                self.db.set_setting('saved_password', password)
            else:
                self.db.set_setting('remember_me', 'false')
                self.db.set_setting('saved_username', '')
                self.db.set_setting('saved_password', '')
            
            self.main_window = MainWindow()
            self.main_window.show()
            self.close()
        else:
            QMessageBox.warning(self, "Login Failed", "Invalid username or password!")
    
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()), 20, 20)
        painter.fillPath(path, QColor(0, 0, 0, 80))

# Main Window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.db = DatabaseManager()
        self.current_session = self.load_last_session()
        self.selected_student_number = None  # ADD THIS LINE

        self.setWindowTitle("School ERP - Management System")
        self.setMinimumSize(1400, 800)
        
        # Center on screen
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(
            (screen.width() - 1400) // 2,
            (screen.height() - 800) // 2,
            1400, 800
        )
        
        self.init_ui()
        
        # Timer for footer clock
        self.timer = QTimer()
        self.timer.timeout.connect(self.update_time)
        self.timer.start(1000)
        self.update_time()
    
        # Timer for dashboard updates
        self.dashboard_timer = QTimer()
        self.dashboard_timer.timeout.connect(self.refresh_home_data)
        self.dashboard_timer.start(5000)  # Update every 5 seconds
        
        # Initial data load
        QTimer.singleShot(500, self.refresh_home_data)
    
    def init_ui(self):
        # Set window style
        self.setStyleSheet("""
            QMainWindow {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #f5f7fa, stop:1 #c3cfe2);
            }
            QCalendarWidget {
                background-color: white !important;
                color: #ed0505 !important;
            }
            QCalendarWidget QToolButton {
                background-color: #667eea !important;
                color: white !important;
            }
            QCalendarWidget QAbstractItemView {
                background-color: white !important;
                color: #ed0505 !important;
                selection-background-color: #667eea !important;
            }
        """)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Sidebar
        self.sidebar = self.create_sidebar()
        main_layout.addWidget(self.sidebar)
        
        # Content area with footer
        content_container = QWidget()
        content_layout = QVBoxLayout(content_container)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        
        # Stacked widget for pages
        self.stack = QStackedWidget()
        content_layout.addWidget(self.stack)
        
        # Add pages
        self.home_page = self.create_home_page()
        self.student_page = self.create_student_page()
        self.attendance_page = self.create_attendance_page()
        self.staff_page = self.create_staff_page()
        self.fees_page = self.create_fees_page()
        self.settings_page = self.create_settings_page()
        
        self.stack.addWidget(self.home_page)
        self.stack.addWidget(self.student_page)
        self.stack.addWidget(self.attendance_page)
        self.stack.addWidget(self.staff_page)
        self.stack.addWidget(self.fees_page)
        self.stack.addWidget(self.settings_page)
        
        # Footer
        self.footer = self.create_footer()
        content_layout.addWidget(self.footer)
        
        main_layout.addWidget(content_container, 1)
    
    def create_sidebar(self):
        sidebar = QFrame()
        sidebar.setFixedWidth(250)
        sidebar.setStyleSheet("""
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #667eea, stop:1 #764ba2);
                border: none;
            }
        """)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        # Logo and title
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setSpacing(5)
        
        logo = QLabel("🏫")
        logo.setStyleSheet("font-size: 40px; background: transparent;")
        logo.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(logo)
        
        title = QLabel("School ERP")
        title.setStyleSheet("""
            font-size: 33px;
            font-weight: bold;
            color: white;
            background: transparent;
        """)
        title.setAlignment(Qt.AlignCenter)
        logo_layout.addWidget(title)
        
        layout.addWidget(logo_container)
        layout.addSpacing(10)
        
        # Session selector
        session_label = QLabel("Current Session:")
        session_label.setStyleSheet("""
            color: rgba(255, 255, 255, 0.9);
            font-size: 16px;
            background: transparent;
        """)
        layout.addWidget(session_label)
        
        self.session_combo = QComboBox()
        sessions = [f"{year}-{str(year+1)[-2:]}" for year in range(2024, 2040)]
        self.session_combo.addItems(sessions)
        self.session_combo.setCurrentText(self.current_session)
        self.session_combo.currentTextChanged.connect(self.change_session)
        self.session_combo.setStyleSheet("""
            QComboBox {
                background: rgba(255, 255, 255, 0.9);
                border: none;
                border-radius: 8px;
                padding: 9px;
                color: #333;
                font-size: 17px;
            }
            QComboBox:hover {
                background: white;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #667eea;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: white;
                border: 1px solid #ddd;
                selection-background-color: #667eea;
                selection-color: white;
            }
        """)
        layout.addWidget(self.session_combo)
        
        layout.addSpacing(20)
        
        # Menu buttons
        self.menu_buttons = []
        
        menus = [
            ("🏠", "Home", 0),
            ("👨‍🎓", "Students", 1),
            ("📊", "Attendance", 2),
            ("👥", "Staff", 3),
            ("💰", "Fees", 4),
            ("⚙️", "Settings", 5)
        ]
        
        for icon, text, index in menus:
            btn = QPushButton(f"{icon}  {text}")
            btn.setStyleSheet("""
                QPushButton {
                    background: rgba(255, 255, 255, 0.1);
                    color: white;
                    border: none;
                    border-radius: 9px;
                    padding: 13px;
                    text-align: left;
                    font-size: 18px;
                    font-weight: 500;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.15);
                }
                QPushButton:pressed {
                    background: rgba(255, 255, 255, 0.4);
                }
            """)
            btn.clicked.connect(lambda checked, idx=index: self.change_page(idx))
            layout.addWidget(btn)
            self.menu_buttons.append(btn)
        
        layout.addStretch()
        
        # Refresh button
        refresh_btn = QPushButton("🔄  Refresh")
        refresh_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px;
                font-size: 15px;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.25);
            }
        """)
        refresh_btn.clicked.connect(self.refresh_data)
        layout.addWidget(refresh_btn)
        
        # Logout button
        logout_btn = QPushButton("🚪  Logout")
        logout_btn.setStyleSheet("""
            QPushButton {
                background: rgba(255, 255, 255, 0.15);
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px;
                font-size: 14px;
            }
            QPushButton:hover {
                background: rgba(255, 100, 100, 0.5);
            }
        """)
        logout_btn.clicked.connect(self.logout)
        layout.addWidget(logout_btn)
        
        return sidebar
    
    def create_footer(self):
        footer = QFrame()
        footer.setFixedHeight(40)
        footer.setStyleSheet("""
            QFrame {
                background: rgba(255, 255, 255, 0.9);
                border-top: 1px solid rgba(0, 0, 0, 0.1);
            }
        """)
        
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 0, 20, 0)
        
        # Left side - time and session
        self.time_label = QLabel()
        self.time_label.setStyleSheet("""
            color: #333;
            font-size: 15px;
            font-weight: 500;
        """)
        layout.addWidget(self.time_label)
        
        layout.addStretch()
        
        # Right side - credit
        credit = QLabel('''
            <div style="text-align:center; font-size:16px;">
                Designed by <b>Harsh Kumar</b>•
                Contact on → 
                <a href="https://www.linkedin.com/in/harsh-kumar-627a6b2b4" style="color:#0A66C2; text-decoration:none;">LinkedIn</a> |
                <a href="https://wa.me/917078518163" style="color:#25D366; text-decoration:none;">WhatsApp</a>
            </div>
            ''')

        credit.setOpenExternalLinks(True)
        credit.setTextInteractionFlags(Qt.TextBrowserInteraction)
        credit.setAlignment(Qt.AlignCenter)
        credit.setStyleSheet("""
            color: #666;
            font-size: 20px;
        """)
        layout.addWidget(credit)
        
        return footer

    
    
    def update_time(self):
        now = datetime.now()
        time_str = now.strftime("%H:%M:%S")
        self.time_label.setText(f"🕐 {time_str} | Session: {self.current_session}")
    
    def change_page(self, index):
        self.stack.setCurrentIndex(index)
        # Update button styles
        for i, btn in enumerate(self.menu_buttons):
            if i == index:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.3);
                        color: white;
                        border: none;
                        border-radius: 10px;
                        padding: 12px;
                        text-align: left;
                        font-size: 15px;
                        font-weight: 500;
                    }
                """)
            else:
                btn.setStyleSheet("""
                    QPushButton {
                        background: rgba(255, 255, 255, 0.1);
                        color: white;
                        border: none;
                        border-radius: 10px;
                        padding: 12px;
                        text-align: left;
                        font-size: 14px;
                        font-weight: 500;
                    }
                    QPushButton:hover {
                        background: rgba(255, 255, 255, 0.2);
                    }
                """)
        
        # Refresh data when changing pages
        if index == 0:  # Home page
            QTimer.singleShot(100, self.refresh_home_data)
        elif index == 1:  # Students page
            if hasattr(self, 'load_students'):
                QTimer.singleShot(100, self.load_students)
        elif index == 3:  # Staff page
            if hasattr(self, 'load_staff'):
                QTimer.singleShot(100, self.load_staff)
                QTimer.singleShot(200, self.load_staff_for_salary)
        elif index == 4:  # Fees page
            if hasattr(self, 'load_fee_records'):
                QTimer.singleShot(100, self.load_fee_records)

    def load_last_session(self):
        """Load the last used session from settings"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'last_session'")
            result = cursor.fetchone()
            conn.close()
            
            if result:
                return result[0]
            else:
                return "2024-25"  # Default session
        except Exception as e:
            print(f"Error loading last session: {e}")
            return "2024-25"
        
    def save_last_session(self, session):
        """Save the current session to settings"""
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO settings (key, value) 
                VALUES ('last_session', ?)
            """, (session,))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"Error saving last session: {e}")
    
    def change_session(self, session):
        self.current_session = session
        self.save_last_session(session)  # Added this line

        # Refresh home data immediately
        QTimer.singleShot(100, self.refresh_home_data)
        
        # Reload all data for new session
        try:
            if hasattr(self, 'load_students'):
                QTimer.singleShot(200, self.load_students)
            if hasattr(self, 'load_staff'):
                QTimer.singleShot(300, self.load_staff)
            if hasattr(self, 'load_staff_for_salary'):
                QTimer.singleShot(400, self.load_staff_for_salary)
            if hasattr(self, 'load_fee_records'):
                QTimer.singleShot(500, self.load_fee_records)
            if hasattr(self, 'load_salary_history'):
                QTimer.singleShot(600, self.load_salary_history)
        except Exception as e:
            print(f"Error reloading data for session {session}: {e}")
        
        # Show message
        QMessageBox.information(self, "Session Changed", f"Switched to session {session}")
        
        # Refresh the current page
        current_index = self.stack.currentIndex()
        self.change_page(current_index)
    
    def refresh_data(self):
        current_index = self.stack.currentIndex()
        if current_index == 0:
            self.refresh_home_data()
        QMessageBox.information(self, "Refresh", "Data refreshed successfully!")
    
    def logout(self):
        reply = QMessageBox.question(self, "Logout", 
                                     "Are you sure you want to logout?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.close()
            login = LoginWindow()
            login.show()
    
    def create_home_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Page title
        title = QLabel("Dashboard")
        title.setStyleSheet("""
            font-size: 36px;
            font-weight: bold;
            color: #333;
        """)
        layout.addWidget(title)
        
        # Statistics cards
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(20)
        
        # Total Students Card
        self.total_students_card = self.create_stat_card(
            "👨‍🎓", "Total Students", "0", 
            "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #667eea, stop:1 #764ba2)"
        )
        cards_layout.addWidget(self.total_students_card)
        
        # Total Staff Card
        self.total_staff_card = self.create_stat_card(
            "👥", "Total Staff", "0",
            "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #06d6a0, stop:1 #00b4d8)"
        )
        cards_layout.addWidget(self.total_staff_card)
        
        # Fees Collected Card
        self.fees_collected_card = self.create_stat_card(
            "💰", "Fees Collected", "₹0.00",
            "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f093fb, stop:1 #f5576c)",

        )
        cards_layout.addWidget(self.fees_collected_card)
        
        # Total Expenses Card
        self.total_expenses_card = self.create_stat_card(
            "💸", "Total Expenses", "₹0.00",
            "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fa709a, stop:1 #fee140)"
        )
        cards_layout.addWidget(self.total_expenses_card)
        
        layout.addLayout(cards_layout)
        
        # Average Attendance Section
        attendance_frame = QFrame()
        attendance_frame.setStyleSheet("""
            QFrame {
                                       
                background: white;
                border-radius: 15px;
                border: 1px solid rgba(0, 0, 0, 0.1);
            }
        """)
        
        attendance_layout = QVBoxLayout(attendance_frame)
        attendance_layout.setContentsMargins(25, 25, 25, 25)
        attendance_layout.setSpacing(15)
        
        att_title = QLabel("📊 Average Attendance")
        att_title.setStyleSheet("""
            font-size: 20px;
            font-weight: bold;
            color: #667eea;
        """)
        attendance_layout.addWidget(att_title)
        
        # Filter controls
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Filter:"))
        
        self.attendance_filter = QComboBox()
        self.attendance_filter.addItems(["Current Month", "Session Year"])
        self.attendance_filter.setStyleSheet("""
            QComboBox {
                color: black;
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 8px;
                min-width: 150px;
                font-size: 15px;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                color: black;
                selection-background-color: #667eea;
                selection-color: white;
                border: 1px solid #aaa;
            }
       
        """)
        filter_layout.addWidget(self.attendance_filter)
        
        load_att_btn = QPushButton("📊 Load Attendance")
        load_att_btn.setStyleSheet("""
            QPushButton {
                background: #667eea;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 10px 20px;
                font-weight: bold;
            }
            QPushButton:hover {
                background: #5568d3;
            }
        """)
        load_att_btn.clicked.connect(self.load_average_attendance)
        filter_layout.addWidget(load_att_btn)
        filter_layout.addStretch()
        
        attendance_layout.addLayout(filter_layout)
        
        # Attendance display
        self.avg_attendance_label = QLabel("Average Attendance: 0.00%")
        self.avg_attendance_label.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: #667eea;
            padding: 20px;
        """)
        self.avg_attendance_label.setAlignment(Qt.AlignCenter)
        attendance_layout.addWidget(self.avg_attendance_label)
        
        layout.addWidget(attendance_frame)
        
        # Export buttons
        export_layout = QHBoxLayout()
        export_layout.setSpacing(15)
        
        export_buttons = [
            ("📄 Export Students Report", self.export_students_report),
            ("📄 Export Staff Report", self.export_staff_report),
            ("📄 Export Fees Report", self.export_fees_report),
            ("📄 Export Expenses Report", self.export_expenses_report)
        ]
        
        for text, callback in export_buttons:
            btn = QPushButton(text)
            btn.setStyleSheet("""
                QPushButton {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #00b4d8, stop:1 #0096c7);
                    color: white;
                    border: none;
                    border-radius: 10px;
                    padding: 12px;
                    font-weight: bold;
                    font-size: 15px;
                }
                QPushButton:hover {
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                        stop:0 #0096c7, stop:1 #00b4d8);
                }
            """)
            btn.clicked.connect(callback)
            export_layout.addWidget(btn)
        
        layout.addLayout(export_layout)
        layout.addStretch()
        
        # Load initial data
        self.refresh_home_data()
        
        return page
    
    def create_stat_card(self, icon, title, value, gradient):
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {gradient};
                border-radius: 15px;
                min-height: 150px;
            }}
        """)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)
        
        icon_label = QLabel(icon)
        icon_label.setStyleSheet("""
            font-size: 75px;
            background: transparent;
        """)
        layout.addWidget(icon_label)
        
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            font-size: 25px;
            color: rgba(255, 255, 255, 0.9);
            background: transparent;
        """)
        layout.addWidget(title_label)
        
        value_label = QLabel(value)
        value_label.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: white;
            background: transparent;
        """)
        value_label.setObjectName("value_label")
        layout.addWidget(value_label)
        
        layout.addStretch()
        
        return card
    
    def refresh_home_data(self):
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Total students
            cursor.execute("SELECT COUNT(*) FROM students WHERE session = ?", (self.current_session,))
            result = cursor.fetchone()
            total_students = result[0] if result else 0
            
            # Find and update the value label in students card
            for child in self.total_students_card.findChildren(QLabel):
                if child.objectName() == "value_label":
                    child.setText(str(total_students))
                    break
            
            # Total staff
            cursor.execute("SELECT COUNT(*) FROM staff WHERE session = ?", (self.current_session,))
            result = cursor.fetchone()
            total_staff = result[0] if result else 0
            
            # Find and update the value label in staff card
            for child in self.total_staff_card.findChildren(QLabel):
                if child.objectName() == "value_label":
                    child.setText(str(total_staff))
                    break
            
            # Fees collected
            cursor.execute("SELECT SUM(total_amount) FROM fee_payments WHERE session = ?", (self.current_session,))
            result = cursor.fetchone()
            fees = result[0] if result and result[0] else 0
            
            # Find and update the value label in fees card
            for child in self.fees_collected_card.findChildren(QLabel):
                if child.objectName() == "value_label":
                    child.setText(f"₹{fees:.2f}")
                    break
            
            # Total expenses
            cursor.execute("SELECT SUM(amount) FROM salary_payments WHERE session = ?", (self.current_session,))
            result = cursor.fetchone()
            expenses = result[0] if result and result[0] else 0
            
            # Find and update the value label in expenses card
            for child in self.total_expenses_card.findChildren(QLabel):
                if child.objectName() == "value_label":
                    child.setText(f"₹{expenses:.2f}")
                    break
            
            conn.close()
            
        except Exception as e:
            print(f"Error refreshing home data: {e}")
            traceback.print_exc()
    
    def load_average_attendance(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        filter_type = self.attendance_filter.currentText()
        
        if filter_type == "Current Month":
            current_month = datetime.now().strftime("%B")
            current_year = datetime.now().year
            cursor.execute("""
                SELECT AVG(percentage) FROM attendance 
                WHERE session = ? AND month = ? AND year = ?
            """, (self.current_session, current_month, str(current_year)))
        else:
            cursor.execute("""
                SELECT AVG(percentage) FROM attendance WHERE session = ?
            """, (self.current_session,))
        
        result = cursor.fetchone()
        avg = result[0] if result and result[0] else 0.0
        
        self.avg_attendance_label.setText(f"Average Attendance: {avg:.2f}%")
        conn.close()
    
    def export_students_report(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Report")
        if not folder:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE session = ?", (self.current_session,))
        students = cursor.fetchall()
        conn.close()
        
        filename = os.path.join(folder, f"Students_Report_{self.current_session}.pdf")
        
        doc = SimpleDocTemplate(filename, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=26,
            textColor=colors.HexColor('#667eea'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        elements.append(Paragraph("Students Report", title_style))
        elements.append(Paragraph(f"Session: {self.current_session}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Table
        data = [['ID', 'Student No.', 'Name', 'Class', 'Section', 'Roll No.']]
        for student in students:
            data.append([
                str(student[0]), student[1], student[2], 
                student[4], student[5], student[3]
            ])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        QMessageBox.information(self, "Success", f"Report saved to:\n{filename}")
    
    def export_staff_report(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Report")
        if not folder:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff WHERE session = ?", (self.current_session,))
        staff = cursor.fetchall()
        conn.close()
        
        filename = os.path.join(folder, f"Staff_Report_{self.current_session}.pdf")
        
        doc = SimpleDocTemplate(filename, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=25,
            textColor=colors.HexColor('#06d6a0'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        elements.append(Paragraph("Staff Report", title_style))
        elements.append(Paragraph(f"Session: {self.current_session}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        data = [['ID', 'Staff ID', 'Name', 'Designation', 'Department', 'Salary']]
        for s in staff:
            data.append([
                str(s[0]), s[1], s[2], s[5], s[7], f"₹{s[9]:.2f}"
            ])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#06d6a0')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        QMessageBox.information(self, "Success", f"Report saved to:\n{filename}")
    
    def export_fees_report(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Report")
        if not folder:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fee_payments WHERE session = ?", (self.current_session,))
        fees = cursor.fetchall()
        conn.close()
        
        filename = os.path.join(folder, f"Fees_Report_{self.current_session}.pdf")
        
        doc = SimpleDocTemplate(filename, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#f5576c'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        elements.append(Paragraph("Fees Collection Report", title_style))
        elements.append(Paragraph(f"Session: {self.current_session}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        total = sum([float(f[16]) for f in fees])
        elements.append(Paragraph(f"<b>Total Collected: ₹{total:.2f}</b>", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        data = [['Receipt No.', 'Student', 'Class', 'Date', 'Amount', 'Status']]
        for f in fees:
            data.append([
                f[1], f[3], f[4], f[8], f"₹{f[16]:.2f}", f[17]

            ])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f5576c')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        QMessageBox.information(self, "Success", f"Report saved to:\n{filename}")
    
    def export_expenses_report(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Report")
        if not folder:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM salary_payments WHERE session = ?", (self.current_session,))
        salaries = cursor.fetchall()
        conn.close()
        
        filename = os.path.join(folder, f"Expenses_Report_{self.current_session}.pdf")
        
        doc = SimpleDocTemplate(filename, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#fee140'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        elements.append(Paragraph("Expenses Report", title_style))
        elements.append(Paragraph(f"Session: {self.current_session}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        total = sum([float(s[3]) for s in salaries])
        elements.append(Paragraph(f"<b>Total Expenses: ₹{total:.2f}</b>", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        data = [['ID', 'Staff Name', 'Amount', 'Date', 'Month']]
        for s in salaries:
            data.append([
                str(s[0]), s[2], f"₹{s[3]:.2f}", s[4], s[5]
            ])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#fa709a')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        QMessageBox.information(self, "Success", f"Report saved to:\n{filename}")
    
    def create_student_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Page title
        title = QLabel("Students Management")
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: #333;
        """)
        layout.addWidget(title)
        
        # Tab widget
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                background: white;
                border-radius: 10px;
            }
            QTabBar::tab {
                background: #f0f0f0;
                color: #333;
                padding: 10px 20px;
                margin-right: 5px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: white;
                color: #667eea;
                font-weight: bold;
            }
        """)
        
        # Add Student Tab
        add_student_tab = self.create_add_student_tab()
        tabs.addTab(add_student_tab, "➕ Add Student")
        
        # Student List Tab
        student_list_tab = self.create_student_list_tab()
        tabs.addTab(student_list_tab, "📋 Student List")
        
        # Backup/Restore Tab
        backup_tab = self.create_student_backup_tab()
        tabs.addTab(backup_tab, "💾 Backup & Restore")
        
        layout.addWidget(tabs)
        
        return page
    
    def create_add_student_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        # Student Number (auto-generated)
        self.student_number_input = QLineEdit()
        self.student_number_input.setReadOnly(True)
        self.student_number_input.setPlaceholderText("Auto-generated")
        self.student_number_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Student Number:", self.student_number_input)
        
        # Full Name
        self.student_name_input = QLineEdit()
        self.student_name_input.setPlaceholderText("Enter full name")
        self.student_name_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Full Name:*", self.student_name_input)
        
        # Roll Number
        self.student_roll_input = QLineEdit()
        self.student_roll_input.setPlaceholderText("Enter roll number")
        self.student_roll_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Roll Number:*", self.student_roll_input)
        
        # Class
        self.student_class_combo = QComboBox()
        classes = ["Nursery", "LKG", "UKG"] + [str(i) for i in range(1, 13)]
        self.student_class_combo.addItems(classes)
        self.student_class_combo.setStyleSheet(self.get_input_style())
        form_layout.addRow("Class:*", self.student_class_combo)
        
        # Section
        self.student_section_combo = QComboBox()
        self.student_section_combo.addItems([chr(i) for i in range(65, 73)])  # A to H
        self.student_section_combo.setStyleSheet(self.get_input_style())
        form_layout.addRow("Section:*", self.student_section_combo)
        
        # Parent Name
        self.student_parent_input = QLineEdit()
        self.student_parent_input.setPlaceholderText("Enter parent name")
        self.student_parent_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Parent Name:*", self.student_parent_input)
        
        # Gender
        self.student_gender_combo = QComboBox()
        self.student_gender_combo.addItems(["Male", "Female", "Other"])
        self.student_gender_combo.setStyleSheet(self.get_input_style())
        form_layout.addRow("Gender:*", self.student_gender_combo)
        
        # Date of Birth
        self.student_dob_input = QDateEdit()
        self.student_dob_input.setCalendarPopup(True)
        self.student_dob_input.setDate(QDate.currentDate())
        self.student_dob_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Date of Birth:*", self.student_dob_input)
        
        # Parent Number
        self.student_phone_input = QLineEdit()
        self.student_phone_input.setPlaceholderText("Enter parent phone number")
        self.student_phone_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Parent Number:*", self.student_phone_input)
        
        # Address
        self.student_address_input = QTextEdit()
        self.student_address_input.setPlaceholderText("Enter address")
        self.student_address_input.setMaximumHeight(80)
        self.student_address_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Address:*", self.student_address_input)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Student")
        save_btn.setStyleSheet(self.get_button_style("#667eea"))
        save_btn.clicked.connect(self.save_student)
        button_layout.addWidget(save_btn)
        
        clear_btn = QPushButton("🔄 Clear Form")
        clear_btn.setStyleSheet(self.get_button_style("#6c757d"))
        clear_btn.clicked.connect(self.clear_student_form)
        button_layout.addWidget(clear_btn)
        
        layout.addLayout(button_layout)
        layout.addStretch()
        
        # Generate student number
        self.generate_student_number()
        
        return tab
    
    def create_student_list_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Search and filter
        filter_layout = QHBoxLayout()
        
        self.student_search_input = QLineEdit()
        self.student_search_input.setPlaceholderText("🔍 Search by name or student number...")
        self.student_search_input.setStyleSheet(self.get_input_style())
        self.student_search_input.textChanged.connect(self.filter_students)
        filter_layout.addWidget(self.student_search_input)
        
        filter_layout.addWidget(QLabel("Class:"))
        self.student_filter_class = QComboBox()
        self.student_filter_class.addItem("All")
        classes = ["Nursery", "LKG", "UKG"] + [str(i) for i in range(1, 13)]
        self.student_filter_class.addItems(classes)
        self.student_filter_class.setStyleSheet(self.get_input_style())
        self.student_filter_class.currentTextChanged.connect(self.filter_students)
        filter_layout.addWidget(self.student_filter_class)
        
        filter_layout.addWidget(QLabel("Section:"))
        self.student_filter_section = QComboBox()
        self.student_filter_section.addItem("All")
        self.student_filter_section.addItems([chr(i) for i in range(65, 73)])
        self.student_filter_section.setStyleSheet(self.get_input_style())
        self.student_filter_section.currentTextChanged.connect(self.filter_students)
        filter_layout.addWidget(self.student_filter_section)
        
        export_btn = QPushButton("📄 Export PDF")
        export_btn.setStyleSheet(self.get_button_style("#00b4d8"))
        export_btn.clicked.connect(self.export_students_list)
        filter_layout.addWidget(export_btn)
        
        layout.addLayout(filter_layout)
        
        # Table
        self.student_table = QTableWidget()
        self.student_table.setColumnCount(10)
        self.student_table.setHorizontalHeaderLabels([
            "Student No.", "Name", "Roll No.", "Class", "Section",
            "Parent Name", "Gender", "DOB", "Phone", "Actions"
        ])
        self.student_table.horizontalHeader().setStretchLastSection(True)
        self.student_table.setAlternatingRowColors(True)
        self.student_table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background: #667eea;
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.student_table)
        
        # Load students
        self.load_students()
        
        return tab
    
    def create_student_backup_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Backup section
        backup_group = QGroupBox("Backup Student Data")
        backup_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #667eea;
                border: 2px solid #667eea;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setSpacing(15)
        
        backup_desc = QLabel("Export all student data to a JSON file for backup purposes.")
        backup_desc.setWordWrap(True)
        backup_layout.addWidget(backup_desc)
        
        backup_btn = QPushButton("💾 Backup Student Data")
        backup_btn.setStyleSheet(self.get_button_style("#667eea"))
        backup_btn.clicked.connect(self.backup_students)
        backup_layout.addWidget(backup_btn)
        
        layout.addWidget(backup_group)
        
        # Restore section
        restore_group = QGroupBox("Restore Student Data")
        restore_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #f5576c;
                border: 2px solid #f5576c;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        restore_layout = QVBoxLayout(restore_group)
        restore_layout.setSpacing(15)
        
        restore_desc = QLabel("Import student data from a backup JSON file. You can choose to restore to a specific class/section or all students.")
        restore_desc.setWordWrap(True)
        restore_layout.addWidget(restore_desc)
        
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Restore to:"))
        
        self.restore_filter_combo = QComboBox()
        self.restore_filter_combo.addItems(["All Students", "Specific Class", "Specific Section"])
        self.restore_filter_combo.setStyleSheet(self.get_input_style())
        filter_layout.addWidget(self.restore_filter_combo)
        
        self.restore_class_combo = QComboBox()
        classes = ["Nursery", "LKG", "UKG"] + [str(i) for i in range(1, 13)]
        self.restore_class_combo.addItems(classes)
        self.restore_class_combo.setStyleSheet(self.get_input_style())
        self.restore_class_combo.setEnabled(False)
        filter_layout.addWidget(self.restore_class_combo)
        
        self.restore_section_combo = QComboBox()
        self.restore_section_combo.addItems([chr(i) for i in range(65, 73)])
        self.restore_section_combo.setStyleSheet(self.get_input_style())
        self.restore_section_combo.setEnabled(False)
        filter_layout.addWidget(self.restore_section_combo)
        
        self.restore_filter_combo.currentTextChanged.connect(self.update_restore_filters)
        
        restore_layout.addLayout(filter_layout)
        
        restore_btn = QPushButton("📂 Choose File and Restore")
        restore_btn.setStyleSheet(self.get_button_style("#f5576c"))
        restore_btn.clicked.connect(self.restore_students)
        restore_layout.addWidget(restore_btn)
        
        layout.addWidget(restore_group)
        layout.addStretch()
        
        return tab
    
    def get_input_style(self):
        return """
            QLineEdit, QComboBox, QDateEdit, QTextEdit {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 10px;
                font-size: 15px;
                color: #333;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus {
                border: 2px solid #667eea;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #667eea;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: white;
                color: #333;
                border: 1px solid #ddd;
                selection-background-color: #667eea;
                selection-color: white;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QComboBox QAbstractItemView::item:hover {
                background: #f0f0f0;
                color: #333;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #667eea;
                color: white;
            }
        """
    
    def get_button_style(self, color):
        return f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 14px;
                min-width: 150px;
            }}
            QPushButton:hover {{
                background: {color}dd;
            }}
            QPushButton:pressed {{
                padding-top: 14px;
                padding-bottom: 10px;
            }}
        """
    
    def generate_student_number(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students")
        count = cursor.fetchone()[0]
        conn.close()
        
        student_number = f"STU{str(count + 1).zfill(6)}"
        self.student_number_input.setText(student_number)
    
    def save_student(self):
        # Validate inputs
        if not self.student_name_input.text():
            QMessageBox.warning(self, "Validation Error", "Please enter student name!")
            return
        
        if not self.student_roll_input.text():
            QMessageBox.warning(self, "Validation Error", "Please enter roll number!")
            return
        
        if not self.student_parent_input.text():
            QMessageBox.warning(self, "Validation Error", "Please enter parent name!")
            return
        
        if not self.student_phone_input.text():
            QMessageBox.warning(self, "Validation Error", "Please enter parent phone number!")
            return
        
        if not self.student_address_input.toPlainText():
            QMessageBox.warning(self, "Validation Error", "Please enter address!")
            return
        
        # Save to database
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO students (
                    student_number, full_name, roll_number, class, section,
                    parent_name, gender, dob, parent_number, address, session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.student_number_input.text(),
                self.student_name_input.text(),
                self.student_roll_input.text(),
                self.student_class_combo.currentText(),
                self.student_section_combo.currentText(),
                self.student_parent_input.text(),
                self.student_gender_combo.currentText(),
                self.student_dob_input.date().toString("yyyy-MM-dd"),
                self.student_phone_input.text(),
                self.student_address_input.toPlainText(),
                self.current_session
            ))
            
            conn.commit()
            QMessageBox.information(self, "Success", "Student added successfully!")
            self.clear_student_form()
            if hasattr(self, 'load_students'):
                self.load_students()
            # Force refresh home data
            QTimer.singleShot(100, self.refresh_home_data)
            
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Error", "Student number already exists!")
        finally:
            conn.close()
    
    def clear_student_form(self):
        self.student_name_input.clear()
        self.student_roll_input.clear()
        self.student_parent_input.clear()
        self.student_phone_input.clear()
        self.student_address_input.clear()
        self.student_class_combo.setCurrentIndex(0)
        self.student_section_combo.setCurrentIndex(0)
        self.student_gender_combo.setCurrentIndex(0)
        self.student_dob_input.setDate(QDate.currentDate())
        self.generate_student_number()
    
    def load_students(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE session = ? ORDER BY class, section, roll_number", 
                      (self.current_session,))
        students = cursor.fetchall()
        conn.close()
        
        self.student_table.setRowCount(0)
        
        for row_idx, student in enumerate(students):
            self.student_table.insertRow(row_idx)
            
            # Add data
            self.student_table.setItem(row_idx, 0, QTableWidgetItem(student[1]))  # Student number
            self.student_table.setItem(row_idx, 1, QTableWidgetItem(student[2]))  # Name
            self.student_table.setItem(row_idx, 2, QTableWidgetItem(student[3]))  # Roll number
            self.student_table.setItem(row_idx, 3, QTableWidgetItem(student[4]))  # Class
            self.student_table.setItem(row_idx, 4, QTableWidgetItem(student[5]))  # Section
            self.student_table.setItem(row_idx, 5, QTableWidgetItem(student[6]))  # Parent name
            self.student_table.setItem(row_idx, 6, QTableWidgetItem(student[7]))  # Gender
            self.student_table.setItem(row_idx, 7, QTableWidgetItem(student[8]))  # DOB
            self.student_table.setItem(row_idx, 8, QTableWidgetItem(student[9]))  # Phone
            
            # Action buttons
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(5, 5, 5, 5)
            action_layout.setSpacing(5)
            
            edit_btn = QPushButton("✏️")
            edit_btn.setStyleSheet("background: #4CAF50; color: white; border: none; padding: 5px; border-radius: 5px;")
            edit_btn.clicked.connect(lambda checked, s=student: self.edit_student(s))
            action_layout.addWidget(edit_btn)
            
            delete_btn = QPushButton("🗑️")
            delete_btn.setStyleSheet("background: #f44336; color: white; border: none; padding: 5px; border-radius: 5px;")
            delete_btn.clicked.connect(lambda checked, s=student: self.delete_student(s))
            action_layout.addWidget(delete_btn)
            
            self.student_table.setCellWidget(row_idx, 9, action_widget)
    
    def filter_students(self):
        search_text = self.student_search_input.text().lower()
        filter_class = self.student_filter_class.currentText()
        filter_section = self.student_filter_section.currentText()
        
        for row in range(self.student_table.rowCount()):
            show_row = True
            
            # Search filter
            if search_text:
                name = self.student_table.item(row, 1).text().lower()
                student_no = self.student_table.item(row, 0).text().lower()
                if search_text not in name and search_text not in student_no:
                    show_row = False
            
            # Class filter
            if filter_class != "All":
                class_text = self.student_table.item(row, 3).text()
                if class_text != filter_class:
                    show_row = False
            
            # Section filter
            if filter_section != "All":
                section_text = self.student_table.item(row, 4).text()
                if section_text != filter_section:
                    show_row = False
            
            self.student_table.setRowHidden(row, not show_row)
    
    def edit_student(self, student):
        # Switch to add student tab and populate form
        # For simplicity, we'll show a message
        QMessageBox.information(self, "Edit Student", 
                              f"Edit functionality for {student[2]} will open in the Add Student tab.")
    
    def delete_student(self, student):
        reply = QMessageBox.question(self, "Delete Student",
                                    f"Are you sure you want to delete {student[2]}?",
                                    QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM students WHERE id = ?", (student[0],))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Success", "Student deleted successfully!")
            self.load_students()
            self.refresh_home_data()
    
    def export_students_list(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Report")
        if not folder:
            return
        
        self.export_students_report()
    
    def backup_students(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Backup")
        if not folder:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM students WHERE session = ?", (self.current_session,))
        students = cursor.fetchall()
        conn.close()
        
        # Convert to JSON
        students_data = []
        for s in students:
            students_data.append({
                'student_number': s[1],
                'full_name': s[2],
                'roll_number': s[3],
                'class': s[4],
                'section': s[5],
                'parent_name': s[6],
                'gender': s[7],
                'dob': s[8],
                'parent_number': s[9],
                'address': s[10],
                'session': s[11]
            })
        
        filename = os.path.join(folder, f"students_backup_{self.current_session}.json")
        with open(filename, 'w') as f:
            json.dump(students_data, f, indent=4)
        
        QMessageBox.information(self, "Success", f"Backup saved to:\n{filename}")
    
    def restore_students(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Backup File", "", "JSON Files (*.json)")
        if not filename:
            return
        
        try:
            with open(filename, 'r') as f:
                students_data = json.load(f)
            
            filter_type = self.restore_filter_combo.currentText()
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            restored_count = 0
            for student in students_data:
                # Apply filters
                if filter_type == "Specific Class":
                    if student['class'] != self.restore_class_combo.currentText():
                        continue
                elif filter_type == "Specific Section":
                    if student['section'] != self.restore_section_combo.currentText():
                        continue
                
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO students (
                            student_number, full_name, roll_number, class, section,
                            parent_name, gender, dob, parent_number, address, session
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        student['student_number'],
                        student['full_name'],
                        student['roll_number'],
                        student['class'],
                        student['section'],
                        student['parent_name'],
                        student['gender'],
                        student['dob'],
                        student['parent_number'],
                        student['address'],
                        self.current_session
                    ))
                    restored_count += 1
                except:
                    pass
            
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Success", f"Restored {restored_count} students successfully!")
            self.load_students()
            self.refresh_home_data()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restore backup:\n{str(e)}")
    
    def update_restore_filters(self, text):
        if text == "Specific Class":
            self.restore_class_combo.setEnabled(True)
            self.restore_section_combo.setEnabled(False)
        elif text == "Specific Section":
            self.restore_class_combo.setEnabled(False)
            self.restore_section_combo.setEnabled(True)
        else:
            self.restore_class_combo.setEnabled(False)
            self.restore_section_combo.setEnabled(False)
    
    def create_attendance_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Page title
        title = QLabel("Attendance Management")
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: #333;
        """)
        layout.addWidget(title)
        
        # Controls
        controls_frame = QFrame()
        controls_frame.setStyleSheet("""
            QFrame {
                background: white;
                border-radius: 10px;
                border: 1px solid #ddd;
            }
        """)
        
        controls_layout = QVBoxLayout(controls_frame)
        controls_layout.setContentsMargins(20, 20, 20, 20)
        controls_layout.setSpacing(15)
        
        # Selection controls
        select_layout = QHBoxLayout()
        
        select_layout.addWidget(QLabel("Class:"))
        self.att_class_combo = QComboBox()
        classes = ["Nursery", "LKG", "UKG"] + [str(i) for i in range(1, 13)]
        self.att_class_combo.addItems(classes)
        self.att_class_combo.setStyleSheet(self.get_input_style())
        select_layout.addWidget(self.att_class_combo)
        
        select_layout.addWidget(QLabel("Section:"))
        self.att_section_combo = QComboBox()
        self.att_section_combo.addItems([chr(i) for i in range(65, 73)])
        self.att_section_combo.setStyleSheet(self.get_input_style())
        select_layout.addWidget(self.att_section_combo)
        
        select_layout.addWidget(QLabel("Month:"))
        self.att_month_combo = QComboBox()
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        self.att_month_combo.addItems(months)
        self.att_month_combo.setCurrentText(datetime.now().strftime("%B"))
        self.att_month_combo.setStyleSheet(self.get_input_style())
        select_layout.addWidget(self.att_month_combo)
        
        select_layout.addWidget(QLabel("Year:"))
        self.att_year_combo = QComboBox()
        self.att_year_combo.addItems([str(y) for y in range(2024, 2036)])
        self.att_year_combo.setCurrentText(str(datetime.now().year))
        self.att_year_combo.setStyleSheet(self.get_input_style())
        select_layout.addWidget(self.att_year_combo)
        
        select_layout.addWidget(QLabel("Working Days:"))
        self.att_working_days = QSpinBox()
        self.att_working_days.setRange(1, 31)
        self.att_working_days.setValue(25)
        self.att_working_days.setStyleSheet(self.get_input_style())
        select_layout.addWidget(self.att_working_days)
        
        load_btn = QPushButton("📋 Load Students")
        load_btn.setStyleSheet(self.get_button_style("#667eea"))
        load_btn.clicked.connect(self.load_attendance_students)
        select_layout.addWidget(load_btn)
        
        select_layout.addStretch()
        
        controls_layout.addLayout(select_layout)
        
        layout.addWidget(controls_frame)
        
        # Attendance table
        self.attendance_table = QTableWidget()
        self.attendance_table.setColumnCount(6)
        self.attendance_table.setHorizontalHeaderLabels([
            "Roll No.", "Student Name", "Parent Name", "Days Present", "Percentage", "Status"
        ])
        self.attendance_table.horizontalHeader().setStretchLastSection(True)
        self.attendance_table.setAlternatingRowColors(True)
        self.attendance_table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background: #667eea;
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.attendance_table)
        
        # Footer with average and buttons
        footer_layout = QHBoxLayout()
        
        self.class_avg_label = QLabel("Average Class Attendance: 0.00%")
        self.class_avg_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #667eea;
        """)
        footer_layout.addWidget(self.class_avg_label)
        
        footer_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Attendance")
        save_btn.setStyleSheet(self.get_button_style("#4CAF50"))
        save_btn.clicked.connect(self.save_attendance)
        footer_layout.addWidget(save_btn)
        
        export_btn = QPushButton("📄 Export PDF")
        export_btn.setStyleSheet(self.get_button_style("#00b4d8"))
        export_btn.clicked.connect(self.export_attendance)
        footer_layout.addWidget(export_btn)
        
        layout.addLayout(footer_layout)
        
        return page
    
    def load_attendance_students(self):
        selected_class = self.att_class_combo.currentText()
        selected_section = self.att_section_combo.currentText()
        month = self.att_month_combo.currentText()
        year = self.att_year_combo.currentText()
        
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT student_number, full_name, roll_number, parent_name 
                FROM students 
                WHERE class = ? AND section = ? AND session = ?
                ORDER BY CAST(roll_number AS INTEGER)
            """, (selected_class, selected_section, self.current_session))
            
            students = cursor.fetchall()
            
            if not students:
                conn.close()
                QMessageBox.information(self, "No Students", "No students found for the selected class and section.")
                return
            
            self.attendance_table.setRowCount(0)
            working_days = self.att_working_days.value()
            
            for row_idx, student in enumerate(students):
                self.attendance_table.insertRow(row_idx)
                
                # Roll number
                self.attendance_table.setItem(row_idx, 0, QTableWidgetItem(student[2]))
                
                # Student name
                self.attendance_table.setItem(row_idx, 1, QTableWidgetItem(student[1]))
                
                # Parent name
                self.attendance_table.setItem(row_idx, 2, QTableWidgetItem(student[3]))
                
                # Check if attendance already exists for this month
                cursor.execute("""
                    SELECT days_present, percentage 
                    FROM attendance 
                    WHERE student_number = ? AND month = ? AND year = ? AND session = ?
                """, (student[0], month, year, self.current_session))
                
                existing_attendance = cursor.fetchone()
                
                # Days present input
                days_input = QSpinBox()
                days_input.setRange(0, working_days)
                if existing_attendance:
                    days_input.setValue(existing_attendance[0])
                else:
                    days_input.setValue(0)
                days_input.valueChanged.connect(lambda v, r=row_idx: self.update_attendance_percentage(r))
                self.attendance_table.setCellWidget(row_idx, 3, days_input)
                
                # Calculate percentage
                if existing_attendance:
                    percentage = existing_attendance[1]
                else:
                    percentage = 0.0
                
                self.attendance_table.setItem(row_idx, 4, QTableWidgetItem(f"{percentage:.2f}%"))
                
                # Status
                if percentage >= 75:
                    status = "Good"
                elif percentage >= 50:
                    status = "Average"
                else:
                    status = "Poor"
                
                self.attendance_table.setItem(row_idx, 5, QTableWidgetItem(status))
            
            conn.close()
            self.calculate_class_average()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load students:\n{str(e)}")
            traceback.print_exc()
    
    def update_attendance_percentage(self, row):
        days_widget = self.attendance_table.cellWidget(row, 3)
        if days_widget:
            days_present = days_widget.value()
            working_days = self.att_working_days.value()
            
            percentage = (days_present / working_days * 100) if working_days > 0 else 0
            self.attendance_table.setItem(row, 4, QTableWidgetItem(f"{percentage:.2f}%"))
            
            # Update status
            if percentage >= 75:
                status = "Good"
            elif percentage >= 50:
                status = "Average"
            else:
                status = "Poor"
            
            self.attendance_table.setItem(row, 5, QTableWidgetItem(status))
        
        self.calculate_class_average()
    
    def calculate_class_average(self):
        total_percentage = 0
        count = 0
        
        for row in range(self.attendance_table.rowCount()):
            percentage_item = self.attendance_table.item(row, 4)
            if percentage_item:
                percentage_text = percentage_item.text().replace('%', '')
                try:
                    total_percentage += float(percentage_text)
                    count += 1
                except:
                    pass
        
        avg = total_percentage / count if count > 0 else 0
        self.class_avg_label.setText(f"Average Class Attendance: {avg:.2f}%")
    
    def save_attendance(self):
        if self.attendance_table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "Please load students first!")
            return
        
        selected_class = self.att_class_combo.currentText()
        selected_section = self.att_section_combo.currentText()
        month = self.att_month_combo.currentText()
        year = self.att_year_combo.currentText()
        working_days = self.att_working_days.value()
        
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            saved_count = 0
            for row in range(self.attendance_table.rowCount()):
                student_name = self.attendance_table.item(row, 1).text()
                
                # Get student number
                cursor.execute("SELECT student_number FROM students WHERE full_name = ? AND class = ? AND section = ? AND session = ?",
                             (student_name, selected_class, selected_section, self.current_session))
                result = cursor.fetchone()
                if not result:
                    continue
                
                student_number = result[0]
                
                days_widget = self.attendance_table.cellWidget(row, 3)
                days_present = days_widget.value() if days_widget else 0
                
                percentage_text = self.attendance_table.item(row, 4).text().replace('%', '')
                percentage = float(percentage_text)
                
                # Check if record exists
                cursor.execute("""
                    SELECT id FROM attendance 
                    WHERE student_number = ? AND month = ? AND year = ? AND session = ?
                """, (student_number, month, year, self.current_session))
                
                if cursor.fetchone():
                    # Update
                    cursor.execute("""
                        UPDATE attendance 
                        SET class = ?, section = ?, working_days = ?, days_present = ?, percentage = ?
                        WHERE student_number = ? AND month = ? AND year = ? AND session = ?
                    """, (selected_class, selected_section, working_days, days_present, percentage, 
                         student_number, month, year, self.current_session))
                else:
                    # Insert
                    cursor.execute("""
                        INSERT INTO attendance (
                            student_number, class, section, month, year,
                            working_days, days_present, percentage, session
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (student_number, selected_class, selected_section, month, year,
                         working_days, days_present, percentage, self.current_session))
                
                saved_count += 1
            
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Success", f"Attendance saved successfully for {saved_count} students!")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save attendance:\n{str(e)}")
            traceback.print_exc()
    
    def export_attendance(self):
        if self.attendance_table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "Please load students first!")
            return
        
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Report")
        if not folder:
            return
        
        selected_class = self.att_class_combo.currentText()
        selected_section = self.att_section_combo.currentText()
        month = self.att_month_combo.currentText()
        year = self.att_year_combo.currentText()
        
        filename = os.path.join(folder, f"Attendance_{selected_class}_{selected_section}_{month}_{year}.pdf")
        
        doc = SimpleDocTemplate(filename, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#667eea'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        elements.append(Paragraph("Attendance Report", title_style))
        elements.append(Paragraph(f"Class: {selected_class} | Section: {selected_section}", styles['Normal']))
        elements.append(Paragraph(f"Month: {month} {year} | Session: {self.current_session}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Table data
        data = [['Roll No.', 'Student Name', 'Days Present', 'Percentage', 'Status']]
        
        for row in range(self.attendance_table.rowCount()):
            roll = self.attendance_table.item(row, 0).text()
            name = self.attendance_table.item(row, 1).text()
            days_widget = self.attendance_table.cellWidget(row, 3)
            days = str(days_widget.value()) if days_widget else "0"
            percentage = self.attendance_table.item(row, 4).text()
            status = self.attendance_table.item(row, 5).text()
            
            data.append([roll, name, days, percentage, status])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#667eea')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(self.class_avg_label.text(), styles['Normal']))
        
        doc.build(elements)
        
        QMessageBox.information(self, "Success", f"Report saved to:\n{filename}")
    
    def create_staff_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Page title
        title = QLabel("Staff Management")
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: #333;
        """)
        layout.addWidget(title)
        
        # Tab widget
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                background: white;
                border-radius: 10px;
            }
            QTabBar::tab {
                background: #f0f0f0;
                color: #333;
                padding: 10px 20px;
                margin-right: 5px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: white;
                color: #06d6a0;
                font-weight: bold;
            }
        """)
        
        # Add Staff Tab
        add_staff_tab = self.create_add_staff_tab()
        tabs.addTab(add_staff_tab, "➕ Add Staff")
        
        # Staff List Tab
        staff_list_tab = self.create_staff_list_tab()
        tabs.addTab(staff_list_tab, "📋 Staff List")
        
        # Salary Payment Tab
        salary_tab = self.create_salary_tab()
        tabs.addTab(salary_tab, "💰 Pay Salary")
        
        # Salary History Tab
        history_tab = self.create_salary_history_tab()
        tabs.addTab(history_tab, "📊 Salary History")
        
        # Backup Tab
        backup_tab = self.create_staff_backup_tab()
        tabs.addTab(backup_tab, "💾 Backup & Restore")
        
        layout.addWidget(tabs)
        
        return page
    
    def create_add_staff_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        # Staff ID
        self.staff_id_input = QLineEdit()
        self.staff_id_input.setPlaceholderText("Auto-generated")
        self.staff_id_input.setReadOnly(True)
        self.staff_id_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Staff ID:", self.staff_id_input)
        
        # Name
        self.staff_name_input = QLineEdit()
        self.staff_name_input.setPlaceholderText("Enter staff name")
        self.staff_name_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Name:*", self.staff_name_input)
        
        # Phone
        self.staff_phone_input = QLineEdit()
        self.staff_phone_input.setPlaceholderText("Enter phone number")
        self.staff_phone_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Phone:*", self.staff_phone_input)
        
        # Email
        self.staff_email_input = QLineEdit()
        self.staff_email_input.setPlaceholderText("Enter email address")
        self.staff_email_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Email:", self.staff_email_input)
        
        # Designation
        self.staff_designation_input = QLineEdit()
        self.staff_designation_input.setPlaceholderText("e.g., Teacher, Principal, Clerk")
        self.staff_designation_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Designation:*", self.staff_designation_input)
        
        # Qualification
        self.staff_qualification_input = QLineEdit()
        self.staff_qualification_input.setPlaceholderText("Enter qualification")
        self.staff_qualification_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Qualification:", self.staff_qualification_input)
        
        # Department
        self.staff_department_input = QLineEdit()
        self.staff_department_input.setPlaceholderText("e.g., Science, Mathematics, Administration")
        self.staff_department_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Department:", self.staff_department_input)
        
        # Joining Date
        self.staff_joining_input = QDateEdit()
        self.staff_joining_input.setCalendarPopup(True)
        self.staff_joining_input.setDate(QDate.currentDate())
        self.staff_joining_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Joining Date:*", self.staff_joining_input)
        
        # Salary
        self.staff_salary_input = QDoubleSpinBox()
        self.staff_salary_input.setRange(0, 1000000)
        self.staff_salary_input.setPrefix("₹ ")
        self.staff_salary_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Salary:*", self.staff_salary_input)
        
        # Address
        self.staff_address_input = QTextEdit()
        self.staff_address_input.setPlaceholderText("Enter address")
        self.staff_address_input.setMaximumHeight(80)
        self.staff_address_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Address:", self.staff_address_input)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Staff")
        save_btn.setStyleSheet(self.get_button_style("#06d6a0"))
        save_btn.clicked.connect(self.save_staff)
        button_layout.addWidget(save_btn)
        
        clear_btn = QPushButton("🔄 Clear Form")
        clear_btn.setStyleSheet(self.get_button_style("#6c757d"))
        clear_btn.clicked.connect(self.clear_staff_form)
        button_layout.addWidget(clear_btn)
        
        layout.addLayout(button_layout)
        layout.addStretch()
        
        # Generate staff ID
        self.generate_staff_id()
        
        return tab
    
    def create_staff_list_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Search
        search_layout = QHBoxLayout()
        
        self.staff_search_input = QLineEdit()
        self.staff_search_input.setPlaceholderText("🔍 Search by name or staff ID...")
        self.staff_search_input.setStyleSheet(self.get_input_style())
        self.staff_search_input.textChanged.connect(self.filter_staff)
        search_layout.addWidget(self.staff_search_input)
        
        export_btn = QPushButton("📄 Export PDF")
        export_btn.setStyleSheet(self.get_button_style("#00b4d8"))
        export_btn.clicked.connect(self.export_staff_report)
        search_layout.addWidget(export_btn)
        
        layout.addLayout(search_layout)
        
        # Table
        self.staff_table = QTableWidget()
        self.staff_table.setColumnCount(9)
        self.staff_table.setHorizontalHeaderLabels([
            "Staff ID", "Name", "Phone", "Email", "Designation",
            "Department", "Joining Date", "Salary", "Actions"
        ])
        self.staff_table.horizontalHeader().setStretchLastSection(True)
        self.staff_table.setAlternatingRowColors(True)
        self.staff_table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background: #06d6a0;
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.staff_table)
        
        # Load staff
        self.load_staff()
        
        return tab
    
    def create_salary_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        # Staff selection
        self.salary_staff_combo = QComboBox()
        self.salary_staff_combo.setStyleSheet(self.get_input_style())
        self.salary_staff_combo.currentTextChanged.connect(self.update_salary_amount)
        form_layout.addRow("Select Staff:*", self.salary_staff_combo)
        
        # Amount
        self.salary_amount_input = QDoubleSpinBox()
        self.salary_amount_input.setRange(0, 1000000)
        self.salary_amount_input.setPrefix("₹ ")
        self.salary_amount_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Amount:*", self.salary_amount_input)
        
        # Month
        self.salary_month_combo = QComboBox()
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        self.salary_month_combo.addItems(months)
        self.salary_month_combo.setCurrentText(datetime.now().strftime("%B"))
        self.salary_month_combo.setStyleSheet(self.get_input_style())
        form_layout.addRow("Month:*", self.salary_month_combo)
        
        # Year
        self.salary_year_combo = QComboBox()
        self.salary_year_combo.addItems([str(y) for y in range(2024, 2036)])
        self.salary_year_combo.setCurrentText(str(datetime.now().year))
        self.salary_year_combo.setStyleSheet(self.get_input_style())
        form_layout.addRow("Year:*", self.salary_year_combo)
        
        # Payment Date
        self.salary_date_input = QDateEdit()
        self.salary_date_input.setCalendarPopup(True)
        self.salary_date_input.setDate(QDate.currentDate())
        self.salary_date_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Payment Date:*", self.salary_date_input)
        
        layout.addLayout(form_layout)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Record")
        save_btn.setStyleSheet(self.get_button_style("#06d6a0"))
        save_btn.clicked.connect(self.save_salary_payment)
        button_layout.addWidget(save_btn)
        
        receipt_btn = QPushButton("🖨️ Save and Print Receipt")
        receipt_btn.setStyleSheet(self.get_button_style("#667eea"))
        receipt_btn.clicked.connect(self.save_and_print_salary_receipt)
        button_layout.addWidget(receipt_btn)
        
        layout.addLayout(button_layout)
        layout.addStretch()
        
        # Load staff list
        self.load_staff_for_salary()
        
        return tab
    
    def create_salary_history_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Filters
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Month:"))
        self.history_month_combo = QComboBox()
        self.history_month_combo.addItem("All")
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        self.history_month_combo.addItems(months)
        self.history_month_combo.setStyleSheet(self.get_input_style())
        self.history_month_combo.currentTextChanged.connect(self.load_salary_history)
        filter_layout.addWidget(self.history_month_combo)
        
        filter_layout.addWidget(QLabel("Year:"))
        self.history_year_combo = QComboBox()
        self.history_year_combo.addItem("All")
        self.history_year_combo.addItems([str(y) for y in range(2024, 2036)])
        self.history_year_combo.setStyleSheet(self.get_input_style())
        self.history_year_combo.currentTextChanged.connect(self.load_salary_history)
        filter_layout.addWidget(self.history_year_combo)
        
        filter_layout.addStretch()
        
        self.total_expenses_label = QLabel("Total Expenses: ₹0.00")
        self.total_expenses_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #06d6a0;
        """)
        filter_layout.addWidget(self.total_expenses_label)
        
        export_btn = QPushButton("📄 Export PDF")
        export_btn.setStyleSheet(self.get_button_style("#00b4d8"))
        export_btn.clicked.connect(self.export_salary_history)
        filter_layout.addWidget(export_btn)
        
        layout.addLayout(filter_layout)
        
        # Table
        self.salary_history_table = QTableWidget()
        self.salary_history_table.setColumnCount(7)
        self.salary_history_table.setHorizontalHeaderLabels([
            "ID", "Staff Name", "Amount", "Month", "Year", "Payment Date", "Actions"
        ])
        self.salary_history_table.horizontalHeader().setStretchLastSection(True)
        self.salary_history_table.setAlternatingRowColors(True)
        self.salary_history_table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background: #06d6a0;
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.salary_history_table)
        
        # Load history
        self.load_salary_history()
        
        return tab
    
    def create_staff_backup_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Backup section
        backup_group = QGroupBox("Backup Staff Data")
        backup_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #06d6a0;
                border: 2px solid #06d6a0;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setSpacing(15)
        
        backup_desc = QLabel("Export all staff data to a JSON file for backup purposes.")
        backup_desc.setWordWrap(True)
        backup_layout.addWidget(backup_desc)
        
        backup_btn = QPushButton("💾 Backup Staff Data")
        backup_btn.setStyleSheet(self.get_button_style("#06d6a0"))
        backup_btn.clicked.connect(self.backup_staff)
        backup_layout.addWidget(backup_btn)
        
        layout.addWidget(backup_group)
        
        # Restore section
        restore_group = QGroupBox("Restore Staff Data")
        restore_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #f5576c;
                border: 2px solid #f5576c;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        restore_layout = QVBoxLayout(restore_group)
        restore_layout.setSpacing(15)
        
        restore_desc = QLabel("Import staff data from a backup JSON file.")
        restore_desc.setWordWrap(True)
        restore_layout.addWidget(restore_desc)
        
        restore_btn = QPushButton("📂 Choose File and Restore")
        restore_btn.setStyleSheet(self.get_button_style("#f5576c"))
        restore_btn.clicked.connect(self.restore_staff)
        restore_layout.addWidget(restore_btn)
        
        layout.addWidget(restore_group)
        layout.addStretch()
        
        return tab
    
    def generate_staff_id(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM staff")
        count = cursor.fetchone()[0]
        conn.close()
        
        staff_id = f"STF{str(count + 1).zfill(6)}"
        self.staff_id_input.setText(staff_id)
    
    def save_staff(self):
        # Validate
        if not self.staff_name_input.text():
            QMessageBox.warning(self, "Validation Error", "Please enter staff name!")
            return
        
        if not self.staff_phone_input.text():
            QMessageBox.warning(self, "Validation Error", "Please enter phone number!")
            return
        
        if not self.staff_designation_input.text():
            QMessageBox.warning(self, "Validation Error", "Please enter designation!")
            return
        
        # Save to database
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO staff (
                    staff_id, name, phone, email, designation, qualification,
                    department, joining_date, salary, address, session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.staff_id_input.text(),
                self.staff_name_input.text(),
                self.staff_phone_input.text(),
                self.staff_email_input.text(),
                self.staff_designation_input.text(),
                self.staff_qualification_input.text(),
                self.staff_department_input.text(),
                self.staff_joining_input.date().toString("yyyy-MM-dd"),
                self.staff_salary_input.value(),
                self.staff_address_input.toPlainText(),
                self.current_session
            ))
            
            conn.commit()
            QMessageBox.information(self, "Success", "Staff member added successfully!")
            self.clear_staff_form()
            if hasattr(self, 'load_staff'):
                self.load_staff()
            if hasattr(self, 'load_staff_for_salary'):
                self.load_staff_for_salary()
            # Force refresh home data
            QTimer.singleShot(100, self.refresh_home_data)
            
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Error", "Staff ID already exists!")
        finally:
            conn.close()
    
    def clear_staff_form(self):
        self.staff_name_input.clear()
        self.staff_phone_input.clear()
        self.staff_email_input.clear()
        self.staff_designation_input.clear()
        self.staff_qualification_input.clear()
        self.staff_department_input.clear()
        self.staff_address_input.clear()
        self.staff_salary_input.setValue(0)
        self.staff_joining_input.setDate(QDate.currentDate())
        self.generate_staff_id()
    
    def load_staff(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff WHERE session = ? ORDER BY name", (self.current_session,))
        staff = cursor.fetchall()
        conn.close()
        
        self.staff_table.setRowCount(0)
        
        for row_idx, s in enumerate(staff):
            self.staff_table.insertRow(row_idx)
            
            self.staff_table.setItem(row_idx, 0, QTableWidgetItem(s[1]))  # Staff ID
            self.staff_table.setItem(row_idx, 1, QTableWidgetItem(s[2]))  # Name
            self.staff_table.setItem(row_idx, 2, QTableWidgetItem(s[3]))  # Phone
            self.staff_table.setItem(row_idx, 3, QTableWidgetItem(s[4]))  # Email
            self.staff_table.setItem(row_idx, 4, QTableWidgetItem(s[5]))  # Designation
            self.staff_table.setItem(row_idx, 5, QTableWidgetItem(s[7]))  # Department
            self.staff_table.setItem(row_idx, 6, QTableWidgetItem(s[8]))  # Joining Date
            self.staff_table.setItem(row_idx, 7, QTableWidgetItem(f"₹{s[9]:.2f}"))  # Salary
            
            # Action buttons
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(5, 5, 5, 5)
            action_layout.setSpacing(5)
            
            delete_btn = QPushButton("🗑️")
            delete_btn.setStyleSheet("background: #f44336; color: white; border: none; padding: 5px; border-radius: 5px;")
            delete_btn.clicked.connect(lambda checked, staff=s: self.delete_staff(staff))
            action_layout.addWidget(delete_btn)
            
            self.staff_table.setCellWidget(row_idx, 8, action_widget)
    
    def filter_staff(self):
        search_text = self.staff_search_input.text().lower()
        
        for row in range(self.staff_table.rowCount()):
            show_row = True
            
            if search_text:
                name = self.staff_table.item(row, 1).text().lower()
                staff_id = self.staff_table.item(row, 0).text().lower()
                if search_text not in name and search_text not in staff_id:
                    show_row = False
            
            self.staff_table.setRowHidden(row, not show_row)
    
    def delete_staff(self, staff):
        reply = QMessageBox.question(self, "Delete Staff",
                                    f"Are you sure you want to delete {staff[2]}?",
                                    QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM staff WHERE id = ?", (staff[0],))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Success", "Staff member deleted successfully!")
            self.load_staff()
            self.load_staff_for_salary()
            self.refresh_home_data()
    
    def load_staff_for_salary(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT staff_id, name, salary FROM staff WHERE session = ? ORDER BY name", 
                      (self.current_session,))
        staff = cursor.fetchall()
        conn.close()
        
        self.salary_staff_combo.clear()
        self.staff_salary_map = {}
        
        for s in staff:
            display_text = f"{s[1]} ({s[0]})"
            self.salary_staff_combo.addItem(display_text)
            self.staff_salary_map[display_text] = (s[0], s[1], s[2])
    
    def update_salary_amount(self, text):
        if text in self.staff_salary_map:
            salary = self.staff_salary_map[text][2]
            self.salary_amount_input.setValue(salary)
    
    def save_salary_payment(self):
        if not self.salary_staff_combo.currentText():
            QMessageBox.warning(self, "Validation Error", "Please select a staff member!")
            return
        
        staff_info = self.staff_salary_map[self.salary_staff_combo.currentText()]
        staff_id = staff_info[0]
        staff_name = staff_info[1]
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO salary_payments (
                staff_id, staff_name, amount, payment_date, month, year, session
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            staff_id,
            staff_name,
            self.salary_amount_input.value(),
            self.salary_date_input.date().toString("yyyy-MM-dd"),
            self.salary_month_combo.currentText(),
            self.salary_year_combo.currentText(),
            self.current_session
        ))
        
        conn.commit()
        conn.close()
        
        QMessageBox.information(self, "Success", "Salary payment recorded successfully!")
        if hasattr(self, 'load_salary_history'):
            self.load_salary_history()
        # Force refresh home data
        QTimer.singleShot(100, self.refresh_home_data)
    
    def save_and_print_salary_receipt(self):
        self.calculate_total_fee()
        if not self.salary_staff_combo.currentText():
            QMessageBox.warning(self, "Validation Error", "Please select a staff member!")
            return

        # Save first
        self.save_salary_payment()

    # Generate receipt
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Receipt")
        if not folder:
            return

        staff_info = self.staff_salary_map[self.salary_staff_combo.currentText()]
        staff_name = staff_info[1]
        staff_id = staff_info[0]
    
    # Get additional staff details if available
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT department, designation, email, phone FROM staff WHERE staff_id = ?", (staff_id,))
            staff_details = cursor.fetchone()
            conn.close()
        
            if staff_details:
                department, designation, email, phone = staff_details
            else:
                department = designation = email = phone = "N/A"
        except:
            department = designation = email = phone = "N/A"

        school_name = self.db.get_setting('school_name') or "School ERP"
        school_address = self.db.get_setting('school_address') or ""
        school_email = self.db.get_setting('school_email') or ""
        school_phone = self.db.get_setting('school_phone') or ""

        filename = os.path.join(folder, f"Salary_Receipt_{staff_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf")

        # Use full A4 page for better formatting
        doc = SimpleDocTemplate(
            filename,
            pagesize=A4,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )
        elements = []
        styles = getSampleStyleSheet()

    # School header with improved styling
        school_style = ParagraphStyle(
            'SchoolName',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.black,
            alignment=TA_CENTER,
            spaceAfter=5,
            fontName='Helvetica-Bold'
        )
        elements.append(Paragraph(school_name, school_style))

    # School address and contact
        if school_address:
            addr_style = ParagraphStyle(
                'Address',
                parent=styles['Normal'],
                alignment=TA_CENTER,
                fontSize=10,
                spaceAfter=3
            )
            elements.append(Paragraph(school_address, addr_style))

        if school_email or school_phone:
            contact_style = ParagraphStyle(
                'Contact',
                parent=styles['Normal'],
                alignment=TA_CENTER,
                fontSize=9,
                spaceAfter=15
            )
            contact_info = []
            if school_email:
                contact_info.append(f"Email: {school_email}")
            if school_phone:
                contact_info.append(f"Phone: {school_phone}")
            elements.append(Paragraph(" | ".join(contact_info), contact_style))
    
        elements.append(Spacer(1, 10))

        # SALARY RECEIPT Title with border
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=15,
            fontName='Helvetica-Bold',
            borderWidth=2,
            borderColor=colors.black,
            borderPadding=10
        )
        elements.append(Paragraph("SALARY RECEIPT", title_style))
        elements.append(Spacer(1, 15))

        # Receipt header info
        receipt_data = [
            ['Receipt No.', f"SAL-{datetime.now().strftime('%Y%m%d%H%M%S')}", 'Payment Date:', self.salary_date_input.date().toString("dd-MM-yyyy")]
        ]

        receipt_table = Table(receipt_data, colWidths=[2 * inch, 2 * inch, 1.5 * inch, 2 * inch])
        receipt_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(receipt_table)
    
        elements.append(Spacer(1, 15))

        # Employee details
        employee_data = [
            ['Employee Name:', staff_name],
            ['Employee ID:', staff_id],
            ['Department:', department],
            ['Designation:', designation],
            ['Email:', email],
            ['Phone:', phone],
        ]

        employee_table = Table(employee_data, colWidths=[2.5 * inch, 4 * inch])
        employee_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(employee_table)
    
        elements.append(Spacer(1, 15))

        # Salary details
        salary_data = [
            ['Salary Details', ''],
            ['Month:', self.salary_month_combo.currentText()],
            ['Year:', self.salary_year_combo.currentText()],
            ['Basic Salary:', f"₹{self.salary_amount_input.value():.2f}"],
            ['Deductions:', '₹0.00'],
            ['Net Salary:', f"₹{self.salary_amount_input.value():.2f}"],
        ]
    
        salary_table = Table(salary_data, colWidths=[2.5 * inch, 4 * inch])
        salary_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('BACKGROUND', (0, 0), (1, 0), colors.lightgrey),
        ]))
        elements.append(salary_table)
    
        elements.append(Spacer(1, 20))

        # Amount in words
        try:
            from num2words import num2words
            amount = int(self.salary_amount_input.value())
            amount_words = num2words(amount, lang='en_IN').title() + " Only"
        except:
            amount_words = "Amount in words"
    
        words_style = ParagraphStyle(
            'Words',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=30
        )
        elements.append(Paragraph(f"Rupees {amount_words}", words_style))
    
        # Signature section
        elements.append(Spacer(1, 40))
        sig_data = [
            ['Employee Signature', '', 'Authorized Signature'],
            ['_________________', '', '_________________'],
        ]
        sig_table = Table(sig_data, colWidths=[2.5 * inch, 2 * inch, 2.5 * inch])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('FONTNAME', (0, 0), (0, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (0, 1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
            ('FONTNAME', (2, 1), (2, 1), 'Helvetica-Bold'),
        ]))
        elements.append(sig_table)

        # Footer
        elements.append(Spacer(1, 20))
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            alignment=TA_CENTER,
            fontSize=8,
            textColor=colors.grey
        )
        elements.append(Paragraph("This is a computer-generated receipt and does not require signature.",     footer_style))
    
        doc.build(elements)
    
        QMessageBox.information(self, "Success", f"Receipt saved to:{filename}")
    def load_salary_history(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        month_filter = self.history_month_combo.currentText()
        year_filter = self.history_year_combo.currentText()
        
        query = "SELECT * FROM salary_payments WHERE session = ?"
        params = [self.current_session]
        
        if month_filter != "All":
            query += " AND month = ?"
            params.append(month_filter)
        
        if year_filter != "All":
            query += " AND year = ?"
            params.append(year_filter)
        
        query += " ORDER BY payment_date DESC"
        
        cursor.execute(query, params)
        payments = cursor.fetchall()
        conn.close()
        
        self.salary_history_table.setRowCount(0)
        total = 0
        
        for row_idx, payment in enumerate(payments):
            self.salary_history_table.insertRow(row_idx)
            
            self.salary_history_table.setItem(row_idx, 0, QTableWidgetItem(str(payment[0])))
            self.salary_history_table.setItem(row_idx, 1, QTableWidgetItem(payment[2]))
            self.salary_history_table.setItem(row_idx, 2, QTableWidgetItem(f"₹{payment[3]:.2f}"))
            self.salary_history_table.setItem(row_idx, 3, QTableWidgetItem(payment[5]))
            self.salary_history_table.setItem(row_idx, 4, QTableWidgetItem(payment[6]))
            self.salary_history_table.setItem(row_idx, 5, QTableWidgetItem(payment[4]))
            
            total += payment[3]
            
            # Action buttons
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(5, 5, 5, 5)
            action_layout.setSpacing(5)
            
            delete_btn = QPushButton("🗑️")
            delete_btn.setStyleSheet("background: #f44336; color: white; border: none; padding: 5px; border-radius: 5px;")
            delete_btn.clicked.connect(lambda checked, p=payment: self.delete_salary_payment(p))
            action_layout.addWidget(delete_btn)
            
            self.salary_history_table.setCellWidget(row_idx, 6, action_widget)
        
        self.total_expenses_label.setText(f"Total Expenses: ₹{total:.2f}")
    
    def delete_salary_payment(self, payment):
        reply = QMessageBox.question(self, "Delete Payment",
                                    "Are you sure you want to delete this payment record?",
                                    QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM salary_payments WHERE id = ?", (payment[0],))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Success", "Payment record deleted successfully!")
            self.load_salary_history()
            self.refresh_home_data()
    
    def export_salary_history(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Report")
        if not folder:
            return
        
        self.export_expenses_report()
    
    def backup_staff(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Backup")
        if not folder:
            return
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM staff WHERE session = ?", (self.current_session,))
        staff = cursor.fetchall()
        conn.close()
        
        staff_data = []
        for s in staff:
            staff_data.append({
                'staff_id': s[1],
                'name': s[2],
                'phone': s[3],
                'email': s[4],
                'designation': s[5],
                'qualification': s[6],
                'department': s[7],
                'joining_date': s[8],
                'salary': s[9],
                'address': s[10],
                'session': s[11]
            })
        
        filename = os.path.join(folder, f"staff_backup_{self.current_session}.json")
        with open(filename, 'w') as f:
            json.dump(staff_data, f, indent=4)
        
        QMessageBox.information(self, "Success", f"Backup saved to:\n{filename}")
    
    def restore_staff(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Select Backup File", "", "JSON Files (*.json)")
        if not filename:
            return
        
        try:
            with open(filename, 'r') as f:
                staff_data = json.load(f)
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            restored_count = 0
            for staff in staff_data:
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO staff (
                            staff_id, name, phone, email, designation, qualification,
                            department, joining_date, salary, address, session
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        staff['staff_id'],
                        staff['name'],
                        staff['phone'],
                        staff['email'],
                        staff['designation'],
                        staff['qualification'],
                        staff['department'],
                        staff['joining_date'],
                        staff['salary'],
                        staff['address'],
                        self.current_session
                    ))
                    restored_count += 1
                except:
                    pass
            
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Success", f"Restored {restored_count} staff members successfully!")
            self.load_staff()
            self.load_staff_for_salary()
            self.refresh_home_data()
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restore backup:\n{str(e)}")
    
    def create_fees_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Page title
        title = QLabel("Fee Management")
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: #333;
        """)
        layout.addWidget(title)
        
        # Tab widget
        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                background: white;
                border-radius: 10px;
            }
            QTabBar::tab {
                background: #f0f0f0;
                color: #333;
                padding: 10px 20px;
                margin-right: 5px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            QTabBar::tab:selected {
                background: white;
                color: #f5576c;
                font-weight: bold;
            }
        """)
        
        # Collect Fee Tab
        collect_tab = self.create_collect_fee_tab()
        tabs.addTab(collect_tab, "💰 Collect Fee")
        
        # All Records Tab
        records_tab = self.create_fee_records_tab()
        tabs.addTab(records_tab, "📋 All Records")
        
        # Paid/Unpaid Tab
        reports_tab = self.create_fee_reports_tab()
        tabs.addTab(reports_tab, "📊 Paid/Unpaid Reports")
        
        layout.addWidget(tabs)
        
        return page
    
    def create_collect_fee_tab(self):
        tab = QWidget()
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; }")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Form
        form_layout = QFormLayout()
        form_layout.setSpacing(15)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        # Receipt Number
        self.fee_receipt_input = QLineEdit()
        self.fee_receipt_input.setPlaceholderText("Auto-generated")
        self.fee_receipt_input.setReadOnly(True)
        self.fee_receipt_input.setStyleSheet(self.get_input_style())
        form_layout.addRow("Receipt Number:", self.fee_receipt_input)
        
        # Student Selection Button
        student_select_layout = QHBoxLayout()
        self.fee_student_button = QPushButton("🔍 Select Student")
        self.fee_student_button.setStyleSheet("""
            QPushButton {
                background: #667eea;
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 20px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background: #5a67d8;
            }
        """)
        self.fee_student_button.clicked.connect(self.open_student_selection_dialog)
        student_select_layout.addWidget(self.fee_student_button)
        student_select_layout.addStretch()
        
        form_layout.addRow("Select Student:*", student_select_layout)
        
        # Student details (auto-filled)
        self.fee_student_name = QLineEdit()
        self.fee_student_name.setReadOnly(True)
        self.fee_student_name.setPlaceholderText("Select a student first")
        self.fee_student_name.setStyleSheet(self.get_input_style())
        
        self.fee_class = QLineEdit()
        self.fee_class.setReadOnly(True)
        self.fee_class.setPlaceholderText("Auto-filled")
        self.fee_class.setStyleSheet(self.get_input_style())
        
        self.fee_section = QLineEdit()
        self.fee_section.setReadOnly(True)
        self.fee_section.setPlaceholderText("Auto-filled")
        self.fee_section.setStyleSheet(self.get_input_style())
        
        self.fee_parent_name = QLineEdit()
        self.fee_parent_name.setReadOnly(True)
        self.fee_parent_name.setPlaceholderText("Auto-filled")
        self.fee_parent_name.setStyleSheet(self.get_input_style())  
        
        # Months selection
        self.fee_months_list = QListWidget()
        self.fee_months_list.setSelectionMode(QListWidget.MultiSelection)
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        self.fee_months_list.addItems(months)
        self.fee_months_list.setMaximumHeight(150)
        self.fee_months_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 8px;
            }
            QListWidget::item:selected {
                background: #667eea;
                color: white;
            }
        """)
        form_layout.addRow("Select Months:*", self.fee_months_list)
        
        # Payment Date
        self.fee_payment_date = QDateEdit()
        self.fee_payment_date.setCalendarPopup(True)
        self.fee_payment_date.setDate(QDate.currentDate())
        self.fee_payment_date.setStyleSheet(self.get_input_style())
        form_layout.addRow("Payment Date:*", self.fee_payment_date)
        
        # Fee components
        self.fee_tuition = QDoubleSpinBox()
        self.fee_tuition.setRange(0, 100000)
        self.fee_tuition.setPrefix("₹ ")
        self.fee_tuition.setStyleSheet(self.get_input_style())
        self.fee_tuition.valueChanged.connect(self.calculate_total_fee)
        form_layout.addRow("Tuition Fee:", self.fee_tuition)
        
        self.fee_lab = QDoubleSpinBox()
        self.fee_lab.setRange(0, 100000)
        self.fee_lab.setPrefix("₹ ")
        self.fee_lab.setStyleSheet(self.get_input_style())
        self.fee_lab.valueChanged.connect(self.calculate_total_fee)
        form_layout.addRow("Lab Fee:", self.fee_lab)
        
        self.fee_sport = QDoubleSpinBox()
        self.fee_sport.setRange(0, 100000)
        self.fee_sport.setPrefix("₹ ")
        self.fee_sport.setStyleSheet(self.get_input_style())
        self.fee_sport.valueChanged.connect(self.calculate_total_fee)
        form_layout.addRow("Sport Fee:", self.fee_sport)
        
        self.fee_computer = QDoubleSpinBox()
        self.fee_computer.setRange(0, 100000)
        self.fee_computer.setPrefix("₹ ")
        self.fee_computer.setStyleSheet(self.get_input_style())
        self.fee_computer.valueChanged.connect(self.calculate_total_fee)
        form_layout.addRow("Computer Fee:", self.fee_computer)
        
        self.fee_maintenance = QDoubleSpinBox()
        self.fee_maintenance.setRange(0, 100000)
        self.fee_maintenance.setPrefix("₹ ")
        self.fee_maintenance.setStyleSheet(self.get_input_style())
        self.fee_maintenance.valueChanged.connect(self.calculate_total_fee)
        form_layout.addRow("Maintenance Fee:", self.fee_maintenance)
        
        self.fee_exam = QDoubleSpinBox()
        self.fee_exam.setRange(0, 100000)
        self.fee_exam.setPrefix("₹ ")
        self.fee_exam.setStyleSheet(self.get_input_style())
        self.fee_exam.valueChanged.connect(self.calculate_total_fee)
        form_layout.addRow("Exam Fee:", self.fee_exam)
        

        
        self.fee_late = QDoubleSpinBox()
        self.fee_late.setRange(0, 100000)
        self.fee_late.setPrefix("₹ ")
        self.fee_late.setStyleSheet(self.get_input_style())
        self.fee_late.valueChanged.connect(self.calculate_total_fee)
        form_layout.addRow("Late Fee:", self.fee_late)
        
        # Total Amount
        self.fee_total = QLineEdit()
        self.fee_total.setReadOnly(True)
        self.fee_total.setStyleSheet("""
            QLineEdit {
                background: #f0f0f0;
                border: 2px solid #667eea;
                border-radius: 8px;
                padding: 10px;
                font-size: 16px;
                font-weight: bold;
                color: #667eea;
            }
        """)
        form_layout.addRow("Total Amount:", self.fee_total)
        
        # Payment Mode
        self.fee_payment_mode = QComboBox()
        self.fee_payment_mode.addItems(["Cash", "Online", "Cheque", "Card"])
        self.fee_payment_mode.setStyleSheet(self.get_input_style())
        form_layout.addRow("Payment Mode:*", self.fee_payment_mode)
        
        # Payment Status
        status_layout = QHBoxLayout()
        self.fee_status_full = QRadioButton("Full Paid")
        self.fee_status_full.setChecked(True)
        self.fee_status_partial = QRadioButton("Partial Paid")
        status_layout.addWidget(self.fee_status_full)
        status_layout.addWidget(self.fee_status_partial)
        status_layout.addStretch()
        form_layout.addRow("Payment Status:*", status_layout)
        
        layout.addLayout(form_layout)
        layout.addWidget(self.fee_student_name)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        save_btn = QPushButton("💾 Save Record")
        save_btn.setStyleSheet(self.get_button_style("#f5576c"))
        save_btn.clicked.connect(self.save_fee_record)
        button_layout.addWidget(save_btn)
        
        print_btn = QPushButton("🖨️ Save And Print Receipt")
        print_btn.setStyleSheet(self.get_button_style("#667eea"))
        print_btn.clicked.connect(self.save_and_print_fee_receipt)
        button_layout.addWidget(print_btn)
        
        clear_btn = QPushButton("🔄 Clear Form")
        clear_btn.setStyleSheet(self.get_button_style("#6c757d"))
        clear_btn.clicked.connect(self.clear_fee_form)
        button_layout.addWidget(clear_btn)
        
        layout.addLayout(button_layout)
        
        scroll.setWidget(content)
        
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.addWidget(scroll)
        
        # Generate receipt number
        self.generate_receipt_number()
        
        # Initialize selected student number
        self.selected_student_number = None
        
        return tab
    
    def open_student_selection_dialog(self):
        dialog = StudentSelectionDialog(self, self.db, self.current_session)
        if dialog.exec_() == QDialog.Accepted and dialog.selected_student:
            student = dialog.selected_student
            
            # Populate form fields
            self.fee_student_name.setText(student[1])  # full_name
            self.fee_class.setText(student[2])         # class
            self.fee_section.setText(student[3])       # section
            self.fee_parent_name.setText(student[4])   # parent_name
            
            # Store selected student number
            self.selected_student_number = student[0]  # student_number
            
            # Update button text
            self.fee_student_button.setText(f"✓ {student[1]} Selected")
            self.fee_student_button.setStyleSheet("""
                QPushButton {
                    background: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 8px;
                    padding: 12px 20px;
                    font-weight: bold;
                    font-size: 14px;
                }
                QPushButton:hover {
                    background: #45a049;
                }
            """)
    
    def get_input_style(self):
        return """
            QLineEdit, QComboBox, QDateEdit, QTextEdit, QSpinBox, QDoubleSpinBox {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                padding: 10px;
                font-size: 14px;
                color: #333;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
                border: 2px solid #667eea;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 10px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #667eea;
                margin-right: 5px;
            }
            QComboBox QAbstractItemView {
                background: white;
                color: #333;
                border: 1px solid #ddd;
                selection-background-color: #667eea;
                selection-color: white;
                outline: none;
            }
            QComboBox QAbstractItemView::item {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }
            QComboBox QAbstractItemView::item:hover {
                background: #f0f0f0;
                color: #333;
            }
            QComboBox QAbstractItemView::item:selected {
                background: #667eea;
                color: white;
            }
        """
    
    def get_button_style(self, color):
        return f"""
            QPushButton {{
                background: {color};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-weight: bold;
                font-size: 15px;
                min-width: 150px;
            }}
            QPushButton:hover {{
                background: {color}dd;
            }}
            QPushButton:pressed {{
                padding-top: 14px;
                padding-bottom: 10px;
            }}
        """
    
    
    
    def create_fee_records_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Filters
        filter_layout = QHBoxLayout()
        
        self.fee_records_search = QLineEdit()
        self.fee_records_search.setPlaceholderText("🔍 Search by student name or receipt number...")
        self.fee_records_search.setStyleSheet(self.get_input_style())
        self.fee_records_search.textChanged.connect(self.filter_fee_records)
        filter_layout.addWidget(self.fee_records_search)
        
        filter_layout.addWidget(QLabel("Month:"))
        self.fee_records_month = QComboBox()
        self.fee_records_month.addItem("All")
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        self.fee_records_month.addItems(months)
        self.fee_records_month.setStyleSheet(self.get_input_style())
        self.fee_records_month.currentTextChanged.connect(self.filter_fee_records)
        filter_layout.addWidget(self.fee_records_month)
        
        layout.addLayout(filter_layout)
        
        # Table
        self.fee_records_table = QTableWidget()
        self.fee_records_table.setColumnCount(9)
        self.fee_records_table.setHorizontalHeaderLabels([
            "Receipt No.", "Student", "Class", "Months", "Date", 
            "Amount", "Mode", "Status", "Actions"
        ])
        self.fee_records_table.horizontalHeader().setStretchLastSection(True)
        self.fee_records_table.setAlternatingRowColors(True)
        self.fee_records_table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background: #f5576c;
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.fee_records_table)
        
        # Load records
        self.load_fee_records()
        
        return tab
    
    def create_fee_reports_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Sub-tabs
        sub_tabs = QTabWidget()
        sub_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #ddd;
                background: white;
                border-radius: 10px;
            }
            QTabBar::tab {
                background: #f0f0f0;
                color: #333;
                padding: 8px 16px;
                margin-right: 3px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
            }
            QTabBar::tab:selected {
                background: white;
                color: #4CAF50;
                font-weight: bold;
            }
        """)
        
        # Paid Fees Tab
        paid_tab = self.create_paid_fees_tab()
        sub_tabs.addTab(paid_tab, "✅ Fees Paid")
        
        # Unpaid Fees Tab
        unpaid_tab = self.create_unpaid_fees_tab()
        sub_tabs.addTab(unpaid_tab, "❌ Fees Unpaid")
        
        layout.addWidget(sub_tabs)
        
        return tab
    
    def create_paid_fees_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Filters
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Month:"))
        self.paid_month_combo = QComboBox()
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        self.paid_month_combo.addItems(months)
        self.paid_month_combo.setCurrentText(datetime.now().strftime("%B"))
        self.paid_month_combo.setStyleSheet(self.get_input_style())
        filter_layout.addWidget(self.paid_month_combo)
        
        filter_layout.addWidget(QLabel("Class:"))
        self.paid_class_combo = QComboBox()
        self.paid_class_combo.addItem("All")
        classes = ["Nursery", "LKG", "UKG"] + [str(i) for i in range(1, 13)]
        self.paid_class_combo.addItems(classes)
        self.paid_class_combo.setStyleSheet(self.get_input_style())
        filter_layout.addWidget(self.paid_class_combo)
        
        filter_layout.addWidget(QLabel("Section:"))
        self.paid_section_combo = QComboBox()
        self.paid_section_combo.addItem("All")
        self.paid_section_combo.addItems([chr(i) for i in range(65, 73)])
        self.paid_section_combo.setStyleSheet(self.get_input_style())
        filter_layout.addWidget(self.paid_section_combo)
        
        load_btn = QPushButton("📋 Load Data")
        load_btn.setStyleSheet(self.get_button_style("#4CAF50"))
        load_btn.clicked.connect(self.load_paid_fees)
        filter_layout.addWidget(load_btn)
        
        export_btn = QPushButton("📄 Export PDF")
        export_btn.setStyleSheet(self.get_button_style("#00b4d8"))
        export_btn.clicked.connect(self.export_paid_fees)
        filter_layout.addWidget(export_btn)
        
        filter_layout.addStretch()
        
        layout.addLayout(filter_layout)
        
        # Table
        self.paid_fees_table = QTableWidget()
        self.paid_fees_table.setColumnCount(6)
        self.paid_fees_table.setHorizontalHeaderLabels([
            "Student No.", "Name", "Class", "Section", "Parent Name", "Amount Paid"
        ])
        self.paid_fees_table.horizontalHeader().setStretchLastSection(True)
        self.paid_fees_table.setAlternatingRowColors(True)
        self.paid_fees_table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background: #4CAF50;
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.paid_fees_table)
        
        # Footer
        self.paid_count_label = QLabel("Total Students: 0")
        self.paid_count_label.setStyleSheet("""
            font-size: 16px;
            font-weight: bold;
            color: #4CAF50;
        """)
        layout.addWidget(self.paid_count_label)
        
        return tab
    
    def create_unpaid_fees_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Filters
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("Month:"))
        self.unpaid_month_combo = QComboBox()
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        self.unpaid_month_combo.addItems(months)
        self.unpaid_month_combo.setCurrentText(datetime.now().strftime("%B"))
        self.unpaid_month_combo.setStyleSheet(self.get_input_style())
        filter_layout.addWidget(self.unpaid_month_combo)
        
        filter_layout.addWidget(QLabel("Class:"))
        self.unpaid_class_combo = QComboBox()
        self.unpaid_class_combo.addItem("All")
        classes = ["Nursery", "LKG", "UKG"] + [str(i) for i in range(1, 13)]
        self.unpaid_class_combo.addItems(classes)
        self.unpaid_class_combo.setStyleSheet(self.get_input_style())
        filter_layout.addWidget(self.unpaid_class_combo)
        
        filter_layout.addWidget(QLabel("Section:"))
        self.unpaid_section_combo = QComboBox()
        self.unpaid_section_combo.addItem("All")
        self.unpaid_section_combo.addItems([chr(i) for i in range(65, 73)])
        self.unpaid_section_combo.setStyleSheet(self.get_input_style())
        filter_layout.addWidget(self.unpaid_section_combo)
        
        load_btn = QPushButton("📋 Load Data")
        load_btn.setStyleSheet(self.get_button_style("#f44336"))
        load_btn.clicked.connect(self.load_unpaid_fees)
        filter_layout.addWidget(load_btn)
        
        export_btn = QPushButton("📄 Export PDF")
        export_btn.setStyleSheet(self.get_button_style("#00b4d8"))
        export_btn.clicked.connect(self.export_unpaid_fees)
        filter_layout.addWidget(export_btn)
        
        filter_layout.addStretch()
        
        layout.addLayout(filter_layout)
        
        # Table
        self.unpaid_fees_table = QTableWidget()
        self.unpaid_fees_table.setColumnCount(5)
        self.unpaid_fees_table.setHorizontalHeaderLabels([
            "Student No.", "Name", "Class", "Section", "Parent Name"
        ])
        self.unpaid_fees_table.horizontalHeader().setStretchLastSection(True)
        self.unpaid_fees_table.setAlternatingRowColors(True)
        self.unpaid_fees_table.setStyleSheet("""
            QTableWidget {
                background: white;
                border: 1px solid #ddd;
                border-radius: 8px;
                gridline-color: #e0e0e0;
            }
            QTableWidget::item {
                padding: 8px;
            }
            QHeaderView::section {
                background: #f44336;
                color: white;
                padding: 10px;
                border: none;
                font-weight: bold;
            }
        """)
        layout.addWidget(self.unpaid_fees_table)
        
        # Footer
        self.unpaid_count_label = QLabel("Total Students: 0")
        self.unpaid_count_label.setStyleSheet("""
            font-size: 15px;
            font-weight: bold;
            color: #f44336;
        """)
        layout.addWidget(self.unpaid_count_label)
        
        return tab
    
    def generate_receipt_number(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Get highest receipt number
        cursor.execute("""
            SELECT receipt_number FROM fee_payments 
            WHERE receipt_number LIKE 'REC%' 
            ORDER BY CAST(SUBSTR(receipt_number, 4) AS INTEGER) DESC 
            LIMIT 1
        """)
        result = cursor.fetchone()
        
        if result:
            last_number = int(result[0][3:])  # Remove 'REC' prefix
            new_number = last_number + 1
        else:
            new_number = 1
        
        conn.close()
        
        receipt_number = f"REC{str(new_number).zfill(6)}"
        self.fee_receipt_input.setText(receipt_number)
    
    def search_student_for_fee(self, text):
        if len(text) < 1:
            self.fee_student_list.hide()
            self.fee_student_list.clear()
            return
        
        try:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT student_number, full_name, class, section, parent_name 
                FROM students 
                WHERE (full_name LIKE ? OR student_number LIKE ?) AND session = ?
                ORDER BY full_name
                LIMIT 10
            """, (f"%{text}%", f"%{text}%", self.current_session))
            
            students = cursor.fetchall()
            conn.close()
            
            self.fee_student_list.clear()
            
            if students and len(students) > 0:
                for student in students:
                    item_text = f"{student[1]} ({student[0]}) - Class {student[2]}-{student[3]}"
                    item = QListWidgetItem(item_text)
                    item.setData(Qt.UserRole, student)
                    self.fee_student_list.addItem(item)
                
                # Show the list and adjust height
                self.fee_student_list.show()
                item_count = min(len(students), 5)  # Show max 5 items
                item_height = 35  # Height per item
                self.fee_student_list.setFixedHeight(item_count * item_height + 10)
            else:
                self.fee_student_list.hide()
                
        except Exception as e:
            print(f"Error searching students: {e}")
            traceback.print_exc()
            self.fee_student_list.hide()
    
    def select_student_for_fee(self):
        """Open student selection dialog and populate fee form"""
        dialog = StudentSelectionDialog(self, self.db, self.current_session)
    
        if dialog.exec_() == QDialog.Accepted and dialog.selected_student:
            student = dialog.selected_student
            
            # Store the selected student number
            self.selected_student_number = student[0]  # student_number
            
            # Populate ALL form fields with student data
            self.fee_student_name.setText(student[1])      # full_name
            self.fee_class.setText(student[2])             # class
            self.fee_section.setText(student[3])           # section
            self.fee_parent_name.setText(student[4])       # parent_name
            
            # Enable the form fields for editing if needed
            self.fee_student_name.setReadOnly(False)
            self.fee_class.setReadOnly(False)
            self.fee_section.setReadOnly(False)
            self.fee_parent_name.setReadOnly(False)
            
            # Show success message
            QMessageBox.information(
                self, 
                "Student Selected", 
                f"Student {student[1]} selected successfully!\nPlease enter fee details and select months."
            )
    
    def calculate_total_fee(self):
        total = (self.fee_tuition.value() + self.fee_lab.value() + 
                self.fee_sport.value() + self.fee_computer.value() +
                self.fee_maintenance.value() + self.fee_exam.value() + self.fee_late.value())
        
        self.fee_total.setText(f"₹{total:.2f}")
    
    def save_fee_record(self):
        if not hasattr(self, 'selected_student_number'):
            QMessageBox.warning(self, "Validation Error", "Please select a student!")
            return
        
        selected_months = [item.text() for item in self.fee_months_list.selectedItems()]
        if not selected_months:
            QMessageBox.warning(self, "Validation Error", "Please select at least one month!")
            return
        
        months_str = ", ".join(selected_months)
        status = "Full Paid" if self.fee_status_full.isChecked() else "Partial Paid"
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute("""
                INSERT INTO fee_payments (
                    receipt_number, student_number, student_name, class, section,
                    parent_name, months, payment_date, tuition_fee, lab_fee,
                    sport_fee, computer_fee, maintenance_fee, exam_fee,
                    late_fee, total_amount, payment_mode, payment_status, session
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.fee_receipt_input.text(),
                self.selected_student_number,
                self.fee_student_name.text(),
                self.fee_class.text(),
                self.fee_section.text(),
                self.fee_parent_name.text(),
                months_str,
                self.fee_payment_date.date().toString("yyyy-MM-dd"),
                self.fee_tuition.value(),
                self.fee_lab.value(),
                self.fee_sport.value(),
                self.fee_computer.value(),
                self.fee_maintenance.value(),
                self.fee_exam.value(),
                self.fee_late.value(),
                float(self.fee_total.text().replace('₹', '').replace(',', '').strip() or 0),
                self.fee_payment_mode.currentText(),
                status,
                self.current_session
            ))
            
            conn.commit()
            QMessageBox.information(self, "Success", "Fee record saved successfully!")
            self.clear_fee_form()
            if hasattr(self, 'load_fee_records'):
                self.load_fee_records()
            # Force refresh home data
            QTimer.singleShot(100, self.refresh_home_data)
            
        except sqlite3.IntegrityError:
            QMessageBox.warning(self, "Error", "Receipt number already exists!")
        finally:
            conn.close()
    
    def save_and_print_fee_receipt(self):
        """Save and print new fee receipt in the same format as print_fee_receipt"""
        
        # --- STEP 1: VALIDATE STUDENT SELECTION ---
        if not hasattr(self, 'selected_student_number') or self.selected_student_number is None:
            QMessageBox.warning(self, "Validation Error", "Please select a student first!")
            return
        
        # --- STEP 2: VALIDATE FORM FIELDS ---
        student_name = self.fee_student_name.text().strip()
        parent_name = self.fee_parent_name.text().strip()
        student_class = self.fee_class.text().strip()
        student_section = self.fee_section.text().strip()
        
        if not student_name:
            QMessageBox.warning(self, "Validation Error", "Student name is missing! Please select a student first.")
            return
        
        if not parent_name:
            QMessageBox.warning(self, "Validation Error", "Parent name is missing! Please select a student first.")
            return
        
        if not student_class:
            QMessageBox.warning(self, "Validation Error", "Class is missing! Please select a student first.")
            return
        
        if not student_section:
            QMessageBox.warning(self, "Validation Error", "Section is missing! Please select a student first.")
            return
        
        # --- STEP 3: VALIDATE MONTHS SELECTION ---
        selected_months = []
        if hasattr(self, 'fee_months_list'):
            selected_months = [item.text() for item in self.fee_months_list.selectedItems()]
        
        if not selected_months:
            QMessageBox.warning(self, "Validation Error", "Please select at least one month!")
            return
        
        # --- STEP 4: GET FEE AMOUNTS ---
        try:
            tuition_fee = self.fee_tuition.value() if hasattr(self, 'fee_tuition') else 0.0
            lab_fee = self.fee_lab.value() if hasattr(self, 'fee_lab') else 0.0
            sport_fee = self.fee_sport.value() if hasattr(self, 'fee_sport') else 0.0
            computer_fee = self.fee_computer.value() if hasattr(self, 'fee_computer') else 0.0
            maintenance_fee = self.fee_maintenance.value() if hasattr(self, 'fee_maintenance') else 0.0
            exam_fee = self.fee_exam.value() if hasattr(self, 'fee_exam') else 0.0
            late_fee = self.fee_late.value() if hasattr(self, 'fee_late') else 0.0
            
            total_amount = tuition_fee + lab_fee + sport_fee + computer_fee + maintenance_fee + exam_fee + late_fee
            
            print(f"Fee amounts - Tuition: {tuition_fee}, Lab: {lab_fee}, Sport: {sport_fee}")  # Debug
            print(f"Computer: {computer_fee}, Maintenance: {maintenance_fee}, Exam: {exam_fee}, Late: {late_fee}")
            print(f"Total: {total_amount}")
            
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Error reading fee amounts: {str(e)}")
            return
        
        if total_amount <= 0:
            QMessageBox.warning(self, "Validation Error", "Please enter at least one fee amount!")
            return
        
        # --- STEP 5: SAVE TO DATABASE FIRST ---
        try:
            self.save_fee_record()
        except Exception as e:
            QMessageBox.warning(self, "Database Error", f"Failed to save fee record: {str(e)}")
            return
        
        # --- STEP 6: SELECT SAVE LOCATION ---
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Receipt")
        if not folder:
            return
        
        # --- STEP 7: GET SCHOOL DETAILS ---
        school_name = self.db.get_setting('school_name') or "Parker School"
        school_address = self.db.get_setting('school_address') or "Khurshid Bagh Rafi Road"
        school_email = self.db.get_setting('school_email') or "myemail@gmail.com"
        
        # --- STEP 8: GENERATE PDF ---
        receipt_number = self.fee_receipt_input.text() if hasattr(self, 'fee_receipt_input') else "REC000001"
        filename = os.path.join(folder, f"Fee_Receipt_{receipt_number}.pdf")
        
        try:
            doc = SimpleDocTemplate(
                filename,
                pagesize=A4,
                rightMargin=40,
                leftMargin=40,
                topMargin=40,
                bottomMargin=40
            )
            elements = []
            styles = getSampleStyleSheet()
            
            # --- SCHOOL HEADER ---
            school_style = ParagraphStyle(
                'SchoolName',
                parent=styles['Heading1'],
                fontSize=24,
                textColor=colors.black,
                alignment=TA_CENTER,
                spaceAfter=5,
                fontName='Helvetica-Bold'
            )
            elements.append(Paragraph(school_name, school_style))
            
            if school_address:
                addr_style = ParagraphStyle(
                    'Address',
                    parent=styles['Normal'],
                    alignment=TA_CENTER,
                    fontSize=10,
                    spaceAfter=3
                )
                elements.append(Paragraph(school_address, addr_style))
            
            if school_email:
                email_style = ParagraphStyle(
                    'Email',
                    parent=styles['Normal'],
                    alignment=TA_CENTER,
                    fontSize=9,
                    spaceAfter=15
                )
                elements.append(Paragraph(f"Email: {school_email}", email_style))
            
            elements.append(Spacer(1, 10))
            
            # --- TITLE ---
            title_style = ParagraphStyle(
                'Title',
                parent=styles['Heading1'],
                fontSize=18,
                alignment=TA_CENTER,
                spaceAfter=15,
                fontName='Helvetica-Bold',
                borderWidth=2,
                borderColor=colors.black,
                borderPadding=10
            )
            elements.append(Paragraph("FEES RECEIPT", title_style))
            elements.append(Spacer(1, 15))
            
            # --- HEADER (Receipt No, Date) ---
            current_date = self.fee_payment_date.date().toString("dd-MM-yyyy") if hasattr(self, 'fee_payment_date') else datetime.now().strftime("%d-%m-%Y")
            
            header_data = [
                ['Receipt No.', receipt_number, 'Date :', current_date],
            ]
            
            header_table = Table(header_data, colWidths=[2*inch, 2*inch, 1*inch, 2*inch])
            header_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 11),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 8),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(header_table)
            elements.append(Spacer(1, 8))
            
            # --- STUDENT DETAILS ---
            months_text = ", ".join(selected_months)
            
            student_data = [
                ['Student Name:', student_name, 'Class:', student_class],
                ['Section:', student_section, 'Parent Name:', parent_name],
                [f'Months: {months_text}', '', '', '']
            ]
            
            student_table = Table(student_data, colWidths=[1.5*inch, 2.5*inch, 1.5*inch, 2.5*inch])
            student_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
                ('TOPPADDING', (0, 0), (-1, -1), 6),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('SPAN', (0, 2), (3, 2))
            ]))
            elements.append(student_table)
            elements.append(Spacer(1, 10))
            
            # --- FEE DETAILS ---
            fee_details_data = [
                ["Student's Fees Detail", 'Amount'],
                ['Tution Fee', f'{tuition_fee:.1f}'],
                ['Sport Fee', f'{sport_fee:.1f}'],
                ['Computer Fee', f'{computer_fee:.1f}'],
                ['Lab Fee', f'{lab_fee:.1f}'],
                ['Maintenance Fee', f'{maintenance_fee:.1f}'],
                ['Exam Fee', f'{exam_fee:.1f}'],
                ['Late Fee', f'{late_fee:.1f}'],
                ['', ''],
                ['Due Fee', f'{total_amount:.1f}'],
                ['Balance Fee', '']
            ]
            
            fee_table = Table(fee_details_data, colWidths=[5*inch, 2*inch])
            fee_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (0, 0), 'LEFT'),
                ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTNAME', (0, 9), (0, 9), 'Helvetica-Bold'),  # Due Fee row
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                ('TOPPADDING', (0, 0), (-1, -1), 5),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            elements.append(fee_table)
            elements.append(Spacer(1, 15))
            
            # --- AMOUNT IN WORDS ---
            def number_to_words(n):
                """Convert number to words (simplified version)"""
                if n == 0:
                    return "Zero"
                
                ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"]
                teens = ["Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen"]
                tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]
                
                def convert_hundreds(num):
                    result = ""
                    if num >= 100:
                        result += ones[num // 100] + " Hundred "
                        num %= 100
                    if num >= 20:
                        result += tens[num // 10] + " "
                        num %= 10
                    elif num >= 10:
                        result += teens[num - 10] + " "
                        num = 0
                    if num > 0:
                        result += ones[num] + " "
                    return result
                
                if n < 1000:
                    return convert_hundreds(int(n)).strip()
                elif n < 100000:
                    thousands = n // 1000
                    remainder = n % 1000
                    result = convert_hundreds(int(thousands)) + "Thousand "
                    if remainder > 0:
                        result += convert_hundreds(int(remainder))
                    return result.strip()
                else:
                    return f"Amount: {n:.2f}"
            
            amount_words = number_to_words(total_amount)
            elements.append(Paragraph(f"Rupees {amount_words} Only", styles['Normal']))
            elements.append(Spacer(1, 30))
            
            # --- SIGNATURE ---
            elements.append(Paragraph("Authorized Signature", ParagraphStyle(
                'Signature',
                parent=styles['Normal'],
                alignment=TA_RIGHT,
                fontSize=10
            )))
            
            # --- BUILD PDF ---
            doc.build(elements)
            
            QMessageBox.information(self, "Success", f"Receipt saved successfully!\\n\\nFile: {filename}")
            
            # Clear form after successful generation
            if hasattr(self, 'clear_fee_form'):
                self.clear_fee_form()
            
        except Exception as e:
            QMessageBox.critical(self, "PDF Error", f"Failed to generate PDF: {str(e)}")
            print(f"PDF generation error: {e}")
            import traceback
            traceback.print_exc()

        
    def clear_fee_form(self):
        self.fee_student_name.clear()
        self.fee_student_name.clear()
        self.fee_class.clear()
        self.fee_section.clear()
        self.fee_parent_name.clear()
        self.fee_months_list.clearSelection()
        self.fee_tuition.setValue(0)
        self.fee_lab.setValue(0)
        self.fee_sport.setValue(0)
        self.fee_computer.setValue(0)
        self.fee_maintenance.setValue(0)
        self.fee_exam.setValue(0)
        self.fee_late.setValue(0)
        self.fee_total.clear()
        self.fee_payment_mode.setCurrentIndex(0)
        self.fee_status_full.setChecked(True)
        self.fee_payment_date.setDate(QDate.currentDate())
        
        if hasattr(self, 'selected_student_number'):
            delattr(self, 'selected_student_number')
        
        self.generate_receipt_number()
    
    def load_fee_records(self):
        conn = self.db.get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM fee_payments WHERE session = ? ORDER BY payment_date DESC", 
                      (self.current_session,))
        records = cursor.fetchall()
        conn.close()
        
        self.fee_records_table.setRowCount(0)
        
        for row_idx, record in enumerate(records):
            self.fee_records_table.insertRow(row_idx)
            
            self.fee_records_table.setItem(row_idx, 0, QTableWidgetItem(record[1]))  # Receipt
            self.fee_records_table.setItem(row_idx, 1, QTableWidgetItem(record[3]))  # Student
            self.fee_records_table.setItem(row_idx, 2, QTableWidgetItem(record[4]))  # Class
            self.fee_records_table.setItem(row_idx, 3, QTableWidgetItem(record[7]))  # Months
            self.fee_records_table.setItem(row_idx, 4, QTableWidgetItem(record[8]))  # Date
            self.fee_records_table.setItem(row_idx, 5, QTableWidgetItem(record[17]))  # Amount
            self.fee_records_table.setItem(row_idx, 6, QTableWidgetItem(record[18]))  # Mode
            self.fee_records_table.setItem(row_idx, 7, QTableWidgetItem(record[19]))  # Status
            
            # Action buttons
            action_widget = QWidget()
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(5, 5, 5, 5)
            action_layout.setSpacing(5)
            
            print_btn = QPushButton("🖨️")
            print_btn.setStyleSheet("background: #667eea; color: white; border: none; padding: 5px; border-radius: 5px;")
            print_btn.clicked.connect(lambda checked, r=record: self.print_fee_receipt(r))
            action_layout.addWidget(print_btn)
            
            delete_btn = QPushButton("🗑️")
            delete_btn.setStyleSheet("background: #f44336; color: white; border: none; padding: 5px; border-radius: 5px;")
            delete_btn.clicked.connect(lambda checked, r=record: self.delete_fee_record(r))
            action_layout.addWidget(delete_btn)
            
            self.fee_records_table.setCellWidget(row_idx, 8, action_widget)
    
    def filter_fee_records(self):
        search_text = self.fee_records_search.text().lower()
        month_filter = self.fee_records_month.currentText()
        
        for row in range(self.fee_records_table.rowCount()):
            show_row = True
            
            if search_text:
                student = self.fee_records_table.item(row, 1).text().lower()
                receipt = self.fee_records_table.item(row, 0).text().lower()
                if search_text not in student and search_text not in receipt:
                    show_row = False
            
            if month_filter != "All":
                months = self.fee_records_table.item(row, 3).text()
                if month_filter not in months:
                    show_row = False
            
            self.fee_records_table.setRowHidden(row, not show_row)
    
    def print_fee_receipt(self, record):
        """Print an existing fee receipt from records"""
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Receipt")
        if not folder:
            return
        
        school_name = self.db.get_setting('school_name') or "School ERP"
        school_address = self.db.get_setting('school_address') or ""
        school_email = self.db.get_setting('school_email') or ""
        
        # record structure: [id, receipt_number, student_number,     student_name, class, section,
        #                    parent_name, months, payment_date,     tuition_fee, lab_fee, sport_fee,
        #                    computer_fee, maintenance_fee, exam_fee, late_fee,
        #                    total_amount, payment_mode,     payment_status, session]
        
        filename = os.path.join(folder, f"Fee_Receipt_{record[1]}.pdf")
        
        doc = SimpleDocTemplate(
            filename,
            pagesize=A4,
            rightMargin=40,
            leftMargin=40,
            topMargin=40,
            bottomMargin=40
        )
        elements = []
        styles = getSampleStyleSheet()
        
        # School Name
        school_style = ParagraphStyle(
            'SchoolName',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.black,
            alignment=TA_CENTER,
            spaceAfter=5,
            fontName='Helvetica-Bold'
        )
        elements.append(Paragraph(school_name, school_style))
        
        # School Address
        if school_address:
            addr_style = ParagraphStyle(
                'Address',
                parent=styles['Normal'],
                alignment=TA_CENTER,
                fontSize=10,
                spaceAfter=3
            )
            elements.append(Paragraph(school_address, addr_style))
        
        # School Email
        if school_email:
            email_style = ParagraphStyle(
                'Email',
                parent=styles['Normal'],
                alignment=TA_CENTER,
                fontSize=9,
                spaceAfter=15
            )
            elements.append(Paragraph(f"Email: {school_email}",     email_style))
    
        elements.append(Spacer(1, 10))
        
        # Title
        title_style = ParagraphStyle(
            'Title',
            parent=styles['Heading1'],
            fontSize=18,
            alignment=TA_CENTER,
            spaceAfter=15,
            fontName='Helvetica-Bold',
            borderWidth=2,
            borderColor=colors.black,
            borderPadding=10
        )
        elements.append(Paragraph("FEES RECEIPT", title_style))
        elements.append(Spacer(1, 15))
        
        # Receipt header
        header_data = [
            ['Receipt No.', record[1], 'Date :', record[8]],
            ['Regn. No.', record[2], '', '']
        ]
        
        header_table = Table(header_data, colWidths=[2*inch, 2*inch,     1*inch, 2*inch])
        header_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 11),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(header_table)
        
        # Student details
        # --- STUDENT DETAILS TABLE ---
        months_raw = record[7]
        if months_raw is None:
            months_text = "N/A"
        else:
            months_text = str(months_raw).strip()
            if months_text == "":
                months_text = "N/A"
        
        # --- ENSURE LINE WRAP WORKS IN PDF ---
        months_paragraph = Paragraph(f"<b>Months:</b> {months_text}", styles['Normal'])
        student_data = [
            ['Student name', record[3], "Father\'s Name", record[6]],
            ['Class', record[4], 'Section', record[5]],
            [months_paragraph, '', '', '']          ]
        
        student_table = Table(student_data, colWidths=[1.5*inch, 2.5*inch, 1.5*inch, 2.5*inch])
        student_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),  # left column bold
            ('FONTNAME', (2, 0), (2, 0), 'Helvetica-Bold'),   # "Father's Name" bold
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ('SPAN', (0, 2), (3, 2)),  # merge all 4 columns for Months row
        ]))
        elements.append(student_table)
        elements.append(Spacer(1, 10))
        
        # Fee details
        total_amount = record[17]
        tution_fee = record[9]
        sport_fee = record[11]
        lab_fee = record[10]
        computer_fee = record[12]
        maintenance_fee = record[13]
        exam_fee = record[14]
        late_fee = record[16]
        fee_details_data = [
            ["Student's Fees Detail", 'Amount'],
            ['Tution Fee', str(tution_fee)],
            ['Sport Fee', str(sport_fee)],
            ['Computer Fee', str(computer_fee)],
            ['Lab Fee', str(lab_fee)],
            ['Maintenance Fee', str(maintenance_fee)],
            ['Exam Fee', str(exam_fee)],
            ['Late Fee', str(late_fee)],
            ['', ''],
            ['Due Fee', str(total_amount)],
            ['Balance Fee', '' ]
        ]
        
        fee_table = Table(fee_details_data, colWidths=[5*inch, 2*inch])
        fee_table.setStyle(TableStyle([
            ('ALIGN', (0, 0), (0, 0), 'LEFT'),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 3), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
            # ('SPAN', (0, 1), (0, 2)),
            # ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(fee_table)
        
        elements.append(Spacer(1, 15))
        
        # Amount in words
        try:
            from num2words import num2words
            amount_words = num2words(total_amount, lang='en_IN').title    () + " Only"
        except:
            amount_words = "Amount in words"
        
        words_style = ParagraphStyle(
            'Words',
            parent=styles['Normal'],
            fontSize=11,
            spaceAfter=30
        )
        elements.append(Paragraph(f"Rupees {amount_words}",     words_style))
        
        # Signature
        elements.append(Spacer(1, 40))
        sig_data = [['', '', 'Authorized Signature']]
        sig_table = Table(sig_data, colWidths=[2.5*inch, 2*inch, 2.5*inch])
        sig_table.setStyle(TableStyle([
            ('ALIGN', (2, 0), (2, 0), 'CENTER'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('LINEABOVE', (2, 0), (2, 0), 1, colors.black),
        ]))
        elements.append(sig_table)
        
        doc.build(elements)
        
        QMessageBox.information(self, "Success", f"Receipt saved to:\n {filename}")
    

    def delete_fee_record(self, record):
        reply = QMessageBox.question(self, "Delete Record",
                                    "Are you sure you want to delete this fee record?",
                                    QMessageBox.Yes | QMessageBox.No)
        
        if reply == QMessageBox.Yes:
            conn = self.db.get_connection()
            cursor = conn.cursor()
            cursor.execute("DELETE FROM fee_payments WHERE id = ?", (record[0],))
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Success", "Fee record deleted successfully!")
            self.load_fee_records()
            self.refresh_home_data()
    
    def load_paid_fees(self):
        month = self.paid_month_combo.currentText()
        class_filter = self.paid_class_combo.currentText()
        section_filter = self.paid_section_combo.currentText()
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Get students who paid for the selected month
        query = """
            SELECT DISTINCT s.student_number, s.full_name, s.class, s.section, 
                   s.parent_name, f.total_amount
            FROM students s
            INNER JOIN fee_payments f ON s.student_number = f.student_number
            WHERE f.months LIKE ? AND f.payment_status = 'Full Paid' AND s.session = ?
        """
        params = [f"%{month}%", self.current_session]
        
        if class_filter != "All":
            query += " AND s.class = ?"
            params.append(class_filter)
        
        if section_filter != "All":
            query += " AND s.section = ?"
            params.append(section_filter)
        
        cursor.execute(query, params)
        students = cursor.fetchall()
        conn.close()
        
        self.paid_fees_table.setRowCount(0)
        
        for row_idx, student in enumerate(students):
            self.paid_fees_table.insertRow(row_idx)
            
            self.paid_fees_table.setItem(row_idx, 0, QTableWidgetItem(student[0]))
            self.paid_fees_table.setItem(row_idx, 1, QTableWidgetItem(student[1]))
            self.paid_fees_table.setItem(row_idx, 2, QTableWidgetItem(student[2]))
            self.paid_fees_table.setItem(row_idx, 3, QTableWidgetItem(student[3]))
            self.paid_fees_table.setItem(row_idx, 4, QTableWidgetItem(student[4]))
            self.paid_fees_table.setItem(row_idx, 5, QTableWidgetItem(f"₹{student[5]:.2f}"))
        
        self.paid_count_label.setText(f"Total Students: {len(students)}")
    
    def load_unpaid_fees(self):
        month = self.unpaid_month_combo.currentText()
        class_filter = self.unpaid_class_combo.currentText()
        section_filter = self.unpaid_section_combo.currentText()
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        # Get all students
        query = "SELECT student_number, full_name, class, section, parent_name FROM students WHERE session = ?"
        params = [self.current_session]
        
        if class_filter != "All":
            query += " AND class = ?"
            params.append(class_filter)
        
        if section_filter != "All":
            query += " AND section = ?"
            params.append(section_filter)
        
        cursor.execute(query, params)
        all_students = cursor.fetchall()
        
        # Get students who paid
        cursor.execute("""
            SELECT DISTINCT student_number 
            FROM fee_payments 
            WHERE months LIKE ? AND payment_status = 'Full Paid' AND session = ?
        """, (f"%{month}%", self.current_session))
        
        paid_students = set([row[0] for row in cursor.fetchall()])
        conn.close()
        
        # Filter unpaid students
        unpaid_students = [s for s in all_students if s[0] not in paid_students]
        
        self.unpaid_fees_table.setRowCount(0)
        
        for row_idx, student in enumerate(unpaid_students):
            self.unpaid_fees_table.insertRow(row_idx)
            
            self.unpaid_fees_table.setItem(row_idx, 0, QTableWidgetItem(student[0]))
            self.unpaid_fees_table.setItem(row_idx, 1, QTableWidgetItem(student[1]))
            self.unpaid_fees_table.setItem(row_idx, 2, QTableWidgetItem(student[2]))
            self.unpaid_fees_table.setItem(row_idx, 3, QTableWidgetItem(student[3]))
            self.unpaid_fees_table.setItem(row_idx, 4, QTableWidgetItem(student[4]))
        
        self.unpaid_count_label.setText(f"Total Students: {len(unpaid_students)}")
    
    def export_paid_fees(self):
        if self.paid_fees_table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "Please load data first!")
            return
        
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Report")
        if not folder:
            return
        
        month = self.paid_month_combo.currentText()
        filename = os.path.join(folder, f"Paid_Fees_{month}_{self.current_session}.pdf")
        
        doc = SimpleDocTemplate(filename, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#4CAF50'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        elements.append(Paragraph("Paid Fees Report", title_style))
        elements.append(Paragraph(f"Month: {month} | Session: {self.current_session}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        data = [['Student No.', 'Name', 'Class', 'Section', 'Amount']]
        
        for row in range(self.paid_fees_table.rowCount()):
            data.append([
                self.paid_fees_table.item(row, 0).text(),
                self.paid_fees_table.item(row, 1).text(),
                self.paid_fees_table.item(row, 2).text(),
                self.paid_fees_table.item(row, 3).text(),
                self.paid_fees_table.item(row, 5).text()
            ])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4CAF50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(self.paid_count_label.text(), styles['Normal']))
        
        doc.build(elements)
        
        QMessageBox.information(self, "Success", f"Report saved to:\n{filename}")
    
    def export_unpaid_fees(self):
        if self.unpaid_fees_table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "Please load data first!")
            return
        
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Report")
        if not folder:
            return
        
        month = self.unpaid_month_combo.currentText()
        filename = os.path.join(folder, f"Unpaid_Fees_{month}_{self.current_session}.pdf")
        
        doc = SimpleDocTemplate(filename, pagesize=A4)
        elements = []
        styles = getSampleStyleSheet()
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#f44336'),
            spaceAfter=30,
            alignment=TA_CENTER
        )
        
        elements.append(Paragraph("Unpaid Fees Report", title_style))
        elements.append(Paragraph(f"Month: {month} | Session: {self.current_session}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        data = [['Student No.', 'Name', 'Class', 'Section', 'Parent Name']]
        
        for row in range(self.unpaid_fees_table.rowCount()):
            data.append([
                self.unpaid_fees_table.item(row, 0).text(),
                self.unpaid_fees_table.item(row, 1).text(),
                self.unpaid_fees_table.item(row, 2).text(),
                self.unpaid_fees_table.item(row, 3).text(),
                self.unpaid_fees_table.item(row, 4).text()
            ])
        
        table = Table(data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f44336')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 12),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        
        elements.append(table)
        elements.append(Spacer(1, 20))
        elements.append(Paragraph(self.unpaid_count_label.text(), styles['Normal']))
        
        doc.build(elements)
        
        QMessageBox.information(self, "Success", f"Report saved to:\n{filename}")
    
    def create_settings_page(self):
        page = QWidget()
        page.setStyleSheet("background: transparent;")
        
        layout = QVBoxLayout(page)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)
        
        # Page title
        title = QLabel("Settings")
        title.setStyleSheet("""
            font-size: 32px;
            font-weight: bold;
            color: #333;
        """)
        layout.addWidget(title)
        
        # School Information
        school_group = QGroupBox("School Information")
        school_group.setStyleSheet("""
            QGroupBox {
                font-size: 16px;
                font-weight: bold;
                color: #667eea;
                border: 2px solid #667eea;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        school_layout = QFormLayout(school_group)
        school_layout.setSpacing(15)
        
        self.settings_school_name = QLineEdit()
        self.settings_school_name.setText(self.db.get_setting('school_name') or "School ERP")
        self.settings_school_name.setStyleSheet(self.get_input_style())
        school_layout.addRow("School Name:", self.settings_school_name)
        
        self.settings_school_address = QTextEdit()
        self.settings_school_address.setPlainText(self.db.get_setting('school_address') or "")
        self.settings_school_address.setMaximumHeight(80)
        self.settings_school_address.setStyleSheet(self.get_input_style())
        school_layout.addRow("School Address:", self.settings_school_address)
        
        self.settings_school_email = QLineEdit()
        self.settings_school_email.setText(self.db.get_setting('school_email') or "")
        self.settings_school_email.setStyleSheet(self.get_input_style())
        school_layout.addRow("School Email:", self.settings_school_email)
        
        save_school_btn = QPushButton("💾 Save School Information")
        save_school_btn.setStyleSheet(self.get_button_style("#667eea"))
        save_school_btn.clicked.connect(self.save_school_settings)
        school_layout.addRow("", save_school_btn)
        
        layout.addWidget(school_group)
        
        # Backup & Restore
        backup_group = QGroupBox("Backup & Restore")
        backup_group.setStyleSheet("""
            QGroupBox {
                font-size: 17px;
                font-weight: bold;
                color: #06d6a0;
                border: 2px solid #06d6a0;
                border-radius: 10px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
            }
        """)
        
        backup_layout = QVBoxLayout(backup_group)
        backup_layout.setSpacing(15)
        
        backup_desc = QLabel("Create a complete backup of all data including students, staff, attendance, fees, and salary records.")
        backup_desc.setWordWrap(True)
        backup_layout.addWidget(backup_desc)
        
        # Backup options
        backup_options_layout = QHBoxLayout()
        
        backup_options_layout.addWidget(QLabel("Backup Type:"))
        
        self.backup_type_combo = QComboBox()
        self.backup_type_combo.addItems(["Complete Backup", "Current Session Only", "Specific Month"])
        self.backup_type_combo.setStyleSheet(self.get_input_style())
        backup_options_layout.addWidget(self.backup_type_combo)
        
        self.backup_month_combo = QComboBox()
        months = ["January", "February", "March", "April", "May", "June",
                 "July", "August", "September", "October", "November", "December"]
        self.backup_month_combo.addItems(months)
        self.backup_month_combo.setCurrentText(datetime.now().strftime("%B"))
        self.backup_month_combo.setStyleSheet(self.get_input_style())
        self.backup_month_combo.setEnabled(False)
        backup_options_layout.addWidget(self.backup_month_combo)
        
        self.backup_type_combo.currentTextChanged.connect(self.update_backup_options)
        
        backup_options_layout.addStretch()
        
        backup_layout.addLayout(backup_options_layout)
        
        backup_btn = QPushButton("💾 Create Backup")
        backup_btn.setStyleSheet(self.get_button_style("#06d6a0"))
        backup_btn.clicked.connect(self.create_complete_backup)
        backup_layout.addWidget(backup_btn)
        
        backup_layout.addSpacing(20)
        
        restore_desc = QLabel("Restore data from a previously created backup file. WARNING: This will override existing data!")
        restore_desc.setWordWrap(True)
        restore_desc.setStyleSheet("color: #f44336; font-weight: bold;")
        backup_layout.addWidget(restore_desc)
        
        restore_options_layout = QHBoxLayout()
        
        self.restore_override_radio = QRadioButton("Override Existing Data")
        self.restore_override_radio.setChecked(True)
        restore_options_layout.addWidget(self.restore_override_radio)
        
        self.restore_reset_radio = QRadioButton("Reset & Restore (Delete All)")
        restore_options_layout.addWidget(self.restore_reset_radio)
        
        restore_options_layout.addStretch()
        
        backup_layout.addLayout(restore_options_layout)
        
        restore_btn = QPushButton("📂 Restore from Backup")
        restore_btn.setStyleSheet(self.get_button_style("#f44336"))
        restore_btn.clicked.connect(self.restore_complete_backup)
        backup_layout.addWidget(restore_btn)
        
        layout.addWidget(backup_group)
        
        layout.addStretch()
        
        return page
    
    def save_school_settings(self):
        self.db.set_setting('school_name', self.settings_school_name.text())
        self.db.set_setting('school_address', self.settings_school_address.toPlainText())
        self.db.set_setting('school_email', self.settings_school_email.text())
        
        QMessageBox.information(self, "Success", "School information saved successfully!")
    
    def update_backup_options(self, text):
        if text == "Specific Month":
            self.backup_month_combo.setEnabled(True)
        else:
            self.backup_month_combo.setEnabled(False)
    
    def create_complete_backup(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Save Backup")
        if not folder:
            return
        
        backup_type = self.backup_type_combo.currentText()
        
        conn = self.db.get_connection()
        cursor = conn.cursor()
        
        backup_data = {
            'backup_type': backup_type,
            'backup_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'session': self.current_session,
            'school_info': {
                'name': self.db.get_setting('school_name'),
                'address': self.db.get_setting('school_address'),
                'email': self.db.get_setting('school_email')
            }
        }
        
        # Students
        if backup_type == "Complete Backup":
            cursor.execute("SELECT * FROM students")
        elif backup_type == "Current Session Only":
            cursor.execute("SELECT * FROM students WHERE session = ?", (self.current_session,))
        else:
            month = self.backup_month_combo.currentText()
            cursor.execute("SELECT * FROM students WHERE session = ?", (self.current_session,))
        
        students = cursor.fetchall()
        backup_data['students'] = []
        for s in students:
            backup_data['students'].append({
                'student_number': s[1], 'full_name': s[2], 'roll_number': s[3],
                'class': s[4], 'section': s[5], 'parent_name': s[6],
                'gender': s[7], 'dob': s[8], 'parent_number': s[9],
                'address': s[10], 'session': s[11]
            })
        
        # Staff
        if backup_type == "Complete Backup":
            cursor.execute("SELECT * FROM staff")
        else:
            cursor.execute("SELECT * FROM staff WHERE session = ?", (self.current_session,))
        
        staff = cursor.fetchall()
        backup_data['staff'] = []
        for s in staff:
            backup_data['staff'].append({
                'staff_id': s[1], 'name': s[2], 'phone': s[3], 'email': s[4],
                'designation': s[5], 'qualification': s[6], 'department': s[7],
                'joining_date': s[8], 'salary': s[9], 'address': s[10], 'session': s[11]
            })
        
        # Attendance
        if backup_type == "Complete Backup":
            cursor.execute("SELECT * FROM attendance")
        elif backup_type == "Current Session Only":
            cursor.execute("SELECT * FROM attendance WHERE session = ?", (self.current_session,))
        else:
            month = self.backup_month_combo.currentText()
            cursor.execute("SELECT * FROM attendance WHERE session = ? AND month = ?", 
                         (self.current_session, month))
        
        attendance = cursor.fetchall()
        backup_data['attendance'] = []
        for a in attendance:
            backup_data['attendance'].append({
                'student_number': a[1], 'class': a[2], 'section': a[3],
                'month': a[4], 'year': a[5], 'working_days': a[6],
                'days_present': a[7], 'percentage': a[8], 'session': a[9]
            })
        
        # Salary Payments
        if backup_type == "Complete Backup":
            cursor.execute("SELECT * FROM salary_payments")
        elif backup_type == "Current Session Only":
            cursor.execute("SELECT * FROM salary_payments WHERE session = ?", (self.current_session,))
        else:
            month = self.backup_month_combo.currentText()
            cursor.execute("SELECT * FROM salary_payments WHERE session = ? AND month = ?", 
                         (self.current_session, month))
        
        salaries = cursor.fetchall()
        backup_data['salary_payments'] = []
        for s in salaries:
            backup_data['salary_payments'].append({
                'staff_id': s[1], 'staff_name': s[2], 'amount': s[3],
                'payment_date': s[4], 'month': s[5], 'year': s[6], 'session': s[7]
            })
        
        # Fee Payments
        if backup_type == "Complete Backup":
            cursor.execute("SELECT * FROM fee_payments")
        elif backup_type == "Current Session Only":
            cursor.execute("SELECT * FROM fee_payments WHERE session = ?", (self.current_session,))
        else:
            month = self.backup_month_combo.currentText()
            cursor.execute("SELECT * FROM fee_payments WHERE session = ? AND months LIKE ?", 
                         (self.current_session, f"%{month}%"))
        
        fees = cursor.fetchall()
        backup_data['fee_payments'] = []
        for f in fees:
            backup_data['fee_payments'].append({
                'receipt_number': f[1], 'student_number': f[2], 'student_name': f[3],
                'class': f[4], 'section': f[5], 'parent_name': f[6], 'months': f[7],
                'payment_date': f[8], 'tuition_fee': f[9], 'lab_fee': f[10],
                'sport_fee': f[11], 'computer_fee': f[12], 'maintenance_fee': f[13],
                'exam_fee': f[14], 'late_fee': f[15],
                'total_amount': f[16], 'payment_mode': f[17], 'payment_status': f[18],
                'session': f[19]
            })
        
        conn.close()
        
        # Save backup
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = os.path.join(folder, f"school_erp_backup_{timestamp}.json")
        
        with open(filename, 'w') as f:
            json.dump(backup_data, f, indent=4)
        
        QMessageBox.information(self, "Success", 
                              f"Backup created successfully!\n\n"
                              f"File: {filename}\n"
                              f"Students: {len(backup_data['students'])}\n"
                              f"Staff: {len(backup_data['staff'])}\n"
                              f"Attendance Records: {len(backup_data['attendance'])}\n"
                              f"Fee Records: {len(backup_data['fee_payments'])}\n"
                              f"Salary Records: {len(backup_data['salary_payments'])}")
    
    def restore_complete_backup(self):
        reply = QMessageBox.warning(self, "Warning",
                                   "Restoring from backup will modify your database. "
                                   "Make sure you have a current backup before proceeding.\n\n"
                                   "Do you want to continue?",
                                   QMessageBox.Yes | QMessageBox.No)
        
        if reply != QMessageBox.Yes:
            return
        
        filename, _ = QFileDialog.getOpenFileName(self, "Select Backup File", "", "JSON Files (*.json)")
        if not filename:
            return
        
        try:
            with open(filename, 'r') as f:
                backup_data = json.load(f)
            
            conn = self.db.get_connection()
            cursor = conn.cursor()
            
            # Reset if selected
            if self.restore_reset_radio.isChecked():
                cursor.execute("DELETE FROM students")
                cursor.execute("DELETE FROM staff")
                cursor.execute("DELETE FROM attendance")
                cursor.execute("DELETE FROM salary_payments")
                cursor.execute("DELETE FROM fee_payments")
            
            # Restore school info
            if 'school_info' in backup_data:
                self.db.set_setting('school_name', backup_data['school_info'].get('name', ''))
                self.db.set_setting('school_address', backup_data['school_info'].get('address', ''))
                self.db.set_setting('school_email', backup_data['school_info'].get('email', ''))
            
            # Restore students
            for student in backup_data.get('students', []):
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO students (
                            student_number, full_name, roll_number, class, section,
                            parent_name, gender, dob, parent_number, address, session
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        student['student_number'], student['full_name'], student['roll_number'],
                        student['class'], student['section'], student['parent_name'],
                        student['gender'], student['dob'], student['parent_number'],
                        student['address'], student['session']
                    ))
                except:
                    pass
            
            # Restore staff
            for staff in backup_data.get('staff', []):
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO staff (
                            staff_id, name, phone, email, designation, qualification,
                            department, joining_date, salary, address, session
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        staff['staff_id'], staff['name'], staff['phone'], staff['email'],
                        staff['designation'], staff['qualification'], staff['department'],
                        staff['joining_date'], staff['salary'], staff['address'], staff['session']
                    ))
                except:
                    pass
            
            # Restore attendance
            for att in backup_data.get('attendance', []):
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO attendance (
                            student_number, class, section, month, year,
                            working_days, days_present, percentage, session
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        att['student_number'], att['class'], att['section'],
                        att['month'], att['year'], att['working_days'],
                        att['days_present'], att['percentage'], att['session']
                    ))
                except:
                    pass
            
            # Restore salary payments
            for salary in backup_data.get('salary_payments', []):
                try:
                    cursor.execute("""
                        INSERT INTO salary_payments (
                            staff_id, staff_name, amount, payment_date, month, year, session
                        ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        salary['staff_id'], salary['staff_name'], salary['amount'],
                        salary['payment_date'], salary['month'], salary['year'], salary['session']
                    ))
                except:
                    pass
            
            # Restore fee payments
            for fee in backup_data.get('fee_payments', []):
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO fee_payments (
                            receipt_number, student_number, student_name, class, section,
                            parent_name, months, payment_date, tuition_fee, lab_fee,
                            sport_fee, computer_fee, maintenance_fee, exam_fee,
                            late_fee, total_amount, payment_mode, payment_status, session
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        fee['receipt_number'], fee['student_number'], fee['student_name'],
                        fee['class'], fee['section'], fee['parent_name'], fee['months'],
                        fee['payment_date'], fee['tuition_fee'], fee['lab_fee'],
                        fee['sport_fee'], fee['computer_fee'], fee['maintenance_fee'],
                        fee['exam_fee'], fee['late_fee'],
                        fee['total_amount'], fee['payment_mode'], fee['payment_status'],
                        fee['session']
                    ))
                except:
                    pass
            
            conn.commit()
            conn.close()
            
            QMessageBox.information(self, "Success",
                                  f"Backup restored successfully!\n\n"
                                  f"Students: {len(backup_data.get('students', []))}\n"
                                  f"Staff: {len(backup_data.get('staff', []))}\n"
                                  f"Attendance Records: {len(backup_data.get('attendance', []))}\n"
                                  f"Fee Records: {len(backup_data.get('fee_payments', []))}\n"
                                  f"Salary Records: {len(backup_data.get('salary_payments', []))}")
            
            # Refresh all data
            self.load_students()
            self.load_staff()
            self.load_staff_for_salary()
            self.load_fee_records()
            self.load_salary_history()
            self.refresh_home_data()
            
            # Update settings display
            self.settings_school_name.setText(self.db.get_setting('school_name') or "School ERP")
            self.settings_school_address.setPlainText(self.db.get_setting('school_address') or "")
            self.settings_school_email.setText(self.db.get_setting('school_email') or "")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to restore backup:\n{str(e)}")
    

# Main application
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # Initialize database
    db = DatabaseManager()
    
    splash = SplashScreen()
    splash.show()
    
    sys.exit(app.exec_())
