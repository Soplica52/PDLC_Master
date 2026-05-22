import sys
import json
import time
import csv
import os
from datetime import datetime
from collections import deque

import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QComboBox, QPushButton, QLabel, 
                             QSlider, QSpinBox, QGroupBox, QMessageBox, QGridLayout,
                             QRadioButton, QButtonGroup, QFileDialog, QTextEdit)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import pyqtgraph as pg

# ==========================================
# 1. Background Serial Thread (Reverted to your working version)
# ==========================================
class SerialWorker(QThread):
    data_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)
    debug_message = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.serial_port = serial.Serial()
        self.serial_port.baudrate = 115200
        self.serial_port.timeout = 1 
        self.is_running = False

    def connect_port(self, port_name):
        self.serial_port.port = port_name
        try:
            self.serial_port.open()
            self.is_running = True
            self.start()
            return True
        except Exception as e:
            self.error_occurred.emit(f"Could not open port: {e}")
            return False

    def disconnect_port(self):
        self.is_running = False
        self.wait() 
        if self.serial_port.is_open:
            self.serial_port.close()

    def send_line(self, command):
        if self.serial_port.is_open:
            try:
                self.debug_message.emit(f"TX -> {command.strip()}")
                self.serial_port.write(command.encode('utf-8'))
            except Exception as e:
                self.error_occurred.emit(f"Write error: {e}")

    def send_command(self, target_lux):
        self.send_line(f"T:{target_lux}\n")

    def run(self):
        while self.is_running and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    # Your original working readline logic
                    line = self.serial_port.readline().decode('utf-8').strip()
                    if line:
                        self.debug_message.emit(f"RX <- {line.strip()}")
                        data = json.loads(line)
                        self.data_received.emit(data)
                else:
                    # Tiny sleep to prevent the UI from freezing
                    self.msleep(10)
            except json.JSONDecodeError:
                pass # Ignore malformed JSON chunks safely
            except Exception as e:
                self.error_occurred.emit(f"Read error: {e}")
                self.is_running = False

