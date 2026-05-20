import sys
import json
import time
import csv
import qdarkstyle
from datetime import datetime
from collections import deque

import serial
import serial.tools.list_ports
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QComboBox, QPushButton, QLabel,
                             QSlider, QSpinBox, QGroupBox, QMessageBox, QGridLayout,
                             QRadioButton, QButtonGroup, QFileDialog)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
import pyqtgraph as pg
import qdarktheme

# Supplemental QSS layered on top of pyqtdarktheme (group panels + metric typography).
_APP_ADDITIONAL_QSS = """
QGroupBox {
    border: 1px solid #3d5166;
    border-radius: 12px;
    margin-top: 14px;
    padding: 18px 14px 14px 14px;
    font-size: 11pt;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 10px;
}
QLabel#metricReadout {
    font-family: "Segoe UI", "SF Pro Display", sans-serif;
    font-size: 20pt;
    font-weight: 600;
    padding: 10px 14px;
    background-color: #1a2330;
    border: 1px solid #2f4054;
    border-radius: 10px;
    color: #e8eef5;
}
QPushButton#sendTargetBtn {
    background-color: #2a7d4f;
    color: #ffffff;
    font-weight: 600;
    padding: 8px 16px;
    min-width: 110px;
}
QPushButton#sendTargetBtn:hover {
    background-color: #33965f;
}
QPushButton#connectBtnConnected {
    background-color: #1f6b45;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#logBtnRecording {
    background-color: #7a2e2e;
    color: #ffffff;
    font-weight: 600;
}
QPushButton#exportGraphBtn {
    background-color: #2563eb;
    color: #ffffff;
    font-weight: 600;
    padding: 10px 16px;
}
QPushButton#exportGraphBtn:hover {
    background-color: #3b82f6;
}
QPushButton#exportCsvBtn {
    background-color: #ea580c;
    color: #ffffff;
    font-weight: 600;
    padding: 10px 16px;
}
QPushButton#exportCsvBtn:hover {
    background-color: #f97316;
}
QPushButton#measureStartBtn {
    background-color: #2a7d4f;
    color: #ffffff;
    font-weight: 600;
    padding: 8px 20px;
    min-width: 72px;
}
QPushButton#measureStartBtn:hover {
    background-color: #33965f;
}
QPushButton#measurePauseBtn {
    background-color: #ea580c;
    color: #ffffff;
    font-weight: 600;
    padding: 8px 20px;
    min-width: 72px;
}
QPushButton#measurePauseBtn:hover {
    background-color: #f97316;
}
QPushButton#measureStopBtn {
    background-color: #dc2626;
    color: #ffffff;
    font-weight: 600;
    padding: 8px 20px;
    min-width: 72px;
}
QPushButton#measureStopBtn:hover {
    background-color: #ef4444;
}
"""

