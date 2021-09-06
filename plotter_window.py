import random
import re
import sys
from threading import Thread

import matplotlib as mpl
import numpy as np
import serial
from PyQt5 import QtGui
from PyQt5.QtWidgets import QApplication, QWidget, QPushButton, QFileDialog, QTextEdit, \
    QComboBox, QMainWindow, QGridLayout
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure

mpl.use('Qt5Agg')


class Canvas(FigureCanvasQTAgg):
    def __init__(self, parent=None, width=5, height=4, dpi=100):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super(Canvas, self).__init__(fig)


class Window(QMainWindow):
    def __init__(self):
        super().__init__()

        self.layout = QGridLayout(self)
        self.main_widget = QWidget(self)
        self.textbox = QTextEdit(self)
        self.comboBoxCOM = QComboBox(self)
        self.comboBoxBaud = QComboBox(self)
        self.comboBoxBit = QComboBox(self)
        self.comboBoxStopBits = QComboBox(self)
        self.comboBoxParity = QComboBox(self)
        self.main_plot = Canvas(self, width=5, height=4, dpi=100)
        self.toolbar = NavigationToolbar2QT(self.main_plot, self)

        self.timebase = 100  # ms
        self.n_data = 50
        self.stop_flag = False
        self.x_data = np.array([])
        self.y_data = np.array([])
        self._plot_ref = None

        self._title = "DATA PLOTTER"
        self._positions = (200, 100, 1100, 600)  # right, down, width, height
        self.com_port = "COM3"
        self.baud_rate = "115200"
        self.data_bits = "8"
        self.parity = "NONE"
        self.stop_bits = "1"

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
        parity = ('NONE', 'ODD', 'EVEN', 'MARK', 'SPACE')
        baud_rates = ("115200", "57600", "38400", "19200", "9600", "1200", "300", "921600", "460800",
                      "230400", "4800", "2400", "150", "110")

        combo_boxes = {self.comboBoxCOM: {"items": ports, "func": self.combo_com_change, "pos": (500, 10)},
                       self.comboBoxBaud: {"items": baud_rates, "func": self.combo_com_change, "pos": (610, 10)},
                       self.comboBoxBit: {"items": bits, "func": self.combo_com_change, "pos": (720, 10)},
                       self.comboBoxParity: {"items": parity, "func": self.combo_com_change, "pos": (830, 10)},
                       self.comboBoxStopBits: {"items": stop_bits, "func": self.combo_com_change, "pos": (940, 10)}}

        for combo_box, combo_params in combo_boxes.items():
            for item in combo_params["items"]:
                combo_box.addItem(item)
            combo_box.move(*combo_params["pos"])
            combo_box.currentIndexChanged.connect(combo_params["func"])

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

    def start_reading(self):
        self.read_port()

    def stop_reading(self):
        self.stop_flag = True
        self.textbox.append(f"Port {self.com_port} closed.\n")

    def clear_window(self):
        self.textbox.setText("")
        self.main_plot.axes.cla()
        self.main_plot.draw()

    def save_data(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getSaveFileName(self, "Save file", "c:\\",
                                                   "All Files (*);;Text Files (*.txt)", options=options)
        if file_name:
            print(file_name)

    def plot_data(self):
        if self.x_data.size >= 50:
            y_data_plot = self.y_data[-50:]
            x_data_plot = self.x_data[-50:]
        else:
            y_data_plot = self.y_data
            x_data_plot = self.x_data

        print(f"X: {x_data_plot}\nY: {y_data_plot}")

        if self._plot_ref is None:
            self._plot_ref = self.main_plot.axes.plot(x_data_plot, y_data_plot, 'r')[0]
        else:
            self._plot_ref.set_xdata(x_data_plot)
            self._plot_ref.set_ydata(y_data_plot)

        self.main_plot.draw()

    def reading_loop(self, serial):
        while not self.stop_flag:
            data = serial.readline()
            data = str(data.decode('utf-8'))
            self.textbox.append(data)
            cursor = self.textbox.textCursor()
            cursor.movePosition(QtGui.QTextCursor.End)
            self.textbox.setTextCursor(cursor)

            if data.startswith("Accel:"):
                span = re.search(r'\[[^\]]*\]', data).span()
                data_list = data[span[0] + 1:span[1] - 1].split(",")

                if self.x_data.size > 0:
                    self.y_data = np.append(self.y_data, int(data_list[0]))
                    self.x_data = np.append(self.x_data, self.x_data[-1] + self.timebase)
                    self.plot_data()
                else:
                    self.y_data = np.append(self.y_data, int(data_list[0]))
                    self.x_data = np.append(self.x_data, self.timebase)

    def read_port(self):
        try:
            ser = serial.Serial(port=self.com_port,
                                baudrate=int(self.baud_rate),
                                bytesize=int(self.data_bits),
                                parity=self.parity[0],
                                stopbits=int(self.stop_bits))
            self.textbox.append(f"Port {self.com_port} opened.\r")
            reading_proc = Thread(target=self.reading_loop, args=(ser,), daemon=True)
            reading_proc.start()

        except serial.serialutil.SerialException:
            self.textbox.append(f"No device found on {self.com_port}.\n")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = Window()
    app.exec_()
