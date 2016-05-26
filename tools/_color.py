from PyQt4 import QtGui
import pyqtgraph as pg
import numpy as np

class ColorWidget(QtGui.QDialog):
    def __init__(self, dock):
        QtGui.QDialog.__init__(self)
        self.dock = dock
        self.colors = []
        self.layout = QtGui.QFormLayout()
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        self.colorDialog=QtGui.QColorDialog()
        addFilter = QtGui.QPushButton("Add Filter")
        addFilter.setMaximumWidth(100)
        for l in self.dock.colors:
            if type(self.dock.colors[l]) != dict:
                f = self.makeFilter(column=l, color=self.dock.colors[l])
            else:
                for v in self.dock.colors[l]:
                    f = self.makeFilter(column=l, value = v, color=self.dock.colors[l][v])
        addFilter.pressed.connect(self.makeFilter)
        self.layout.addRow('', addFilter)
        self.layout.addWidget(buttonBox)
        buttonBox.accepted.connect(self.applyFilter)
        self.setLayout(self.layout)
        buttonBox.rejected.connect(self.close)
        self.colorDialog.colorSelected.connect(self.colorSelected)
        self.show()

    def applyFilter(self):
        colors = {}
        for w in self.colors:
            cs = w.children()
            l = cs[2].currentText() if type(cs[2]) == QtGui.QComboBox else cs[2].text()
            v = cs[3].currentText() if cs[3].isVisible() else ''
            color = cs[4].palette().color(QtGui.QPalette.Background)
            if l == 'Default':
                colors[l] = (color.redF(), color.greenF(), color.blueF(), color.alphaF())
            else:
                if l not in colors:
                    colors[l] = {}
                colors[l].update({v: (color.redF(), color.greenF(), color.blueF(), color.alphaF())})
        self.dock.colors = {}
        self.dock.update(colors=colors)
        self.close()

    def colorSelected(self, c):
        self.currentButton.setStyleSheet("background-color: rgba(%d, %d, %d, %d);" % (c.red(), c.green(), c.blue(), c.alpha()))

    def makeFilter(self, column=None, value=None, color=None):
        w = QtGui.QWidget()
        lay = QtGui.QHBoxLayout()
        removeButton = QtGui.QPushButton('-')
        removeButton.setMaximumWidth(30)
        valueSpin = QtGui.QComboBox()
        colorButton = QtGui.QPushButton("Set Color")
        removeButton.pressed.connect(lambda : self.removeFilter(w))

        def setValues(i):
            valueSpin.clear()
            s = self.dock.data.columns[i]
            data = np.unique(self.dock.data[s].values.astype(str))[:30]
            if not all([type(a) == str for a in data]):
                data = [str(i) for i in data]
            valueSpin.addItems(data)
            if str(value) in data:
                valueSpin.setCurrentIndex(data.index(str(value)))

        if column == 'Default':
            columnSpin = QtGui.QLabel(column)
            removeButton.setVisible(False)
            valueSpin.setVisible(False)
        else:
            columnSpin = QtGui.QComboBox()
            columnSpin.currentIndexChanged.connect(setValues)
            columnSpin.addItems(self.dock.data.columns)
            if column != None:
                columnSpin.setCurrentIndex(list(self.dock.data.columns).index(column))
            
        if color != None:
            color = tuple(255 * i for i in color)
            colorButton.setStyleSheet("background-color: rgba(%d, %d, %d, %d);" % color)
        
        def colorPressed():
            self.currentButton = colorButton
            self.colorDialog.show()

        colorButton.pressed.connect(colorPressed)
        lay.addWidget(removeButton)
        lay.addWidget(columnSpin)
        lay.addWidget(valueSpin)
        lay.addWidget(colorButton)
        w.setLayout(lay)
        self.layout.insertRow(self.layout.rowCount() - 2, w)
        self.colors.append(w)

    def removeFilter(self, w):
        self.layout.removeWidget(w)
        w.close()
        self.colors.remove(w)