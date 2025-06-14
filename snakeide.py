import subprocess
import sys
import os
import re
import shutil
import math

from PySide6.QtWidgets import (
	QApplication, QButtonGroup, QMainWindow, QSplitter, QTextEdit, QTreeView, QPlainTextEdit,
	QFileSystemModel, QFileDialog, QMessageBox, QMenu, QStatusBar,
	QToolBar, QLabel, QFrame, QVBoxLayout, QWidget, QHBoxLayout, 
	QTabWidget, QTabBar, QPushButton, QScrollBar, QDialog,
	QLineEdit, QDialogButtonBox, QInputDialog,
	QFileIconProvider
)
from PySide6.QtGui import (
	QFont, QKeyEvent, QKeySequence, QPalette, QColor, QAction, QIcon, QPixmap, QPainter, QShortcut,
	QSyntaxHighlighter, QTextCharFormat, QFontMetrics, QTextCursor
)
from PySide6.QtCore import (
	QFileInfo, Qt, QModelIndex, QSize, QRect,
	QThread, Signal, QProcess, QSortFilterProxyModel,
	QPoint
)
from PySide6.QtSvg import QSvgRenderer

from highlighter import PythonHighlighter
from core import *
import json

from PySide6.QtWidgets import QDialog, QVBoxLayout, QLineEdit, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt

def resource_path(relative):
	return os.path.join(getattr(sys, '_MEIPASS', os.path.abspath(".")), relative).replace("\\", "/")

def fix_qss_paths(qss: str) -> str:
	def path(name):
		return resource_path(f"icons/{name}").replace("\\", "/")

	return qss.format(
		close_tab=path("close_tab.svg"),
		caret_right=path("caret-right.svg"),
		caret_down=path("caret-down.svg")
	)

class CommandPalette(QDialog):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.setWindowFlags(
			Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
		)
		self.setAttribute(Qt.WA_TranslucentBackground)
		self.setFixedWidth(parent.width() * 0.8)  # 80% width of parent window
		self.move(
			parent.x() + parent.width() * 0.1,
			parent.y() + 10  # 10 px from top of main window
		)

		layout = QVBoxLayout(self)
		layout.setContentsMargins(8, 8, 8, 8)

		self.input = QLineEdit()
		self.input.setPlaceholderText("Type a command...")
		layout.addWidget(self.input)

		self.list_widget = QListWidget()
		layout.addWidget(self.list_widget)
		self.list_widget.setObjectName("CommandPaletteList")

		# Example commands
		self.commands = ["Build File", "Debug File"]
		self.update_list("")

		self.input.textChanged.connect(self.update_list)
		self.input.returnPressed.connect(self.execute_command)
		self.IDE = parent

	def update_list(self, filter_text):
		self.list_widget.clear()
		filtered = [cmd for cmd in self.commands if filter_text.lower() in cmd.lower()]
		for cmd in filtered:
			self.list_widget.addItem(QListWidgetItem(cmd))
		if filtered:
			self.list_widget.setCurrentRow(0)

	def execute_command(self):
		current = self.list_widget.currentItem()
		if current:
			if current.text() == "Build File":
				if self.IDE is not None:
					self.IDE.build_file()
			elif current.text() == "Debug File":
				if self.IDE is not None:
					self.IDE.debug_run()
			self.hide()
			return
		s=self.input.text().split(" ")
		if len(s)>1:
			cmdlet, args = s[0].strip(), s[1:]
		else:
			cmdlet, args = self.input.text().strip(), []
		self.hide()

	def keyPressEvent(self, event):
		if event.key() == Qt.Key_Escape:
			self.hide()
		else:
			super().keyPressEvent(event)

class ConsoleWidget(QTextEdit):
	enterPressed = Signal(str)  # Signal to emit command

	def keyPressEvent(self, event):
		if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
			text = self.toPlainText().split('\n')[-1] + '\n'
			self.enterPressed.emit(text)
			self.insertPlainText('\n')  # optional: simulate new line
		else:
			super().keyPressEvent(event)

class CustomInputDialog(QDialog):
	"""Themed input dialog matching Snake IDE style"""
	def __init__(self, parent, title, label, initial_text=""):
		super().__init__(parent)
		self.setWindowTitle(title)
		self.setModal(True)
		
		layout = QVBoxLayout(self)
		self.label = QLabel(label)
		self.input = QLineEdit(initial_text)
		buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
		
		layout.addWidget(self.label)
		layout.addWidget(self.input)
		layout.addWidget(buttons)
		
		buttons.accepted.connect(self.accept)
		buttons.rejected.connect(self.reject)
		
	def get_text(self):
		return self.input.text().strip()

class BuildThread(QProcess):
	finished = Signal(str)

	def __init__(self, console_output):
		super().__init__()
		self.console_output = console_output

		# Connect signals
		self.readyReadStandardOutput.connect(self.handle_stdout)
		self.readyReadStandardError.connect(self.handle_stderr)

	def start_build(self, program, arguments=[]):
		"""Start the process with given program and arguments."""
		self.setProgram(program)
		self.setArguments(arguments)
		self.setProcessChannelMode(QProcess.MergedChannels)  # Optional: merge stdout + stderr
		self.stateChanged.connect(self.on_state_changed)
		self.start()

	def on_state_changed(self, state):
		if state == QProcess.NotRunning:
			self.finished.emit('finished')

	def handle_stdout(self):
		data = self.readAllStandardOutput().data().decode()
		self.console_output.insertPlainText(data)
		self.console_output.ensureCursorVisible()

	def handle_stderr(self):
		data = self.readAllStandardError().data().decode()
		self.console_output.insertPlainText(data)
		self.console_output.ensureCursorVisible()

	def write(self, command):
		"""Send command to the running process"""
		if self.state() == QProcess.Running:
			self.writeData(command, len(command))