# ==========================================
# 2. Main GUI Application
# ==========================================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("STM32 Smart Window Dashboard")
        self.resize(1050, 750)

        self.buffer_size = 300
        self.time_data = deque(maxlen=self.buffer_size)
        self.lux_data = deque(maxlen=self.buffer_size)
        self.target_data = deque(maxlen=self.buffer_size)
        self.led_data = deque(maxlen=self.buffer_size)
        self.foil_data = deque(maxlen=self.buffer_size)
        self.real_time_data = deque(maxlen=self.buffer_size)
        self.start_time = time.time()

        self.is_logging = False
        self.csv_file = None
        self.csv_writer = None
        
        # New State Flags
        self.is_measuring = False
        self.control_mode = "auto"

        self.setup_ui()

        self.worker = SerialWorker()
        self.worker.data_received.connect(self.update_data)
        self.worker.error_occurred.connect(self.show_error)
        self.worker.debug_message.connect(self.log_debug)

        self.refresh_ports()

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        # --- Top Bar: Connection ---
        conn_group = QGroupBox("Serial Connection")
        conn_layout = QHBoxLayout()
        self.port_combo = QComboBox()
        self.refresh_btn = QPushButton("Refresh Ports")
        self.refresh_btn.clicked.connect(self.refresh_ports)
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self.toggle_connection)
        
        conn_layout.addWidget(QLabel("COM Port:"))
        conn_layout.addWidget(self.port_combo)
        conn_layout.addWidget(self.refresh_btn)
        conn_layout.addWidget(self.connect_btn)
        conn_layout.addStretch()
        conn_group.setLayout(conn_layout)
        main_layout.addWidget(conn_group)

        # --- Middle: Graphing ---
        pg.setConfigOption('background', 'w')
        pg.setConfigOption('foreground', 'k')
        self.plot_widget = pg.PlotWidget(title="Live Metrics (Lux vs Time)")
        self.plot_widget.setLabel('left', 'Value')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.plot_widget.addLegend()
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        
        self.curve_lux = self.plot_widget.plot(pen=pg.mkPen('b', width=2), name="Lux")
        self.curve_target = self.plot_widget.plot(pen=pg.mkPen('g', width=2, style=Qt.DashLine), name="Target")
        self.curve_led = self.plot_widget.plot(pen=pg.mkPen('r', width=2), name="LED %")
        main_layout.addWidget(self.plot_widget, stretch=3)

        # --- Bottom section ---
        bottom_layout = QHBoxLayout()

        # 1. Live Data Readouts
        readout_group = QGroupBox("Live Metrics")
        readout_layout = QGridLayout()
        self.lbl_lux = QLabel("Lux: --")
        self.lbl_target = QLabel("Target: --")
        self.lbl_effort = QLabel("Effort: --")
        self.lbl_foil = QLabel("Foil V: --")
        self.lbl_led = QLabel("LED %: --")
        
        for lbl in [self.lbl_lux, self.lbl_target, self.lbl_effort, self.lbl_foil, self.lbl_led]:
            lbl.setStyleSheet("font-size: 14px; font-weight: bold;")

        readout_layout.addWidget(self.lbl_lux, 0, 0)
        readout_layout.addWidget(self.lbl_target, 0, 1)
        readout_layout.addWidget(self.lbl_effort, 1, 0)
        readout_layout.addWidget(self.lbl_foil, 1, 1)
        readout_layout.addWidget(self.lbl_led, 2, 0, 1, 2)
        readout_group.setLayout(readout_layout)
        bottom_layout.addWidget(readout_group, stretch=1)

        # 2. Measurement & Logging Controls
        meas_log_group = QGroupBox("Measurement & Logging")
        meas_log_layout = QVBoxLayout()
        
        meas_btns_layout = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_pause = QPushButton("Pause")
        self.btn_stop = QPushButton("Stop")
        
        self.btn_start.clicked.connect(self.start_measurements)
        self.btn_pause.clicked.connect(self.pause_measurements)
        self.btn_stop.clicked.connect(self.stop_measurements)
        
        # Initially disabled until connected
        for btn in (self.btn_start, self.btn_pause, self.btn_stop):
            btn.setEnabled(False)
            meas_btns_layout.addWidget(btn)
            
        meas_log_layout.addLayout(meas_btns_layout)

        self.log_btn = QPushButton("Start Recording CSV")
        self.log_btn.setCheckable(True)
        self.log_btn.toggled.connect(self.toggle_logging)
        self.lbl_log_status = QLabel("Status: Not Recording")
        self.btn_export_csv = QPushButton("Export Graph Data to CSV")
        self.btn_export_csv.clicked.connect(self.export_current_data)
        meas_log_layout.addWidget(self.log_btn)
        meas_log_layout.addWidget(self.lbl_log_status)
        meas_log_layout.addWidget(self.btn_export_csv)
        
        meas_log_group.setLayout(meas_log_layout)
        bottom_layout.addWidget(meas_log_group, stretch=1)

        # 3. Control Mode & Overrides
        control_group = QGroupBox("System Controls")
        control_layout = QVBoxLayout()

        # Mode Selection
        mode_layout = QHBoxLayout()
        self.radio_auto = QRadioButton("Auto Mode")
        self.radio_manual = QRadioButton("Manual Mode")
        self.radio_auto.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.radio_auto)
        self.mode_group.addButton(self.radio_manual)
        self.mode_group.buttonClicked.connect(self._on_control_mode_clicked)
        mode_layout.addWidget(self.radio_auto)
        mode_layout.addWidget(self.radio_manual)
        control_layout.addLayout(mode_layout)
        
        # Target Lux Control
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Target Lux:"))
        self.target_spinbox = QSpinBox()
        self.target_spinbox.setRange(0, 2000)
        self.target_spinbox.setValue(700)
        self.target_slider = QSlider(Qt.Horizontal)
        self.target_slider.setRange(0, 2000)
        self.target_slider.setValue(700)
        self.target_slider.valueChanged.connect(self.target_spinbox.setValue)
        self.target_spinbox.valueChanged.connect(self.target_slider.setValue)
        self.target_slider.sliderReleased.connect(self.send_target_command)
        self.target_spinbox.editingFinished.connect(self.send_target_command)
        
        target_layout.addWidget(self.target_spinbox)
        control_layout.addLayout(target_layout)
        control_layout.addWidget(self.target_slider)

        # Manual Overrides (LED & Foil)
        manual_layout = QHBoxLayout()
        self.lbl_led_intensity = QLabel("LED %:")
        self.led_manual_slider = QSlider(Qt.Horizontal)
        self.led_manual_slider.setRange(0, 100)
        self.led_manual_slider.setValue(0)
        self.led_manual_slider.sliderReleased.connect(self.send_led_override)
        
        self.btn_foil = QPushButton("PDLC Foil: Off")
        self.btn_foil.setCheckable(True)
        self.btn_foil.toggled.connect(self.send_foil_override)
        
        manual_layout.addWidget(self.lbl_led_intensity)
        manual_layout.addWidget(self.led_manual_slider)
        manual_layout.addWidget(self.btn_foil)
        control_layout.addLayout(manual_layout)

        self.btn_sync = QPushButton("Sync Settings to STM32")
        self.btn_sync.setStyleSheet("background-color: #9C27B0; color: white;")
        self.btn_sync.clicked.connect(self.sync_settings)
        control_layout.addWidget(self.btn_sync)

        control_group.setLayout(control_layout)
        bottom_layout.addWidget(control_group, stretch=2)

        main_layout.addLayout(bottom_layout, stretch=1)

        debug_group = QGroupBox("Serial Debugger")
        debug_layout = QHBoxLayout()
        self.debug_console = QTextEdit()
        self.debug_console.setReadOnly(True)
        self.debug_console.setMaximumHeight(150)
        self.btn_clear_debug = QPushButton("Clear Debug Log")
        self.btn_clear_debug.clicked.connect(self.debug_console.clear)
        debug_layout.addWidget(self.debug_console, stretch=1)
        debug_layout.addWidget(self.btn_clear_debug)
        debug_group.setLayout(debug_layout)
        main_layout.addWidget(debug_group)
        
        # Initialize UI state
        self.apply_control_mode("auto", notify_device=False)

    # ==========================================
    # Logic Methods
    # ==========================================
    def refresh_ports(self):
        self.port_combo.clear()
        ports = serial.tools.list_ports.comports()
        for port, desc, hwid in sorted(ports):
            self.port_combo.addItem(f"{port}")

    def toggle_connection(self):
        if not self.worker.is_running:
            port = self.port_combo.currentText()
            if port:
                if self.worker.connect_port(port):
                    self.connect_btn.setText("Disconnect")
                    self.connect_btn.setStyleSheet("background-color: #ff9999;")
                    self.port_combo.setEnabled(False)
                    self.refresh_btn.setEnabled(False)
                    
                    self.time_data.clear()
                    self.lux_data.clear()
                    self.target_data.clear()
                    self.led_data.clear()
                    self.foil_data.clear()
                    self.real_time_data.clear()
                    
                    self.apply_control_mode(self.control_mode)
                    
                    # AUTOMATICALLY START GRAPHING ON CONNECT
                    self.start_measurements()
        else:
            self.worker.disconnect_port()
            self.connect_btn.setText("Connect")
            self.connect_btn.setStyleSheet("")
            self.port_combo.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            
            # Shut down UI graphing elements on disconnect
            self.is_measuring = False
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)

    # --- MEASUREMENT STATE MACHINE ---
    def start_measurements(self):
        self.is_measuring = True
        if not self.time_data:
            self.start_time = time.time()
            
        self.btn_start.setEnabled(False)
        self.btn_pause.setEnabled(True)
        self.btn_stop.setEnabled(True)

    def pause_measurements(self):
        self.is_measuring = False
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(True)

    def stop_measurements(self):
        self.is_measuring = False
        self.btn_start.setEnabled(True)
        self.btn_pause.setEnabled(False)
        self.btn_stop.setEnabled(False)
        
        # Clear data and wipe the screen
        self.time_data.clear()
        self.lux_data.clear()
        self.target_data.clear()
        self.led_data.clear()
        self.foil_data.clear()
        self.real_time_data.clear()
        self.curve_lux.setData([], [])
        self.curve_target.setData([], [])
        self.curve_led.setData([], [])
        self.lbl_lux.setText("Lux: --")
        self.lbl_target.setText("Target: --")
        self.lbl_effort.setText("Effort: --")
        self.lbl_foil.setText("Foil V: --")
        self.lbl_led.setText("LED %: --")

    # --- CONTROL OVERRIDES ---
    def _on_control_mode_clicked(self, button):
        mode = "auto" if button is self.radio_auto else "manual"
        self.apply_control_mode(mode)

    def apply_control_mode(self, mode, *, notify_device=True):
        self.control_mode = mode
        automatic = mode == "auto"
        manual = not automatic

        # Enable/Disable sections based on mode
        self.target_spinbox.setEnabled(automatic)
        self.target_slider.setEnabled(automatic)
        self.led_manual_slider.setEnabled(manual)
        self.btn_foil.setEnabled(manual)

        if notify_device:
            command = "MODE:AUTO\n" if automatic else "MODE:MANUAL\n"
            self.worker.send_line(command)

    def send_target_command(self):
        if self.control_mode == "auto":
            val = self.target_spinbox.value()
            self.worker.send_command(val)

    def send_led_override(self):
        if self.control_mode == "manual":
            value = self.led_manual_slider.value()
            self.worker.send_line(f"LED:{value}\n")

    def send_foil_override(self, checked):
        if self.control_mode == "manual":
            self.btn_foil.setText(f"PDLC Foil: {'On' if checked else 'Off'}")
            self.worker.send_line(f"FOIL:{100 if checked else 0}\n")

    def sync_settings(self):
        mode_cmd = "MODE:AUTO\r\n" if self.control_mode == "auto" else "MODE:MANUAL\r\n"
        target_cmd = f"T:{self.target_spinbox.value()}\r\n"
        led_cmd = f"LED:{self.led_manual_slider.value()}\r\n"
        foil_cmd = f"FOIL:{100 if self.btn_foil.isChecked() else 0}\r\n"

        for cmd in (mode_cmd, target_cmd, led_cmd, foil_cmd):
            self.worker.send_line(cmd)
            time.sleep(0.05)

    # --- LOGGING ---
    def toggle_logging(self, checked):
        if checked:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_dir = os.path.dirname(os.path.abspath(__file__))
            default_path = os.path.join(default_dir, f"stm32_log_{timestamp}.csv")
            filename, _ = QFileDialog.getSaveFileName(
                self,
                "Save Live Recording CSV",
                default_path,
                "CSV Files (*.csv);;All Files (*)"
            )
            if not filename:
                self.log_btn.setChecked(False)
                return
            try:
                self.csv_file = open(filename, 'w', newline='')
                self.csv_writer = csv.writer(self.csv_file)
                self.csv_writer.writerow(['Real_Time', 'Time_Elapsed(s)', 'Lux', 'Target', 'Effort', 'Foil_V', 'LED_Pct'])
                self.is_logging = True
                self.log_btn.setText("Stop Recording")
                self.lbl_log_status.setText(f"Recording to: {filename}")
                self.log_btn.setStyleSheet("background-color: #ffcccc;")
            except Exception as e:
                self.show_error(f"Failed to open log file: {e}")
                self.log_btn.setChecked(False)
        else:
            self.is_logging = False
            if self.csv_file:
                self.csv_file.close()
                self.csv_file = None
                self.csv_writer = None
            self.log_btn.setText("Start Recording CSV")
            self.lbl_log_status.setText("Status: Not Recording")
            self.log_btn.setStyleSheet("")

    def export_current_data(self):
        if not self.time_data:
            QMessageBox.information(self, "No Data", "There is no graph data to export.")
            return

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_dir = os.path.dirname(os.path.abspath(__file__))
        default_path = os.path.join(default_dir, f"stm32_graph_export_{timestamp}.csv")
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export Graph Data",
            default_path,
            "CSV Files (*.csv);;All Files (*)"
        )
        if not filename:
            return

        try:
            with open(filename, 'w', newline='') as export_file:
                writer = csv.writer(export_file)
                writer.writerow(['Real_Time', 'Time_Elapsed(s)', 'Lux', 'Target', 'LED_Pct', 'Foil_V'])
                for i in range(len(self.time_data)):
                    writer.writerow([
                        self.real_time_data[i],
                        round(self.time_data[i], 3),
                        self.lux_data[i],
                        self.target_data[i],
                        self.led_data[i],
                        self.foil_data[i]
                    ])
            QMessageBox.information(self, "Export Complete", f"Graph data exported to:\n{filename}")
        except Exception as e:
            self.show_error(f"Failed to export graph data: {e}")

    # --- INCOMING DATA HANDLER ---
    def update_data(self, data):
        # THE FIX: If paused/stopped, ignore the incoming data
        if not self.is_measuring:
            return

        # 1. Update Labels
        self.lbl_lux.setText(f"Lux: {data.get('lux', 0)}")
        self.lbl_target.setText(f"Target: {data.get('target', 0)}")
        self.lbl_effort.setText(f"Effort: {data.get('effort', 0)}")
        self.lbl_foil.setText(f"Foil V: {data.get('foil_v', 0.0)} V")
        self.lbl_led.setText(f"LED %: {data.get('led_pct', 0)}")

        # 2. Update Plot Buffers
        current_time = time.time() - self.start_time
        real_time_str = datetime.now().strftime("%H:%M:%S")
        self.real_time_data.append(real_time_str)
        self.time_data.append(current_time)
        self.lux_data.append(data.get('lux', 0))
        self.target_data.append(data.get('target', 0))
        self.led_data.append(data.get('led_pct', 0))
        self.foil_data.append(data.get('foil_v', 0.0))

        # 3. Update Plot Lines
        self.curve_lux.setData(list(self.time_data), list(self.lux_data))
        self.curve_target.setData(list(self.time_data), list(self.target_data))
        self.curve_led.setData(list(self.time_data), list(self.led_data))

        # 4. Log to CSV if active
        if self.is_logging and self.csv_writer:
            self.csv_writer.writerow([
                real_time_str,
                round(current_time, 3),
                data.get('lux', 0),
                data.get('target', 0),
                data.get('effort', 0),
                data.get('foil_v', 0.0),
                data.get('led_pct', 0)
            ])

    def show_error(self, message):
        QMessageBox.warning(self, "Error", message)

    def log_debug(self, msg):
        self.debug_console.append(msg)
        scrollbar = self.debug_console.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def closeEvent(self, event):
        self.worker.disconnect_port()
        if self.csv_file:
            self.csv_file.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion") 
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())