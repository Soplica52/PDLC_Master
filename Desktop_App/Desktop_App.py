import sys
import json
import time
import csv
from datetime import datetime
from collections import deque

import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QComboBox, QPushButton, QLabel, 
                             QSlider, QSpinBox, QGroupBox, QMessageBox, QGridLayout)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import pyqtgraph as pg

# ==========================================
# 1. Background Serial Thread
# ==========================================
class SerialWorker(QThread):
    """
    Handles serial communication in a background thread to prevent the GUI from freezing.
    """
    data_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.serial_port = serial.Serial()
        self.serial_port.baudrate = 115200
        self.serial_port.timeout = 1 # 1 second timeout
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
        self.wait() # Wait for thread to finish
        if self.serial_port.is_open:
            self.serial_port.close()

    def send_command(self, target_lux):
        if self.serial_port.is_open:
            command = f"T:{target_lux}\n"
            try:
                self.serial_port.write(command.encode('utf-8'))
            except Exception as e:
                self.error_occurred.emit(f"Write error: {e}")

    def run(self):
        while self.is_running and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    line = self.serial_port.readline().decode('utf-8').strip()
                    if line:
                        data = json.loads(line)
                        self.data_received.emit(data)
            except json.JSONDecodeError:
                pass # Ignore malformed JSON chunks
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
        self.resize(1000, 700)

        # Buffer arrays for plotting (max 300 points ~ 60 seconds at 5Hz)
        self.buffer_size = 300
        self.time_data = deque(maxlen=self.buffer_size)
        self.lux_data = deque(maxlen=self.buffer_size)
        self.target_data = deque(maxlen=self.buffer_size)
        self.led_data = deque(maxlen=self.buffer_size)
        self.start_time = time.time()

        # CSV Logging variables
        self.is_logging = False
        self.csv_file = None
        self.csv_writer = None

        self.setup_ui()

        # Initialize Serial Worker
        self.worker = SerialWorker()
        self.worker.data_received.connect(self.update_data)
        self.worker.error_occurred.connect(self.show_error)

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
        
        # Plot curves
        self.curve_lux = self.plot_widget.plot(pen=pg.mkPen('b', width=2), name="Lux")
        self.curve_target = self.plot_widget.plot(pen=pg.mkPen('g', width=2, style=Qt.DashLine), name="Target")
        self.curve_led = self.plot_widget.plot(pen=pg.mkPen('r', width=2), name="LED %")
        main_layout.addWidget(self.plot_widget, stretch=3)

        # --- Bottom section: Controls & Readouts ---
        bottom_layout = QHBoxLayout()

        # 1. Live Data Readouts
        readout_group = QGroupBox("Live Metrics")
        readout_layout = QGridLayout()
        self.lbl_lux = QLabel("Lux: --")
        self.lbl_target = QLabel("Target: --")
        self.lbl_effort = QLabel("Effort: --")
        self.lbl_foil = QLabel("Foil V: --")
        self.lbl_led = QLabel("LED %: --")
        
        # Style labels for readability
        for lbl in [self.lbl_lux, self.lbl_target, self.lbl_effort, self.lbl_foil, self.lbl_led]:
            lbl.setStyleSheet("font-size: 14px; font-weight: bold;")

        readout_layout.addWidget(self.lbl_lux, 0, 0)
        readout_layout.addWidget(self.lbl_target, 0, 1)
        readout_layout.addWidget(self.lbl_effort, 1, 0)
        readout_layout.addWidget(self.lbl_foil, 1, 1)
        readout_layout.addWidget(self.lbl_led, 2, 0, 1, 2)
        readout_group.setLayout(readout_layout)
        bottom_layout.addWidget(readout_group, stretch=1)

        # 2. Controls
        control_group = QGroupBox("User Controls")
        control_layout = QVBoxLayout()
        
        target_layout = QHBoxLayout()
        target_layout.addWidget(QLabel("Set Target Lux:"))
        self.target_spinbox = QSpinBox()
        self.target_spinbox.setRange(0, 2000)
        self.target_spinbox.setValue(700)
        
        self.target_slider = QSlider(Qt.Horizontal)
        self.target_slider.setRange(0, 2000)
        self.target_slider.setValue(700)

        # Sync slider and spinbox
        self.target_slider.valueChanged.connect(self.target_spinbox.setValue)
        self.target_spinbox.valueChanged.connect(self.target_slider.setValue)

        # Only send command when slider is released or spinbox editing is finished
        # to prevent flooding the serial port
        self.target_slider.sliderReleased.connect(self.send_target_command)
        self.target_spinbox.editingFinished.connect(self.send_target_command)

        target_layout.addWidget(self.target_spinbox)
        control_layout.addLayout(target_layout)
        control_layout.addWidget(self.target_slider)
        control_group.setLayout(control_layout)
        bottom_layout.addWidget(control_group, stretch=2)

        # 3. Logging
        logging_group = QGroupBox("Data Logging")
        logging_layout = QVBoxLayout()
        self.log_btn = QPushButton("Start Recording")
        self.log_btn.setCheckable(True)
        self.log_btn.toggled.connect(self.toggle_logging)
        self.lbl_log_status = QLabel("Status: Not Recording")
        
        logging_layout.addWidget(self.log_btn)
        logging_layout.addWidget(self.lbl_log_status)
        logging_group.setLayout(logging_layout)
        bottom_layout.addWidget(logging_group, stretch=1)

        main_layout.addLayout(bottom_layout, stretch=1)

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
                    self.connect_btn.setStyleSheet("background-color: lightgreen;")
                    self.port_combo.setEnabled(False)
                    self.refresh_btn.setEnabled(False)
                    self.start_time = time.time() # Reset plot time
                    self.time_data.clear()
                    self.lux_data.clear()
                    self.target_data.clear()
                    self.led_data.clear()
        else:
            self.worker.disconnect_port()
            self.connect_btn.setText("Connect")
            self.connect_btn.setStyleSheet("")
            self.port_combo.setEnabled(True)
            self.refresh_btn.setEnabled(True)

    def send_target_command(self):
        val = self.target_spinbox.value()
        self.worker.send_command(val)

    def toggle_logging(self, checked):
        if checked:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"stm32_log_{timestamp}.csv"
            try:
                self.csv_file = open(filename, 'w', newline='')
                self.csv_writer = csv.writer(self.csv_file)
                self.csv_writer.writerow(['Timestamp', 'Lux', 'Target', 'Effort', 'Foil_V', 'LED_Pct'])
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
            self.log_btn.setText("Start Recording")
            self.lbl_log_status.setText("Status: Not Recording")
            self.log_btn.setStyleSheet("")

    def update_data(self, data):
        # 1. Update Labels
        self.lbl_lux.setText(f"Lux: {data.get('lux', 0)}")
        self.lbl_target.setText(f"Target: {data.get('target', 0)}")
        self.lbl_effort.setText(f"Effort: {data.get('effort', 0)}")
        self.lbl_foil.setText(f"Foil V: {data.get('foil_v', 0.0)} V")
        self.lbl_led.setText(f"LED %: {data.get('led_pct', 0)}")

        # 2. Update Plot Buffers
        current_time = time.time() - self.start_time
        self.time_data.append(current_time)
        self.lux_data.append(data.get('lux', 0))
        self.target_data.append(data.get('target', 0))
        self.led_data.append(data.get('led_pct', 0))

        # 3. Update Plot Lines
        self.curve_lux.setData(list(self.time_data), list(self.lux_data))
        self.curve_target.setData(list(self.time_data), list(self.target_data))
        self.curve_led.setData(list(self.time_data), list(self.led_data))

        # 4. Log to CSV if active
        if self.is_logging and self.csv_writer:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.csv_writer.writerow([
                ts, 
                data.get('lux', 0), 
                data.get('target', 0), 
                data.get('effort', 0), 
                data.get('foil_v', 0.0), 
                data.get('led_pct', 0)
            ])

    def show_error(self, message):
        QMessageBox.warning(self, "Error", message)

    def closeEvent(self, event):
        # Clean up resources safely upon exit
        self.worker.disconnect_port()
        if self.csv_file:
            self.csv_file.close()
        event.accept()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setStyle("Fusion") # Cleaner cross-platform look
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())