class DebugThread(QProcess):
	finished = Signal(str)

	def __init__(self, console_output, breakpoints):
		super().__init__()
		self.console_output = console_output
		self.bps = breakpoints.get_breakpoints()

		self.readyReadStandardOutput.connect(self.handle_stdout)

	def start_build(self, program, arguments=[]):
		"""Start the process with given program and arguments."""
		self.setProgram(program)
		self.setArguments(arguments)
		self.setProcessChannelMode(QProcess.MergedChannels)  # Optional: merge stdout + stderr
		self.stateChanged.connect(self.on_state_changed)
		self.console_output.insertPlainText("Running Debugger.\n")
		self.currentBP = 0
		self.start()
	def handle_stdout(self):
		data = self.readAllStandardOutput().data().decode('utf-8')
		for line in data.splitlines():
			if line.startswith("-> "):
				self.print_out(f"(BREAKPOINT) Line {self.bps[self.currentBP]+1}:\n\t" ,line.removeprefix("-> "))
				self.get_variables()
				self.currentBP += 1
			elif line.startswith("__VARIABLES__"):
				v =line.removeprefix("__VARIABLES__")
				variables = eval(v)
				for k,v in variables.items():
					if k.startswith("__"):
						continue
					self.print_out(f"Variable: {k} Value: {v}")
			else:
				print(len(line), line)
	def get_variables(self):
		self.code = """__VARS__={}
for __k, __v in list(locals().items()): __VARS__[__k]=str(__v)
print('__VARIABLES__'+str(__VARS__))"""
		for line in self.code.split("\n"):
			self.write('!'+line+'\n', False)
	def print_out(self, *args, end='\n'):
		for arg in args:
			self.console_output.insertPlainText(str(arg)+" ")
		self.console_output.insertPlainText(end)
	def on_state_changed(self, state):
		if state == QProcess.NotRunning:
			self.write("quit\n")
			self.console_output.insertPlainText(f"\n-> quit\n")
			self.finished.emit('finished')

	def write(self, command, printout=True):
		"""Send command to the running process"""
		if self.state() == QProcess.Running:
			if printout:
				self.console_output.insertPlainText(f"-> {command}\n")
			self.writeData(command, len(command))

CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'snakeide.conf')

class LineNumberArea(QWidget):
	def __init__(self, editor):
		super().__init__(editor)
		self.editor = editor

	def sizeHint(self):
		return QSize(self.editor.line_number_area_width(), 0)

	def paintEvent(self, event):
		self.editor.line_number_area_paint_event(event)

	def mousePressEvent(self, event):
		"""Handle mouse clicks for setting breakpoints"""
		if event.button() == Qt.LeftButton:
			# Calculate clicked line number
			block = self.editor.firstVisibleBlock()
			block_number = block.blockNumber()
			top = self.editor.blockBoundingGeometry(block).translated(
				self.editor.contentOffset()).top()
			
			y = event.position().y()
			while block.isValid():
				bottom = top + self.editor.blockBoundingRect(block).height()
				if top <= y <= bottom:
					# Toggle breakpoint at this line
					self.editor.toggle_breakpoint(block_number)
					break
				
				block = block.next()
				top = bottom
				block_number += 1
		super().mousePressEvent(event)

class CodeEditor(QPlainTextEdit):
	def __init__(self, parent=None):
		super().__init__(parent)
		self.efont = QFont("Cascadia Mono")
		self.efont.setPointSize(13) 
		self.efont.setStyleStrategy(QFont.StyleStrategy.PreferMatch)
		self.efont.setWeight(QFont.Weight.DemiBold)
		self.efont.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
		self.breakpoints = set()
		self.setFont(self.efont)
		self.line_number_area = LineNumberArea(self)
		self.blockCountChanged.connect(self.update_line_number_area_width)
		self.updateRequest.connect(self.update_line_number_area)
		self.update_line_number_area_width()
		self.paired_chars = {
			'(': ')',
			'[': ']',
			'{': '}',
			'"': '"',
			"'": "'"
		}
		self.cursorPositionChanged.connect(self.highlight_current_line)
	def keyPressEvent(self, event: QKeyEvent):
		cursor = self.textCursor()
		key = event.key()
		text = event.text()

		# Handle auto-pairing
		if text in self.paired_chars:
			closing_char = self.paired_chars[text]
			cursor.insertText(text + closing_char)
			cursor.movePosition(QTextCursor.Left)
			self.setTextCursor(cursor)
			return

		# Handle skipping over existing closing character
		elif text in self.paired_chars.values():
			next_char = self._next_char_right(cursor)
			if next_char == text:
				cursor.movePosition(QTextCursor.Right)
				self.setTextCursor(cursor)
				return
		elif key == Qt.Key.Key_Backspace:
			current_character = self._next_char_left(cursor)
			next_char = self._next_char_right(cursor)

			if current_character in self.paired_chars:
				if self.paired_chars[current_character] == next_char:
					cursor.movePosition(QTextCursor.Right)
					cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor)
					cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor)
					cursor.removeSelectedText()
					self.setTextCursor(cursor)
					return

		# Default behavior
		super().keyPressEvent(event)

	def line_number_area_width(self):
		digits = len(str(max(1, self.blockCount())))
		space = 3 + self.fontMetrics().horizontalAdvance('9') * digits
		return space + 14

	def update_line_number_area_width(self):
		self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

	def update_line_number_area(self, rect, dy):
		if dy:
			self.line_number_area.scroll(0, dy)
		else:
			self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
		
		if rect.contains(self.viewport().rect()):
			self.update_line_number_area_width()

	def resizeEvent(self, event):
		super().resizeEvent(event)
		cr = self.contentsRect()
		self.line_number_area.setGeometry(QRect(cr.left(), cr.top(), self.line_number_area_width(), cr.height()))
	def _next_char_right(self, cursor):
		cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
		next_char = cursor.selectedText()
		cursor.movePosition(QTextCursor.Left)
		return next_char
	def _next_char_left(self, cursor):
		cursor.movePosition(QTextCursor.Left, QTextCursor.KeepAnchor)
		next_char = cursor.selectedText()
		cursor.movePosition(QTextCursor.Right)
		return next_char
	def highlight_current_line(self):
		pass
	def toggle_breakpoint(self, line_number):
		"""Toggle breakpoint at given line number"""
		if line_number in self.breakpoints:
			self.breakpoints.remove(line_number)
		else:
			self.breakpoints.add(line_number)
		self.line_number_area.update()

	def get_breakpoints(self):
		"""Return sorted list of breakpoint line numbers"""
		return sorted(self.breakpoints)

	def line_number_area_paint_event(self, event):
		painter = QPainter(self.line_number_area)
		# Use Snake IDE theme colors for line numbers
		painter.fillRect(event.rect(), QColor("#3C3F41"))  # Background color
		
		block = self.firstVisibleBlock()
		block_number = block.blockNumber()
		top = self.blockBoundingGeometry(block).translated(self.contentOffset()).top()
		bottom = top + self.blockBoundingRect(block).height()

		# Get current line to highlight it
		current_line = self.textCursor().blockNumber()

		breakpoint_icon = QSvgRenderer(resource_path("./icons/breakpoint.svg"))
		icon_height = 14
		
		# Draw breakpoints and line numbers
		radius = 4
		while block.isValid() and top <= event.rect().bottom():
			if block.isVisible() and bottom >= event.rect().top():
				# Highlight current line
				if block_number == current_line:
					painter.fillRect(0, int(top), self.line_number_area.width(), 
									int(bottom - top), QColor("#4C5052"))
				
				# Draw breakpoint if set
				if block_number in self.breakpoints:
					x = 0
					y = math.floor(top + (bottom - top - icon_height) / 2)
					breakpoint_icon.render(painter, QRect(x,y, 14,14))
				
				# Draw line number text
				painter.setPen(QColor("#A9B7C6"))  # Snake IDE text color
				painter.drawText(0, int(top), self.line_number_area.width() - 3, 
								self.fontMetrics().height(),
								Qt.AlignRight, str(block_number + 1))
			
			block = block.next()
			top = bottom
			bottom = top + self.blockBoundingRect(block).height()
			block_number += 1