# ==========================================
# 1. Background Serial Thread
# ==========================================
class SerialWorker(QThread):
    data_received = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

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
                self.serial_port.write(command.encode('utf-8'))
                print(f"Sent to STM32: {command.strip()}")
            except Exception as e:
                self.error_occurred.emit(f"Write error: {e}")

    def send_command(self, target_lux):
        self.send_line(f"T:{target_lux}\n")

    def run(self):
        while self.is_running and self.serial_port.is_open:
            try:
                if self.serial_port.in_waiting > 0:
                    line = self.serial_port.readline().decode('utf-8').strip()
                    if line:
                        data = json.loads(line)
                        self.data_received.emit(data)
            except json.JSONDecodeError:
                pass 
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

        self.buffer_size = 300
        self.time_data = deque(maxlen=self.buffer_size)
        self.lux_data = deque(maxlen=self.buffer_size)
        self.target_data = deque(maxlen=self.buffer_size)
        self.led_data = deque(maxlen=self.buffer_size)
        self.start_time = time.time()

        self.is_logging = False
        self.csv_file = None
        self.csv_writer = None
        self.control_mode = "auto"
        self.is_measuring = False

        self.setup_ui()

        self.worker = SerialWorker()
        self.worker.data_received.connect(self.update_data)
        self.worker.error_occurred.connect(self.show_error)

        self.refresh_ports()

    def setup_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(14)

        # --- Top Bar: Connection ---
        conn_group = QGroupBox("Serial Connection")
        conn_layout = QHBoxLayout()
        conn_layout.setSpacing(12)
        self.port_combo = QComboBox()
        self.port_combo.setMinimumWidth(140)
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
        pg.setConfigOption('background', '#161b22')
        pg.setConfigOption('foreground', '#c9d1d9')
        self.plot_widget = pg.PlotWidget(title="Live Metrics (Lux vs Time)")
        self.plot_widget.setBackground('#161b22')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.25)
        self.plot_widget.setLabel('left', 'Value')
        self.plot_widget.setLabel('bottom', 'Time (s)')
        self.plot_widget.addLegend(offset=(10, 10))

        self.curve_lux = self.plot_widget.plot(
            pen=pg.mkPen('#58a6ff', width=2), name="Lux")
        self.curve_target = self.plot_widget.plot(
            pen=pg.mkPen('#3fb950', width=2, style=Qt.DashLine), name="Target")
        self.curve_led = self.plot_widget.plot(
            pen=pg.mkPen('#f78166', width=2), name="LED %")
        main_layout.addWidget(self.plot_widget, stretch=3)

        # --- Bottom section: Controls & Readouts ---
        bottom_layout = QHBoxLayout()
        bottom_layout.setSpacing(14)

        # 1. Live Data Readouts
        readout_group = QGroupBox("Live Metrics")
        readout_layout = QGridLayout()
        readout_layout.setHorizontalSpacing(12)
        readout_layout.setVerticalSpacing(12)
        self.lbl_lux = QLabel("Lux: --")
        self.lbl_target = QLabel("Target: --")
        self.lbl_effort = QLabel("Effort: --")
        self.lbl_foil = QLabel("Foil V: --")
        self.lbl_led = QLabel("LED %: --")

        for lbl in [self.lbl_lux, self.lbl_target, self.lbl_effort, self.lbl_foil, self.lbl_led]:
            lbl.setObjectName("metricReadout")
            lbl.setAlignment(Qt.AlignCenter)

        readout_layout.addWidget(self.lbl_lux, 0, 0)
        readout_layout.addWidget(self.lbl_target, 0, 1)
        readout_layout.addWidget(self.lbl_effort, 1, 0)
        readout_layout.addWidget(self.lbl_foil, 1, 1)
        readout_layout.addWidget(self.lbl_led, 2, 0, 1, 2)
        readout_group.setLayout(readout_layout)
        bottom_layout.addWidget(readout_group, stretch=1)

        # 2. Measurement controls
        measure_group = QGroupBox("Measurement Controls")
        measure_layout = QHBoxLayout()
        measure_layout.setSpacing(12)

        self.btn_start = QPushButton("Start")
        self.btn_start.setObjectName("measureStartBtn")
        self.btn_start.clicked.connect(self.start_measurements)

        self.btn_pause = QPushButton("Pause")
        self.btn_pause.setObjectName("measurePauseBtn")
        self.btn_pause.clicked.connect(self.pause_measurements)

        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("measureStopBtn")
        self.btn_stop.clicked.connect(self.stop_measurements)

        for btn in (self.btn_start, self.btn_pause, self.btn_stop):
            btn.setEnabled(False)

        measure_layout.addWidget(self.btn_start)
        measure_layout.addWidget(self.btn_pause)
        measure_layout.addWidget(self.btn_stop)
        measure_layout.addStretch()
        measure_group.setLayout(measure_layout)
        bottom_layout.addWidget(measure_group, stretch=1)

        # 3. Control mode
        mode_group = QGroupBox("Control Mode")
        mode_layout = QVBoxLayout()
        mode_layout.setSpacing(10)
        self.radio_auto = QRadioButton("Automatic")
        self.radio_manual = QRadioButton("Manual")
        self.radio_auto.setChecked(True)
        self.mode_button_group = QButtonGroup(self)
        self.mode_button_group.addButton(self.radio_auto)
        self.mode_button_group.addButton(self.radio_manual)
        self.mode_button_group.buttonClicked.connect(self._on_control_mode_clicked)
        mode_layout.addWidget(self.radio_auto)
        mode_layout.addWidget(self.radio_manual)
        mode_layout.addStretch()
        mode_group.setLayout(mode_layout)
        bottom_layout.addWidget(mode_group, stretch=1)

        # 4. Controls
        control_group = QGroupBox("User Controls")
        control_layout = QVBoxLayout()
        control_layout.setSpacing(12)

        target_layout = QHBoxLayout()
        target_layout.setSpacing(12)
        self.lbl_target_lux = QLabel("Set Target Lux:")
        target_layout.addWidget(self.lbl_target_lux)

        self.target_spinbox = QSpinBox()
        self.target_spinbox.setRange(0, 2000)
        self.target_spinbox.setValue(1000)
        self.target_spinbox.setMinimumWidth(100)

        self.btn_send_target = QPushButton("Send Target")
        self.btn_send_target.setObjectName("sendTargetBtn")
        self.btn_send_target.clicked.connect(self.send_target_command)

        target_layout.addWidget(self.target_spinbox)
        target_layout.addWidget(self.btn_send_target)
        target_layout.addStretch()

        control_layout.addLayout(target_layout)

        self.target_slider = QSlider(Qt.Horizontal)
        self.target_slider.setRange(0, 2000)
        self.target_slider.setValue(700)

        self.target_slider.valueChanged.connect(self.target_spinbox.setValue)
        self.target_spinbox.valueChanged.connect(self.target_slider.setValue)
        self.target_slider.sliderReleased.connect(self.send_target_command)

        control_layout.addWidget(self.target_slider)
        control_group.setLayout(control_layout)
        bottom_layout.addWidget(control_group, stretch=2)

        # 5. Manual overrides
        manual_group = QGroupBox("Manual Overrides")
        manual_layout = QVBoxLayout()
        manual_layout.setSpacing(12)

        led_row = QHBoxLayout()
        led_row.setSpacing(12)
        self.lbl_led_intensity = QLabel("LED Intensity:")
        self.led_manual_slider = QSlider(Qt.Horizontal)
        self.led_manual_slider.setRange(0, 100)
        self.led_manual_slider.setValue(0)
        self.lbl_led_value = QLabel("0%")
        self.lbl_led_value.setMinimumWidth(44)
        self.lbl_led_value.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.led_manual_slider.valueChanged.connect(
            lambda value: self.lbl_led_value.setText(f"{value}%"))
        self.led_manual_slider.sliderReleased.connect(self.send_led_override)

        led_row.addWidget(self.lbl_led_intensity)
        led_row.addWidget(self.led_manual_slider, stretch=1)
        led_row.addWidget(self.lbl_led_value)
        manual_layout.addLayout(led_row)

        self.btn_foil = QPushButton("PDLC Foil: Off")
        self.btn_foil.setCheckable(True)
        self.btn_foil.toggled.connect(self.send_foil_override)
        manual_layout.addWidget(self.btn_foil)

        manual_group.setLayout(manual_layout)
        bottom_layout.addWidget(manual_group, stretch=2)

        self.apply_control_mode("auto", notify_device=False)

        # 6. Logging
        logging_group = QGroupBox("Data Logging")
        logging_layout = QVBoxLayout()
        logging_layout.setSpacing(10)
        self.log_btn = QPushButton("Start Recording")
        self.log_btn.setCheckable(True)
        self.log_btn.toggled.connect(self.toggle_logging)
        self.lbl_log_status = QLabel("Status: Not Recording")
        self.lbl_log_status.setWordWrap(True)

        logging_layout.addWidget(self.log_btn)
        logging_layout.addWidget(self.lbl_log_status)
        logging_group.setLayout(logging_layout)
        bottom_layout.addWidget(logging_group, stretch=1)

        main_layout.addLayout(bottom_layout, stretch=1)

        # --- Export options ---
        export_group = QGroupBox("Export Options")
        export_layout = QVBoxLayout()
        export_layout.setSpacing(10)

        self.btn_export_graph = QPushButton("Export Graph (Vector SVG)")
        self.btn_export_graph.setObjectName("exportGraphBtn")
        self.btn_export_graph.clicked.connect(self.export_graph_vector)

        self.btn_export_csv = QPushButton("Export Current Data (CSV)")
        self.btn_export_csv.setObjectName("exportCsvBtn")
        self.btn_export_csv.clicked.connect(self.export_current_data)

        export_layout.addWidget(self.btn_export_graph)
        export_layout.addWidget(self.btn_export_csv)
        export_group.setLayout(export_layout)
        main_layout.addWidget(export_group)

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
                    self.connect_btn.setObjectName("connectBtnConnected")
                    self.connect_btn.style().unpolish(self.connect_btn)
                    self.connect_btn.style().polish(self.connect_btn)
                    self.port_combo.setEnabled(False)
                    self.refresh_btn.setEnabled(False)
                    self.start_time = time.time()
                    self.time_data.clear()
                    self.lux_data.clear()
                    self.target_data.clear()
                    self.led_data.clear()
                    self.apply_control_mode(self.control_mode)
                    self.btn_start.setEnabled(True)
                    self.btn_pause.setEnabled(True)
                    self.btn_stop.setEnabled(True)
        else:
            self.worker.disconnect_port()
            self.connect_btn.setText("Connect")
            self.connect_btn.setObjectName("")
            self.connect_btn.style().unpolish(self.connect_btn)
            self.connect_btn.style().polish(self.connect_btn)
            self.port_combo.setEnabled(True)
            self.refresh_btn.setEnabled(True)
            self.btn_start.setEnabled(False)
            self.btn_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.is_measuring = False

    def _on_control_mode_clicked(self, button):
        mode = "auto" if button is self.radio_auto else "manual"
        self.apply_control_mode(mode)

    def apply_control_mode(self, mode, *, notify_device=True):
        """Update UI enablement and optionally notify the device of the new mode."""
        self.control_mode = mode
        automatic = mode == "auto"

        manual = not automatic

        self.lbl_target_lux.setEnabled(automatic)
        self.target_spinbox.setEnabled(automatic)
        self.btn_send_target.setEnabled(automatic)
        self.target_slider.setEnabled(automatic)

        self.lbl_led_intensity.setEnabled(manual)
        self.led_manual_slider.setEnabled(manual)
        self.lbl_led_value.setEnabled(manual)
        self.btn_foil.setEnabled(manual)

        if notify_device:
            command = "MODE:AUTO\n" if automatic else "MODE:MANUAL\n"
            self.worker.send_line(command)

    def send_target_command(self):
        if self.control_mode != "auto":
            return
        val = self.target_spinbox.value()
        self.worker.send_command(val)

    def send_led_override(self):
        if self.control_mode != "manual":
            return
        value = self.led_manual_slider.value()
        self.worker.send_line(f"LED:{value}\n")

    def send_foil_override(self, checked):
        if self.control_mode != "manual":
            return
        self.btn_foil.setText(f"PDLC Foil: {'On' if checked else 'Off'}")
        self.worker.send_line(f"FOIL:{1 if checked else 0}\n")

    def start_measurements(self):
        self.is_measuring = True
        if not self.time_data:
            self.start_time = time.time()

    def pause_measurements(self):
        self.is_measuring = False

    def stop_measurements(self):
        self.is_measuring = False
        self.time_data.clear()
        self.lux_data.clear()
        self.target_data.clear()
        self.led_data.clear()
        self.curve_lux.setData([], [])
        self.curve_target.setData([], [])
        self.curve_led.setData([], [])
        self.lbl_lux.setText("Lux: --")
        self.lbl_target.setText("Target: --")
        self.lbl_effort.setText("Effort: --")
        self.lbl_foil.setText("Foil V: --")
        self.lbl_led.setText("LED %: --")

    def export_graph_vector(self):
        default_name = f"stm32_plot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.svg"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Graph as SVG",
            default_name,
            "SVG Vector Graphics (*.svg)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".svg"):
            file_path += ".svg"

        try:
            exporter = pg.exporters.SVGExporter(self.plot_widget.plotItem)
            exporter.export(file_path)
            QMessageBox.information(
                self,
                "Export Successful",
                f"Graph saved as vector SVG:\n{file_path}",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Could not export graph:\n{e}",
            )

    def export_current_data(self):
        default_name = f"stm32_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Current Data as CSV",
            default_name,
            "CSV Files (*.csv)",
        )
        if not file_path:
            return
        if not file_path.lower().endswith(".csv"):
            file_path += ".csv"

        try:
            with open(file_path, "w", newline="") as csv_file:
                writer = csv.writer(csv_file)
                writer.writerow(["Time_Elapsed(s)", "Lux", "Target", "LED_Pct"])
                row_count = len(self.time_data)
                for i in range(row_count):
                    writer.writerow([
                        self.time_data[i],
                        self.lux_data[i],
                        self.target_data[i],
                        self.led_data[i],
                    ])
            QMessageBox.information(
                self,
                "Export Successful",
                f"Exported {row_count} rows to:\n{file_path}",
            )
        except Exception as e:
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Could not export data:\n{e}",
            )

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
                self.log_btn.setObjectName("logBtnRecording")
                self.log_btn.style().unpolish(self.log_btn)
                self.log_btn.style().polish(self.log_btn)
            except Exception as e:
                self.show_error(f"Failed to open log file: {e}")
                self.log_btn.setChecked(False)
        else:
            self.is_logging = False
            if self.csv_file:
                self.csv_file.close()
            self.log_btn.setText("Start Recording")
            self.lbl_log_status.setText("Status: Not Recording")
            self.log_btn.setObjectName("")
            self.log_btn.style().unpolish(self.log_btn)
            self.log_btn.style().polish(self.log_btn)

    def update_data(self, data):
        if not self.is_measuring:
            return

        self.lbl_lux.setText(f"Lux: {data.get('lux', 0)}")
        self.lbl_target.setText(f"Target: {data.get('target', 0)}")
        self.lbl_effort.setText(f"Effort: {data.get('effort', 0)}")
        self.lbl_foil.setText(f"Foil V: {data.get('foil_v', 0.0)} V")
        self.lbl_led.setText(f"LED %: {data.get('led_pct', 0)}")

        current_time = time.time() - self.start_time
        self.time_data.append(current_time)
        self.lux_data.append(data.get('lux', 0))
        self.target_data.append(data.get('target', 0))
        self.led_data.append(data.get('led_pct', 0))

        self.curve_lux.setData(list(self.time_data), list(self.lux_data))
        self.curve_target.setData(list(self.time_data), list(self.target_data))
        self.curve_led.setData(list(self.time_data), list(self.led_data))

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
        self.worker.disconnect_port()
        if self.csv_file:
            self.csv_file.close()
        event.accept()

if __name__ == '__main__':
    # Enable High DPI scaling natively (optional but recommended)
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    
    app = QApplication(sys.argv)
    
    # Apply QDarkStyle
    app.setStyleSheet(qdarkstyle.load_stylesheet_pyqt5())
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())