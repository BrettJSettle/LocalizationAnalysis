from PyQt4 import QtGui

from PyQt4.QtCore import *

import pandas as pd
import numpy as np
import pyqtgraph as pg
import file_manager as fm

class FileViewWidget(QtGui.QWidget):
    accepted = Signal(object)
    def __init__(self, filename):
        self.filename = filename
        QtGui.QWidget.__init__(self)
        layout = QtGui.QFormLayout()
        self.setLayout(layout)
        data = [l.strip().split('\t') for l in open(filename, 'r').readlines()[:20]]

        dataWidget = pg.TableWidget(editable=True, sortable=False)
        dataWidget.setData(data)
        dataWidget.setMaximumHeight(300)
        layout.addRow(dataWidget)
        self.headerCheck = QtGui.QCheckBox('Skip First Row As Headers')
        self.headerCheck.setChecked('Xc' in data[0])
        self.xComboBox = QtGui.QComboBox()
        self.yComboBox = QtGui.QComboBox()
        self.colorButton = QtGui.QPushButton()
        self.color = (np.random.random(), np.random.random(), np.random.random(), 1)
        self.colorButton.setStyleSheet("background-color: rgba(%d, %d, %d, %d);" % tuple(255 * i for i in self.color))
        self.colorDialog=QtGui.QColorDialog()
        self.colorDialog.colorSelected.connect(self.colorSelected)
        self.colorButton.pressed.connect(self.colorDialog.show)
        names = data[0]

        for i in range(dataWidget.columnCount()):
            self.xComboBox.addItem(str(i+1))
            self.yComboBox.addItem(str(i+1))

        Xc = data[0].index('Xc') if 'Xc' in data[0] else 0
        Yc = data[0].index('Yc') if 'Yc' in data[0] else 1
        self.xComboBox.setCurrentIndex(Xc)
        self.yComboBox.setCurrentIndex(Yc)
        
        layout.addRow('Headers', self.headerCheck)
        layout.addRow('Xc Column', self.xComboBox)
        layout.addRow('Yc Column', self.yComboBox)
        layout.addRow('Color', self.colorButton)
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        layout.addRow(buttonBox)
        buttonBox.accepted.connect(self.import_data)
        buttonBox.rejected.connect(self.close)
        self.setWindowTitle(filename)

    def colorSelected(self, c):
        self.color = c.getRgbF()
        self.colorButton.setStyleSheet("background-color: rgba(%d, %d, %d, %d);" % (c.red(), c.green(), c.blue(), c.alpha()))

    def import_data(self):
        if self.headerCheck.isChecked():
            data = pd.read_table(self.filename)
            if 'Xc' not in data or 'Yc' not in data:
                cols = list(data.columns)
                cols[int(self.xComboBox.currentText())-1] = 'Xc'
                cols[int(self.yComboBox.currentText())-1] = 'Yc'
                data.columns = cols
            for i in range(len(data.columns)):
                try:
                    if all(np.isnan(data.values[:, i])):
                        data = data.drop(data.columns[[i]], axis=1)
                except:
                    pass
        else:
            data = np.loadtxt(self.filename, usecols=[int(self.xComboBox.currentText())-1, int(self.yComboBox.currentText())-1], dtype={'names': ['Xc', 'Yc'], 'formats':[np.float, np.float]})
            data = pd.DataFrame(data)
        self.accepted.emit(data)
        self.close()