class snakeideEditor(QMainWindow):
	def __init__(self):
		super().__init__()
		self.setWindowTitle("Snake IDE V1")
		self.resize(1500,1500)
		self.showMaximized()
		self._tab_size = 4
		self._current_file = None
		self.default_Config = {"tab_size": 4, "current_project": None, "current_file": None, "open_files": []}
		self.config = self.load_config()
		self.console_process = None

		# Load custom icons
		self.folder_icon = self.load_folder_icon()
		self.file_icon = self.load_file_icon()

		self.open_files = {}
		self._init_ui()
		self._apply_snakeide_theme()

		
		# Apply UI font
		ui_font = QFont("Segoe UI")
		ui_font.setPointSize(9)
		QApplication.setFont(ui_font)
		
		if len(sys.argv)>1:
			self.open_files={}
			self._open_folder(sys.argv[1])
		else:
			if self.config.get("current_project"):
				self._open_folder(self.config.get("current_project"))
			# Open files from last session
			for file_path in self.config.get("open_files", []):
				if file_path:
					if os.path.exists(file_path):
						self._open_file(file_path)
			
			# Set current tab
			if self.config.get("current_file") and self.config["current_file"] in self.open_files:
				index = self.editor_tabs.indexOf(self.open_files[self.config["current_file"]]["widget"])
				self.editor_tabs.setCurrentIndex(index)

		self._tab_size = self.config.get("tab_size", 4)
		self.set_tab_size(self._tab_size)

	def open_command_palette(self):
		if not hasattr(self, 'command_palette'):
			self.command_palette = CommandPalette(self)
		self.command_palette.move(
			self.x() + self.width() * 0.1,
			self.y() + 10
		)
		self.command_palette.setObjectName("CommandPalette")
		self.command_palette.show()
		self.command_palette.input.setFocus()

	
	def load_folder_icon(self):
		"""Load folder icon from file or use base64 fallback"""
		icon_path = os.path.join(os.path.dirname(__file__), "icons/folder.svg")
		return QIcon(icon_path)
	
	def load_file_icon(self):
		"""Load file icon - using generic document icon"""
		parent = os.path.join(os.path.dirname(__file__), "icons")
		icons = {'general_file': QIcon(os.path.join(parent, "general_file.svg"))}
		for icon in os.listdir(parent):
			if icon.startswith("extension_"):
				extension_name = icon.removeprefix("extension_").removesuffix(".svg")
				icons[extension_name] = QIcon(os.path.join(parent, icon))
		return icons
		
	def load_config(self):
		if not os.path.exists(CONFIG_PATH):
			return self.default_Config
			
		with open(CONFIG_PATH, 'r') as f:
			try:
				config = json.load(f)
			except:
				return self.default_Config
		return config

	def save_config(self):
		# Update open files list
		self.config["open_files"] = list(self.open_files.keys())
		
		# Update current file
		current_widget = self.editor_tabs.currentWidget()
		if current_widget:
			for path, file_info in self.open_files.items():
				if file_info["widget"] == current_widget:
					self.config["current_file"] = path
					break
		
		with open(CONFIG_PATH, 'w') as f:
			json.dump(self.config, f, indent=4)

	def _init_ui(self):
		self._create_actions()
		self._create_toolbar()
		self._create_menus()
		
		# Main splitter
		self.main_splitter = QSplitter(Qt.Horizontal)
		
		# Left panel with project tree
		left_panel = self._create_left_panel()
		
		# Right panel with editor
		right_panel = self._create_editor_panel()

		self._create_status_bar()
		
		self.main_splitter.addWidget(left_panel)
		self.main_splitter.addWidget(right_panel)
		self.main_splitter.setSizes([280, 920])

		self.console_output = QTextEdit()
		self.console_output.setReadOnly(True)
		self.console_output.setFixedHeight(150)
		self.console_output.setObjectName("Console")

		self.root_splitter = QSplitter(Qt.Vertical)
		self.root_splitter.addWidget(self.main_splitter)
		self.root_splitter.addWidget(self.console_output)
		self.root_splitter.setStretchFactor(1, 1)  # Make top grow with window
		
		self.setCentralWidget(self.root_splitter)

		# Initially hide project tree, stop button and console
		left_panel.hide()
		self.console_output.hide()
		self.stop_button.hide()

	def _create_left_panel(self):
		"""Create the left project panel"""
		panel = QFrame()
		panel.setFrameStyle(QFrame.NoFrame)
		layout = QVBoxLayout(panel)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)
		
		# Project header
		header = QLabel("Project")
		header.setObjectName("panel_header")
		header.setFixedHeight(24)
		header.setContentsMargins(8, 4, 8, 4)
		layout.addWidget(header)
		
		# Project tree with custom icons

		folder_path = os.path.expanduser("~")

		self.model = QFileSystemModel()
		self.model.setIconProvider(FileIconProvider(self.folder_icon, self.file_icon))
		
		self.tree = QTreeView()
		self.tree.setModel(self.model)
		self.tree.setHeaderHidden(True)
		self.tree.setRootIsDecorated(True)
		self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
		self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
		self.tree.doubleClicked.connect(self._on_tree_double_click)
		
		# Hide all columns except name
		for i in range(1, self.model.columnCount()):
			self.tree.hideColumn(i)
			
		layout.addWidget(self.tree)
		return panel

	def _create_editor_panel(self):
		"""Create the main editor panel"""
		panel = QFrame()
		panel.setFrameStyle(QFrame.NoFrame)
		layout = QVBoxLayout(panel)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.setSpacing(0)
		
		# Editor tabs
		self.editor_tabs = QTabWidget()
		self.editor_tabs.setObjectName("editor_tabs")
		self.editor_tabs.setTabPosition(QTabWidget.North)
		self.editor_tabs.setTabsClosable(True)
		self.editor_tabs.setMovable(True)
		self.editor_tabs.tabCloseRequested.connect(self.close_tab)
		self.editor_tabs.currentChanged.connect(self._tab_changed)
		
		# Add new tab button
		new_tab_btn = QPushButton("+")
		new_tab_btn.setObjectName("new_tab_button")
		new_tab_btn.setFixedSize(24, 24)
		new_tab_btn.clicked.connect(self._create_new_tab)
		self.editor_tabs.setCornerWidget(new_tab_btn, Qt.TopRightCorner)
		
		layout.addWidget(self.editor_tabs)
		
		return panel
		
	def _adjust_input_height(self):
		"""Adjust input field height based on content"""
		doc = self.console_input.document()
		height = doc.size().height() + 10
		self.console_input.setFixedHeight(min(int(height), 150))
		
	def run_command(self, cmdlet, args):
		"""Execute a Python command and show output in console"""
		# Clear previous process if any
		if getattr(self, 'console_process') is not None:
			self.console_process.kill()
			self.console_process = None
			
		self.console_output.clear()
		# Create and start process
		self.console_process = BuildThread(self.console_output)
		self.console_process.finished.connect(self._command_finished)
		
		# Start Python with the command
		self.console_process.start_build(cmdlet, args)
		self.console_output.show()
	def _command_finished(self):
		self.building_label.hide()
		self.console_output.insertPlainText("Finished Build.")
		self.run_button.setIcon(QIcon(resource_path("./icons/run_file.svg")))
	def _create_toolbar(self):
		toolbar = QToolBar()
		toolbar.setObjectName("main_toolbar")
		toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
		toolbar.setIconSize(QSize(16, 16))
		toolbar.setFloatable(False)
		toolbar.setMovable(False)
		
		# Add some common actions (icons would be loaded from resources in real app)
		self.addToolBar(toolbar)

	def _create_actions(self):
		# File actions
		self.new_file_act = QAction("New File", self)
		self.new_file_act.setShortcut("Ctrl+N")
		self.new_file_act.triggered.connect(self._create_new_tab)
		
		self.open_file_act = QAction("Open File...", self)
		self.open_file_act.setShortcut("Ctrl+O")
		self.open_file_act.triggered.connect(self.open_file)
		
		self.open_project_act = QAction("Open Project...", self)
		self.open_project_act.triggered.connect(self.open_project)
		
		self.save_act = QAction("Save", self)
		self.save_act.setShortcut("Ctrl+S")
		self.save_act.triggered.connect(self.save_file)
		
		self.save_all_act = QAction("Save All", self)
		self.save_all_act.setShortcut("Ctrl+Shift+S")
		self.save_all_act.triggered.connect(self.save_all_files)
		
		self.close_tab_act = QAction("Close Tab", self)
		self.close_tab_act.setShortcut("Ctrl+W")
		self.close_tab_act.triggered.connect(self.close_current_tab)
		
		self.exit_act = QAction("Exit", self)
		self.exit_act.triggered.connect(self.close)
		
		# View actions
		self.toggle_project_act = QAction("Project", self)
		self.toggle_project_act.setShortcut("Alt+1")
		self.toggle_project_act.setCheckable(True)
		self.toggle_project_act.triggered.connect(self.toggle_project_panel)
		
		# Tab size actions
		self.tab2_act = QAction("2", self, checkable=True)
		self.tab2_act.triggered.connect(lambda: self.set_tab_size(2))
		self.tab4_act = QAction("4", self, checkable=True)
		self.tab4_act.triggered.connect(lambda: self.set_tab_size(4))
		self.tab8_act = QAction("8", self, checkable=True)
		self.tab8_act.triggered.connect(lambda: self.set_tab_size(8))
		self.tab_actions = [self.tab2_act, self.tab4_act, self.tab8_act]

		self.build_file_act = QAction("Build", self)
		self.build_file_act.setShortcut("Ctrl+B")
		self.build_file_act.triggered.connect(self.build_file)

		shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
		shortcut.activated.connect(self.open_command_palette)

		
	def build_file(self):
		if getattr(self, 'console_process') is not None:
			self.console_process.kill()
			self.console_process = None
		current_editor = self.get_current_editor()
		self.run_button.hide()
		self.debugrun_button.hide()
		self.stop_button.show()
		self.console_output.show()
		if current_editor and hasattr(current_editor, 'file_path'):
			file_path = current_editor.file_path

			self.building_label.show()
			self.run_command(sys.executable, (file_path,))

	def _create_menus(self):
		menu_bar = self.menuBar()
		
		# File menu
		file_menu = menu_bar.addMenu("File")
		file_menu.addAction(self.new_file_act)
		file_menu.addAction(self.open_file_act)
		file_menu.addAction(self.open_project_act)
		file_menu.addSeparator()
		file_menu.addAction(self.save_act)
		file_menu.addAction(self.save_all_act)
		file_menu.addSeparator()
		file_menu.addAction(self.close_tab_act)
		file_menu.addSeparator()
		file_menu.addAction(self.exit_act)
		
		# Edit menu
		edit_menu = menu_bar.addMenu("Edit")
		
		# View menu
		view_menu = menu_bar.addMenu("View")
		view_menu.addAction(self.toggle_project_act)
		view_menu.addSeparator()
		
		# Code menu
		code_menu = menu_bar.addMenu("Code")
		tab_menu = code_menu.addMenu("Tab Size")
		for action in self.tab_actions:
			tab_menu.addAction(action)
		self.tab4_act.setChecked(True)
		
		# Tools menu
		build_menu = menu_bar.addMenu("Build")
		build_menu.addAction(self.build_file_act)
		
		# Help menu
		help_menu = menu_bar.addMenu("Help")

	def _create_status_bar(self):
		status = QStatusBar()
		status.setObjectName("snakeide_statusbar")

		status
		
		# Left side info
		self.cursor_label = QLabel("Ln 1, Col 1")
		self.cursor_label.setObjectName("status_label")
		status.addWidget(self.cursor_label)
		
		self.encoding_label = QLabel("UTF-8")
		self.encoding_label.setObjectName("status_label")
		status.addWidget(self.encoding_label)

		self.building_label = QLabel("Running File...")
		self.building_label.setObjectName("building_label")
		status.addWidget(self.building_label)
		self.building_label.hide()
		
		build_icons_container = QWidget()
		self.build_icons = QHBoxLayout()

		build_icons_container.setLayout(self.build_icons)

		self.run_button = QPushButton()
		self.run_button.setObjectName("RunBTN")
		self.run_button.setIcon(QIcon(resource_path("./icons/run_file.svg")))

		self.run_button.clicked.connect(self.build_file)

		self.stop_button = QPushButton()
		self.stop_button.setObjectName("stopBTN")
		self.stop_button.setIcon(QIcon(resource_path("./icons/stop_execution.svg")))

		self.stop_button.clicked.connect(self.stop_execution)

		self.debugrun_button = QPushButton()
		self.debugrun_button.setObjectName("debugRunBTN")
		self.debugrun_button.setIcon(QIcon(resource_path("./icons/debug_run.svg")))

		self.debugrun_button.clicked.connect(self.debug_run)

		self.continue_button = QPushButton()
		self.continue_button.setObjectName("ContinueBTN")
		self.continue_button.setIcon(QIcon(resource_path("./icons/resume_execution.svg")))

		self.continue_button.clicked.connect(self.continue_run)

		self.build_icons.addWidget(self.run_button)
		self.build_icons.addWidget(self.stop_button)
		self.build_icons.addWidget(self.debugrun_button)
		self.build_icons.addWidget(self.continue_button)


		# Right side info
		status.addPermanentWidget(build_icons_container)
		
		self.setStatusBar(status)
		
		# Connect cursor position updates
		self.editor_tabs.currentChanged.connect(self._connect_current_editor_signals)
	def stop_execution(self):
		if getattr(self, 'console_process') is not None:
			self.console_process.kill()
			self.console_process = None
		self.run_button.show()
		self.debugrun_button.show()
		self.stop_button.hide()

	def debug_run(self):
		if getattr(self, 'console_process') is not None:
			self.console_process.kill()
			self.console_process = None
		self.debugrun_button.hide()
		self.run_button.hide()
		self.stop_button.show()
		self.console_output.show()
		self.console_output.clear()
		# Create and start process
		self.console_process = DebugThread(self.console_output, self.get_current_editor())
		self.console_process.finished.connect(self._command_finished)

		breakpoints = self.get_current_editor().get_breakpoints()
		if breakpoints:
			# Create a temporary file with breakpoint commands
			bp_file = os.path.join(os.path.dirname(__file__), "breakpoints.tmp")
			with open(bp_file, 'w') as f:
				for line in breakpoints:
					f.write(f"__import__('pdb').set_trace()  # BREAKPOINT-LINE:{line}\n")
			
			# Inject breakpoints into the code
			original_code = self.get_current_editor().toPlainText()
			lines = original_code.split('\n')
			for line_num in sorted(breakpoints, reverse=True):
				if 0 <= line_num < len(lines):
					lines.insert(line_num, f"__import__('pdb').set_trace()  # BREAKPOINT-LINE:{line_num}")
			
			modified_code = '\n'.join(lines)
			
			# Create a temporary file to run
			temp_file = os.path.join(os.path.dirname(__file__), "temp_run.py")
			with open(temp_file, 'w') as f:
				f.write(modified_code)
			
			# Run the modified file
			self.console_process.start_build(sys.executable, [temp_file])
			return
		else:
			self.build_file()
		
	def _connect_current_editor_signals(self):
		"""Connect signals for the current editor"""
		editor = self.get_current_editor()
		if editor:
			editor.cursorPositionChanged.connect(self._update_cursor_position)
			self._update_cursor_position()

	def continue_run(self):
		breakpoints = self.get_current_editor().get_breakpoints()
		if self.console_process:
			if breakpoints:
				self.console_process.write('continue\n')
		
	def _update_cursor_position(self):
		"""Update cursor position in status bar"""
		editor = self.get_current_editor()
		if editor:
			cursor = editor.textCursor()
			line = cursor.blockNumber() + 1
			col = cursor.columnNumber() + 1
			self.cursor_label.setText(f"Ln {line}, Col {col}")

	def _apply_snakeide_theme(self):
		# snakeide Darcula color scheme
		snakeide_style = f"""
		QMainWindow {{
			background-color: #2B2B2B;
			color: #A9B7C6;
			font-family: "Segoe UI";
		}}
		
		QDialog {{
			background-color: #2B2B2B;
			color: #A9B7C6;
			font-family: "Segoe UI";
		}}
		
		QLineEdit {{
			background-color: #3C3F41;
			color: #A9B7C6;
			border: 1px solid #5E6060;
			padding: 5px;
			border-radius: 3px;
		}}
		
		QLabel {{
			color: #A9B7C6;
		}}
	
		QPushButton {{
			background-color: #3C3F41;
			color: #A9B7C6;
			border: 1px solid #5E6060;
			padding: 5px 10px;
			border-radius: 3px;
		}}
		
		QPushButton:hover {{
			background-color: #4C5052;
		}}
		
		QPushButton:pressed {{
			background-color: #2B2B2B;
		}}
		
		QMenuBar {{
			background-color: #3C3F41;
			color: #A9B7C6;
			border: none;
			padding: 2px;
		}}

		QTextEdit[objectName="Console"]{{
			font-family: 'Cascadia Mono';
			font-size: 16px;
			background-color: #2B2B2B;
			color: #EEEEEE;
			margin: 5px;
			border: 1px solid #424242;
		}}

		QTextEdit[objectName="Console"]:focus{{
			border: 1px solid #696969;
		}}
		
		QMenuBar::item {{
			background-color: transparent;
			padding: 4px 8px;
			margin: 0px;
		}}
		
		QMenuBar::item:selected {{
			background-color: #4C5052;
		}}
		
		QMenuBar::item:pressed {{
			background-color: #4C5052;
		}}
		
		QMenu {{
			background-color: #3C3F41;
			color: #A9B7C6;
			border: 1px solid #5E6060;
			margin: 0px;
		}}
		
		QMenu::item {{
			padding: 4px 20px;
			margin: 0px;
		}}
		
		QMenu::item:selected {{
			background-color: #4C5052;
		}}
		
		QMenu::separator {{
			height: 1px;
			background-color: #5E6060;
			margin: 2px 0px;
		}}
		
		QToolBar {{
			background-color: #3C3F41;
			border: none;
			spacing: 2px;
			padding: 2px;
		}}
		
		QSplitter {{
			background-color: #2B2B2B;
		}}
		
		QSplitter::handle {{
			background-color: #3C3F41;
			width: 1px;
			height: 1px;
		}}
		
		QSplitter::handle:hover {{
			background-color: #4C5052;
		}}
		
		QTabWidget::pane {{
			background-color: #2B2B2B;
			border: none;
		}}
		
		QTabBar {{
			background-color: #3C3F41;
			border-bottom: 1px solid #323232;
		}}
		
		QTabBar::tab {{
			background-color: #3C3F41;
			color: #A9B7C6;
			padding: 4px 8px;
			border: none;
			min-width: 80px;
		}}
		
		QTabBar::tab:selected {{
			background-color: #4C5052;
			border-bottom: 2px solid #6897BB;
		}}
		
		QTabBar::tab:hover {{
			background-color: #4C5052;
		}}
		
		QTabBar::close-button {{
			image: url('{resource_path('icons/close_tab.svg')}');
			subcontrol-position: right;
			padding: 2px;
		}}
		
		QTabBar::close-button:hover {{
			background-color: #5E6060;
			border-radius: 3px;
		}}
		
		QPushButton#new_tab_button {{
			background-color: #3C3F41;
			color: #A9B7C6;
			border: none;
			font-weight: bold;
		}}
		
		QPushButton#new_tab_button:hover {{
			background-color: #4C5052;
		}}
		
		QLabel[objectName="panel_header"] {{
			background-color: #3C3F41;
			color: #A9B7C6;
			font-weight: bold;
			font-size: 11px;
			border-bottom: 1px solid #323232;
		}}

		QLabel[objectName="building_label"] {{
			color: #A9B7C6;
			padding: 2px 4px;
		}}
		
		QPlainTextEdit[objectName^="editor_"] {{
			background-color: #2B2B2B;
			color: #A9B7C6;
			border: none;
			selection-background-color: #214283;
			selection-color: #A9B7C6;
		}}
		
		QTreeView {{
			background-color: #3C3F41;
			color: #A9B7C6;
			border: none;
			outline: none;
			show-decoration-selected: 0;
		}}
		
		QTreeView::item {{
			padding: 2px;
		}}
		
		QTreeView::item:selected {{
			background-color: #4C5052;
		}}
		
		QTreeView::item:hover {{
			background-color: #4C5052;
		}}
		
		QTreeView::branch:has-children:!has-siblings:closed,
		QTreeView::branch:closed:has-children:has-siblings {{
			border-image: none;
			margin: 2px;
			image: url("{resource_path('icons/caret-right.svg')}");
		}}
		
		QTreeView::branch:open:has-children:!has-siblings,
		QTreeView::branch:open:has-children:has-siblings {{
			border-image: none;
			margin: 2px;
			image: url("{resource_path('icons/caret-down.svg')}");
		}}
		
		QStatusBar {{
			background-color: #3C3F41;
			color: #A9B7C6;
			border-top: 1px solid #323232;
		}}
		
		QStatusBar[objectName="snakeide_statusbar"] {{
			font-size: 11px;
		}}
		
		QLabel[objectName="status_label"] {{
			color: #A9B7C6;
			padding: 2px 4px;
		}}
		
		QScrollBar:vertical {{
			background-color: #3C3F41;
			width: 12px;
			border: none;
		}}
		
		QScrollBar::handle:vertical {{
			background-color: #5E6060;
			min-height: 20px;
			border-radius: 6px;
			margin: 0px 2px;
		}}
		
		QScrollBar::handle:vertical:hover {{
			background-color: #7C7C7C;
		}}
		
		QScrollBar::add-line:vertical,
		QScrollBar::sub-line:vertical {{
			height: 0px;
		}}
		
		QScrollBar:horizontal {{
			background-color: #3C3F41;
			height: 12px;
			border: none;
		}}
		
		QScrollBar::handle:horizontal {{
			background-color: #5E6060;
			min-width: 20px;
			border-radius: 6px;
			margin: 2px 0px;
		}}
		
		QScrollBar::handle:horizontal:hover {{
			background-color: #7C7C7C;
		}}
		
		QScrollBar::add-line:horizontal,
		QScrollBar::sub-line:horizontal {{
			width: 0px;
		}}

		QDialog[objectName="CommandPalette"]{{
			background-color: #3C3F41;
			color: #A9B7C6;
			border-top: 1px solid #323232;
		}}
		QListWidget[objectName="CommandPaletteList"]{{
			background-color: #3C3F41;
			color: #A9B7C6;
			border-top: 1px solid #323232;
		}}
		"""
		self.setStyleSheet(snakeide_style)

	def toggle_project_panel(self):
		"""Toggle project panel visibility"""
		left_panel = self.main_splitter.widget(0)
		if left_panel.isVisible():
			left_panel.hide()
			self.toggle_project_act.setChecked(False)
		else:
			left_panel.show()
			self.toggle_project_act.setChecked(True)

	def set_tab_size(self, size):
		"""Set tab size for editor"""
		self._tab_size = size
		for editor_info in self.open_files.values():
			editor = editor_info["editor"]
			fm = QFontMetrics(editor.font())
			editor.setTabStopDistance(size * fm.horizontalAdvance(' '))
		
		for act in self.tab_actions:
			act.setChecked(False)
		getattr(self, f'tab{size}_act').setChecked(True)

	def open_file(self):
		"""Open a single file"""
		path, _ = QFileDialog.getOpenFileName(
			self, "Open File", "", 
			"Python Files (*.py);;All Files (*.*)"
		)
		if path:
			self._open_file(path)

	def open_project(self):
		path = QFileDialog.getExistingDirectory(self, "Open Project", "")
		self._open_folder(path)

	def _create_new_tab(self):
		"""Create a new empty tab"""
		self._open_file(None, "Untitled.py")

	def _open_file(self, path, title="Untitled.py"):
		"""Open a file in a new tab or switch to existing tab"""
		# Check if file is already open
		if path and path in self.open_files:
			tab_index = self.editor_tabs.indexOf(self.open_files[path]["widget"])
			self.editor_tabs.setCurrentIndex(tab_index)
			return
			
		# Create new editor
		editor = CodeEditor()
		editor.setObjectName("editor_" + str(len(self.open_files)))
		editor.file_path = path
		
		# Set tab size
		fm = QFontMetrics(editor.font())
		editor.setTabStopDistance(self._tab_size * fm.horizontalAdvance(' '))
		editor.setLineWrapMode(QPlainTextEdit.NoWrap)
		
		# Create highlighter
		highlighter = PythonHighlighter(editor.document())
		
		# Create container widget for editor
		container = QWidget()
		layout = QVBoxLayout(container)
		layout.setContentsMargins(0, 0, 0, 0)
		layout.addWidget(editor)
		
		# Add to tabs
		tab_index = self.editor_tabs.addTab(container, title)
		self.editor_tabs.setCurrentIndex(tab_index)
		
		# Store file info
		self.open_files[path] = {
			"editor": editor,
			"highlighter": highlighter,
			"widget": container
		}
		
		# Load file if path exists
		if path and os.path.exists(path):
			try:
				with open(path, 'r', encoding='utf-8') as f:
					text = f.read()
				editor.setPlainText(text)
				
				# Set tab title to filename
				filename = os.path.basename(path)
				self.editor_tabs.setTabText(tab_index, filename)
				
				self.statusBar().showMessage(f"Opened: {filename}", 2000)
			except Exception as e:
				QMessageBox.warning(self, "Error", f"Could not open file: {str(e)}")
		
		# Connect editor signals
		editor.cursorPositionChanged.connect(self._update_cursor_position)
		self._update_cursor_position()

	def get_current_editor(self):
		"""Get the current editor widget"""
		current_widget = self.editor_tabs.currentWidget()
		if current_widget:
			# The editor is the first child of the container
			return current_widget.findChild(CodeEditor)
		return None

	def save_file(self):
		"""Save current file"""
		editor = self.get_current_editor()
		if not editor:
			return
			
		path = editor.file_path
		if path:
			try:
				with open(path, 'w', encoding='utf-8') as f:
					f.write(editor.toPlainText())
				self.statusBar().showMessage(f"Saved: {os.path.basename(path)}", 2000)
			except Exception as e:
				QMessageBox.warning(self, "Error", f"Could not save file: {str(e)}")
		else:
			# Save As dialog
			self.save_file_as()

	def save_file_as(self):
		"""Save current file with a new name"""
		editor = self.get_current_editor()
		if not editor:
			return
			
		path, _ = QFileDialog.getSaveFileName(
			self, "Save File", "", 
			"Python Files (*.py);;All Files (*.*)"
		)
		if path:
			try:
				with open(path, 'w', encoding='utf-8') as f:
					f.write(editor.toPlainText())
				
				# Update tab info
				editor.file_path = path
				filename = os.path.basename(path)
				tab_index = self.editor_tabs.currentIndex()
				self.editor_tabs.setTabText(tab_index, filename)
				
				# Update open files
				old_path = None
				for p, info in self.open_files.items():
					if info["editor"] == editor:
						old_path = p
						break
				if old_path is not None:
					del self.open_files[old_path]
				self.open_files[path] = {
					"editor": editor,
					"highlighter": self.open_files[old_path]["highlighter"],
					"widget": self.open_files[old_path]["widget"]
				}
				
				self.statusBar().showMessage(f"Saved: {filename}", 2000)
			except Exception as e:
				QMessageBox.warning(self, "Error", f"Could not save file: {str(e)}")

	def save_all_files(self):
		"""Save all open files"""
		for path, file_info in self.open_files.items():
			if path:  # Skip untitled files
				editor = file_info["editor"]
				try:
					with open(path, 'w', encoding='utf-8') as f:
						f.write(editor.toPlainText())
				except Exception as e:
					QMessageBox.warning(self, "Error", f"Could not save {path}: {str(e)}")
		self.statusBar().showMessage("All files saved", 2000)

	def close_current_tab(self):
		"""Close the current tab"""
		current_index = self.editor_tabs.currentIndex()
		if current_index >= 0:
			self.close_tab(current_index)

	def close_tab(self, index, confirmation=False):
		"""Close a tab by index"""
		widget = self.editor_tabs.widget(index)
		
		# Find the file path for this tab
		path = None
		for p, file_info in self.open_files.items():
			if file_info["widget"] == widget:
				path = p
				break
		
		# Check if we need to save
		if path:
			editor = self.open_files[path]["editor"]
			if confirmation:
				if editor.document().isModified():
					reply = QMessageBox.question(
						self, "Save Changes?",
						f"Do you want to save changes to {os.path.basename(path)}?",
						QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel
					)
					if reply == QMessageBox.Save:
						self.save_file()
					elif reply == QMessageBox.Cancel:
						return
			self.save_file()
		
		# Remove the tab
		self.editor_tabs.removeTab(index)
		
		# Remove from open files
		if path in self.open_files:
			del self.open_files[path]

	def _tab_changed(self, index):
		"""Handle tab change event"""
		if index >= 0:
			self._update_cursor_position()

	def _open_folder(self, path=None):
		if path:
			path = os.path.abspath(path)

			for tab_index in range(self.editor_tabs.count()-1, -1, -1):
				self.close_tab(tab_index)

			# Set model to parent so the folder is visible as a child
			self.model.setRootPath(path)
			self.tree.setRootIndex(self.model.index(path))

			# UI updates
			left_panel = self.main_splitter.widget(0)
			left_panel.show()
			self.toggle_project_act.setChecked(True)

			project_name = os.path.basename(path)
			self.config['current_project'] = path
			self.setWindowTitle(f"{project_name} - Snake IDE")



	def _on_tree_double_click(self, index: QModelIndex):
		"""Handle tree double click"""
		if not index.isValid():
			return
			
		path = self.model.filePath(index)
		if os.path.isfile(path):
			self._open_file(path)

	def _on_tree_context_menu(self, point):
		"""Handle tree context menu"""
		index = self.tree.indexAt(point)
		if not index.isValid():
			# If clicking on empty space, use root path
			if self.model.rootPath():
				path = self.model.rootPath()
			else:
				return
		else:
			path = self.model.filePath(index)
			if not os.path.isdir(path):
				path = os.path.dirname(path)
				
		menu = QMenu(self)
		new_file = menu.addAction("New Python File")
		new_folder = menu.addAction("New Directory")
		rename = menu.addAction("Rename")
		delete_selected = menu.addAction("Delete Selected")
		menu.addSeparator()
		
		action = menu.exec_(self.tree.viewport().mapToGlobal(point))
		
		if action == new_file:
			name, ok = QFileDialog.getSaveFileName(
				self, "New Python File", 
				os.path.join(path, "untitled.py"),
				"Python Files (*.py)"
			)
			if ok and name:
				try:
					with open(name, 'w', encoding='utf-8') as f:
						f.write("# New Python file\n")
					self._open_file(name)
				except Exception as e:
					QMessageBox.warning(self, "Error", str(e))
					
		elif action == new_folder:
			dialog = CustomInputDialog(self, "New Folder", "Folder name:")
			if dialog.exec_() == QDialog.Accepted:
				folder_name = dialog.get_text()
				if folder_name:
					try:
						new_folder_path = os.path.join(path, folder_name)
						os.makedirs(new_folder_path, exist_ok=True)
					except Exception as e:
						QMessageBox.warning(self, "Error", str(e))
						
		elif action == rename:
			if index.isValid():
				old_name = os.path.basename(path)
				dialog = CustomInputDialog(self, "Rename", "New name:", old_name)
				if dialog.exec_() == QDialog.Accepted:
					new_name = dialog.get_text()
					if new_name and new_name != old_name:
						try:
							parent_dir = os.path.dirname(path)
							new_path = os.path.join(parent_dir, new_name)
							os.rename(path, new_path)
						except Exception as e:
							QMessageBox.warning(self, "Error", str(e))
			
		elif action == delete_selected:
			if index.isValid():
				path = self.model.filePath(index)
				reply = QMessageBox.question(
					self, "Confirm Delete",
					f"Are you sure you want to delete '{os.path.basename(path)}'?",
					QMessageBox.Yes | QMessageBox.No
				)
				if reply == QMessageBox.Yes:
					try:
						if os.path.isfile(path):
							os.remove(path)
						else:
							shutil.rmtree(path) 
					except Exception as e:
						QMessageBox.warning(self, "Error", str(e))
					
	def closeEvent(self, event):
		self.save_config()
		event.accept()

class FileIconProvider(QFileIconProvider):
	"""Custom icon provider for file system model"""
	def __init__(self, folder_icon, file_icons):
		super().__init__()
		self.folder_icon = folder_icon
		self.file_icons = file_icons
		
	def icon(self, type: QFileInfo):
		if isinstance(type, QFileInfo):
			if type.isDir():
				return self.folder_icon

			return self.file_icons.get(type.completeSuffix(), self.file_icons['general_file'])
		return type

if __name__ == '__main__':
	app = QApplication(sys.argv)
	app.setApplicationName("Snake IDE")    
	window = snakeideEditor()
	window.show()
	
	sys.exit(app.exec())