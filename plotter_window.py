import re
import sys
from threading import Thread

import matplotlib as mpl
import numpy as np
import serial
from PyQt5 import QtGui
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QFileDialog, QTextEdit, \
    QComboBox, QMainWindow, QGridLayout, QLabel
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

from pathlib import Path
import pandas as pd

mpl.use('Qt5Agg')


class Canvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=5, height=8, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(Canvas, self).__init__(fig)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()

        self.layout = QGridLayout(self)
        self.main_widget = QWidget(self)
        self.textbox = QTextEdit(self)
        self.cursor = self.textbox.textCursor()
        self.comboBoxCOM = QComboBox(self)
        self.comboBoxBaud = QComboBox(self)
        self.comboBoxBit = QComboBox(self)
        self.comboBoxStopBits = QComboBox(self)
        self.comboBoxParity = QComboBox(self)
        self.comboBoxSensor = QComboBox(self)
        self.main_plot = Canvas(self, width=5, height=7, dpi=100)
        self.toolbar = NavigationToolbar2QT(self.main_plot, self)

        self.timebase = 50  # ms
        self.n_data = 100
        self.x_data_plot = list(range(self.n_data))
        self.plot_yrange = {"acc": [-2200, 2200], "gyr": [-1500000, 1500000], "enc": [-50, 50]}
        self.x_data = np.array([])
        self.y_data = [[np.array([]) for _ in range(3)] for _ in range(3)]  # accel, gyro, enc
        self._plot_refs = [None, None, None]
        self._stop_flag = False
        self._reading_thread = None
        self.plot_colours = ("r", "g", "b")

        self._title = "DATA PLOTTER"
        self._positions = (200, 100, 1200, 900)  # right, down, width, height
        self.com_port = "COM3"
        self.baud_rate = "115200"
        self.data_bits = "8"
        self.parity = "NONE"
        self.stop_bits = "1"
        self.sensor = "ACCELEROMETER"

        self.init_main_widget()
        self.setCentralWidget(self.main_widget)
        self.init_basic_elements()

    def init_main_widget(self):
        self.textbox.setReadOnly(True)
        for widget in (self.main_plot, self.toolbar, self.textbox):
            self.layout.addWidget(widget)
        self.main_widget.setLayout(self.layout)

    def init_basic_elements(self):
        self.setWindowTitle(self._title)
        self.setGeometry(*self._positions)
        self.setFixedSize(*self._positions[2:])

        buttons = {"OPEN": {"pos": (10, 10, 100, 22), "func": self.start_reading},
                   "CLOSE": {"pos": (110, 10, 100, 22), "func": self.stop_reading},
                   "SAVE": {"pos": (250, 10, 100, 22), "func": self.save_data},
                   "CLEAR": {"pos": (350, 10, 100, 22), "func": self.clear_window}}

        for btn_name, btn_params in buttons.items():
            btn = QPushButton(btn_name, self)
            btn.setGeometry(*btn_params["pos"])
            btn.clicked.connect(btn_params["func"])

        bits = [str(i) for i in range(8, 4, -1)]
        stop_bits = [str(i) for i in range(1, 3)]
        ports = [f"COM{i}" for i in range(1, 11)]
        sensors = ["ACCELEROMETER", "GYROSCOPE", "ENCODERS"]
        parity = ('NONE', 'ODD', 'EVEN', 'MARK', 'SPACE')
        baud_rates = ("115200", "57600", "38400", "19200", "9600", "1200", "300", "921600", "460800",
                      "230400", "4800", "2400", "150", "110")

        combo_boxes = {self.comboBoxCOM: {"items": ports, "func": self.combo_com_change, "pos": (500, 10),
                                          "def": ports.index(self.com_port), "label": "Port"},
                       self.comboBoxBaud: {"items": baud_rates, "func": self.combo_bit_change, "pos": (610, 10),
                                           "def": baud_rates.index(self.baud_rate), "label": "Baud"},
                       self.comboBoxBit: {"items": bits, "func": self.combo_bit_change, "pos": (720, 10),
                                          "def": bits.index(self.data_bits), "label": "Data bits"},
                       self.comboBoxParity: {"items": parity, "func": self.combo_parity_change, "pos": (830, 10),
                                             "def": parity.index(self.parity), "label": "Parity"},
                       self.comboBoxStopBits: {"items": stop_bits, "func": self.combo_stopbits_change, "pos": (940, 10),
                                               "def": stop_bits.index(self.stop_bits), "label": "Stop bits"},
                       self.comboBoxSensor: {"items": sensors, "func": self.combo_sensor_change, "pos": (1050, 10),
                                             "def": sensors.index(self.sensor), "label": "Sensors"}}

        for combo_box, combo_params in combo_boxes.items():
            for item in combo_params["items"]:
                combo_box.addItem(item)
            combo_box.move(*combo_params["pos"])
            combo_box.setCurrentIndex(combo_params["def"])
            combo_box.currentIndexChanged.connect(combo_params["func"])

            combo_label = QLabel(self)
            combo_label.setText(combo_params["label"])
            combo_label.move(combo_params["pos"][0], 35)

        self.show()

    def combo_com_change(self):
        self.com_port = self.comboBoxCOM.currentText()

    def combo_bit_change(self):
        self.data_bits = self.comboBoxBit.currentText()

    def combo_parity_change(self):
        self.parity = self.comboBoxParity.currentText()

    def combo_baud_change(self):
        self.baud_rate = self.comboBoxBaud.currentText()

    def combo_stopbits_change(self):
        self.stop_bits = self.comboBoxStopBits.currentText()

    def combo_sensor_change(self):
        self.sensor = self.comboBoxSensor.currentText()
        self.main_plot.axes.set_ylim(self.plot_yrange[self.sensor.lower()[:3]])

    def set_cursor(self):
        self.cursor.movePosition(QtGui.QTextCursor.End)
        self.textbox.setTextCursor(self.cursor)

    def start_reading(self):
        self.main_plot.axes.set_ylim(self.plot_yrange[self.sensor.lower()[:3]])
        if self._reading_thread is None:
            self._stop_flag = False
            self.read_port()
        else:
            self.textbox.append(f"Port already opened.\r")
            self.set_cursor()

    def stop_reading(self):
        if self._reading_thread is not None:
            self._stop_flag = True
            self._reading_thread.join()
            self._reading_thread = None
        self.textbox.append(f"Port {self.com_port} closed.\n")
        self.set_cursor()

    def clear_window(self):
        self.textbox.setText("")
        self._plot_refs = [None, None, None]
        self.main_plot.axes.cla()
        self.main_plot.draw()
        self.main_plot.axes.set_ylim(self.plot_yrange[self.sensor.lower()[:3]])

    def save_data(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getSaveFileName(self, "Save file", "c:\\", "CSV Files (*.csv)", options=options)

        if file_name:
            df = pd.DataFrame({"time": self.x_data,
                               "accelX": self.y_data[0][0],
                               "accelY": self.y_data[0][1],
                               "accelZ": self.y_data[0][2],
                               "gyroX": self.y_data[1][0],
                               "gyroY": self.y_data[1][1],
                               "gyroZ": self.y_data[1][2],
                               "enc1": self.y_data[2][0],
                               "enc2": self.y_data[2][1],
                               "enc3": self.y_data[2][2]})

            df.to_csv(Path(file_name), index=False)

    def plot_data(self):
        y_data = {"ACCELEROMETER": self.y_data[0], "GYROSCOPE": self.y_data[1], "ENCODERS": self.y_data[2]}

        if y_data[self.sensor][0].size >= self.n_data:
            y_data_plot = [data[-self.n_data:] for data in y_data[self.sensor]]
            for i, colour in enumerate(self.plot_colours):
                if self._plot_refs[i] is None:
                    self._plot_refs[i] = self.main_plot.axes.plot(self.x_data_plot, y_data_plot[i], colour)[0]
                else:
                    self._plot_refs[i].set_ydata(y_data_plot[i])

            self.main_plot.draw()

    def reading_loop(self, serial):
        while not self._stop_flag:
            data = serial.readline()
            data = str(data.decode('utf-8'))
            self.textbox.append(data)
            self.cursor.movePosition(QtGui.QTextCursor.End)
            self.textbox.setTextCursor(self.cursor)

            data_list = data.split("; ")

            for sens, sensor_data in enumerate(data_list):
                span = re.search(r'\[[^\]]*\]', sensor_data).span()
                data_axes = sensor_data[span[0] + 1:span[1] - 1].split(",")
                for ax in range(len(data_axes)):
                    self.y_data[sens][ax] = np.append(self.y_data[sens][ax], int(data_axes[ax]))

            self.x_data = np.append(self.x_data, (len(self.x_data) * self.timebase) + self.timebase)

            if self.x_data.size > 0:
                self.plot_data()

    def read_port(self):
        try:
            ser = serial.Serial(port=self.com_port,
                                baudrate=int(self.baud_rate),
                                bytesize=int(self.data_bits),
                                parity=self.parity[0],
                                stopbits=int(self.stop_bits))
            self.textbox.append(f"Port {self.com_port} opened.\r")
            self.set_cursor()
            self._reading_thread = Thread(target=self.reading_loop, args=(ser,), daemon=True)
            self._reading_thread.start()

        except serial.serialutil.SerialException:
            self.textbox.append(f"No device found on {self.com_port}.\n")
            self.set_cursor()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    app.exec_()
