
import dep_check

import pandas as pd
import numpy as np
import pyqtgraph as pg
import file_manager as fm

from pyqtgraph.dockarea import *
from pyqtgraph.console import *
from PyQt4.QtCore import *

import os, difflib, time, vispy.scene, threading

from collections import defaultdict
from tools._dbscan import *
from PyQt4 import QtGui, QtCore
from visuals import MyROI
from vispy.scene import visuals
from vispy.scene.cameras import MagnifyCamera, Magnify1DCamera, PanZoomCamera

app = QtGui.QApplication([])

class FilterWidget(QtGui.QDialog):
    def __init__(self, dock):
        QtGui.QDialog.__init__(self)
        self.dock = dock
        self.filters = []
        self.layout = QtGui.QFormLayout()
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        self.colorDialog=QtGui.QColorDialog()
        addFilter = QtGui.QPushButton("Add Filter")
        addFilter.setMaximumWidth(100)
        for l in self.dock.filters:
            if type(self.dock.filters[l]) != dict:
                f = self.makeFilter(column=l, color=self.dock.filters[l])
            else:
                for v in self.dock.filters[l]:
                    f = self.makeFilter(column=l, value = v, color=self.dock.filters[l][v])
        addFilter.pressed.connect(self.makeFilter)
        self.layout.addRow('', addFilter)
        self.layout.addWidget(buttonBox)
        buttonBox.accepted.connect(self.applyFilter)
        self.setLayout(self.layout)
        buttonBox.rejected.connect(self.close)
        self.colorDialog.colorSelected.connect(self.colorSelected)
        self.show()

    def applyFilter(self):
        filters = {}
        for w in self.filters:
            cs = w.children()
            l = cs[2].currentText() if type(cs[2]) == QtGui.QComboBox else cs[2].text()
            v = cs[3].currentText() if cs[3].isVisible() else ''
            color = cs[4].palette().color(QtGui.QPalette.Background)
            if l == 'Default':
                filters[l] = (color.redF(), color.greenF(), color.blueF(), color.alphaF())
            else:
                if l not in filters:
                    filters[l] = {}
                filters[l].update({v: (color.redF(), color.greenF(), color.blueF(), color.alphaF())})
        self.dock.update(filters=filters)
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
        self.filters.append(w)

    def removeFilter(self, w):
        self.layout.removeWidget(w)
        w.close()
        self.filters.remove(w)

class PlotDock(Dock):
    sigUpdated = Signal(object)
    sigROITranslated = Signal(object)
    def __init__(self, name, data):
        Dock.__init__(self, name, closable=True)
        data.insert(0, 'File', os.path.basename(name))
        self.canvas = vispy.scene.SceneCanvas(keys='interactive')
        self.grid = self.canvas.central_widget.add_grid()
        self.vb = self.grid.add_view(row=0, col=0)
        self.layout.addWidget(self.canvas.native)
        
        self.scatter = visuals.Markers()
        self.scatter.set_data(pos=np.zeros((2, 3)))
        self.vb.add(self.scatter)

        self.gridLines = visuals.GridLines(parent=self.vb.scene)
        self.vb.camera = PanZoomCamera()
        self.canvas.scene._process_mouse_event = self.mouseEvent
        self.canvas.resize_event = self.resizeEvent

        self.currentROI = None
        self.rois = []
        self.pos = [0, 0]
        self.filters = {}
        self.update(filters={'Default': (np.random.random(), np.random.random(), np.random.random(), 1.)}, data=data)


    def dataStr(self):
        s = 'Name: %s\n' % self.name()
        s += "Mouse: (%.2f, %.2f)\n" % (self.pos[0], self.pos[1])
        s += 'N Points: %s\n' % len(self.data)
        s += '\n'
        if len(self.rois) > 0:
            for roi in self.rois:
                s += '%s\n' % roi.dataStr()
        return s

    def resizeEvent(self, ev):
        vb_x, vb_y = self.vb.size
        cam_x, cam_y = self.vb.camera.rect.size
        A = (cam_x * vb_y) / (cam_y * vb_x)
        self.vb.camera.rect.size = (cam_x, A * cam_y)

    def mapToCamera(self, pos):
        pos = pos / self.vb.size
        pos[1] = 1-pos[1]
        r = self.vb.camera.rect
        return r.pos + pos * r.size

    def exportROIs(self):
        fname = fm.getSaveFileName()
        if fname == '':
            return
        s = [repr(roi) for roi in self.rois]
        s = '\n'.join(s)
        open(fname, 'w').write(s)

    def getColors(self):
        colors = np.array([self.filters['Default']] * len(self.data))
        for f in self.filters:
            if f != 'Default':
                for v in self.filters[f]:
                    colors[self.data[f].values.astype(str) == v] = self.filters[f][v]
        return colors

    def importROIs(self):
        fname = fm.getOpenFileName()
        if fname == '':
            return
        rois = ROIVisual.importROIs(fname, self)
        self.rois.extend(rois)

    def clearROIs(self):
        while len(self.rois) > 0:
            self.rois[0].delete()

    def exportPoints(self):
        fname = fm.getSaveFileName()
        if fname == '':
            return
        open(fname, 'w').write(str(self.data))

    def addChannel(self, name=None, data=[]):
        if name == None:
            name = fm.getOpenFileName()
        if name == '':
            return

        if len(data) == 0:
            self.fileWidget = FileViewWidget(name)
            self.fileWidget.accepted.connect(lambda d : self.addChannel(name, d))
            self.fileWidget.show()
            return

        data.insert(0, 'File', os.path.basename(name))
        self.update(data=pd.concat([self.data, data]), filters={'File': {os.path.basename(name): (np.random.random(), np.random.random(), np.random.random(), 1)}})

    def showFilter(self):
        self.filterWidget = FilterWidget(self)
        self.filterWidget.show()

    def raiseContextMenu(self, pos):
        self.menu = QtGui.QMenu(self.name())
        self.menu.addAction("Add Channel", self.addChannel)
        roiMenu = self.menu.addMenu("ROIs")
        roiMenu.addAction("Import from txt", self.importROIs)
        roiMenu.addAction("Export to txt", self.exportROIs)
        roiMenu.addAction("Clear All", self.clearROIs)
        self.menu.addAction("Export Points", self.exportPoints)
        self.menu.addAction("Filter", self.showFilter)
        self.menu.addAction("Close Dock", self.close)
        self.menu.popup(pos)

    def mouseEvent(self, ev):
        self.sigUpdated.emit(self)
        pos = self.mapToCamera(ev.pos)
        self.pos = pos
        for roi in self.rois:
            roi.mouseIsOver(pos)

        if ev.button == 2:
            if ev.press_event != None:
                if ev.press_event.type == 'mouse_release':
                    if self.currentROI != None:
                        if len(self.currentROI.points) > 4:
                            self.currentROI.draw_finished()
                            self.rois.append(self.currentROI)
                            self.currentROI = None
                        else:
                            self.currentROI.delete()
                            self.currentROI = None
                            for roi in self.rois:
                                if roi.hover:
                                    roi.raiseContextMenu(self.canvas.native.mapToGlobal(QtCore.QPoint(*ev.pos)))
                                    return
                            self.raiseContextMenu(self.canvas.native.mapToGlobal(QtCore.QPoint(*ev.pos)))
                elif ev.press_event.type == 'mouse_move':
                    self.currentROI.extend(pos)
            else:
                self.currentROI = MyROI(self, pos, parent=self.canvas.scene)
                self.currentROI.transform = self.vb._camera._transform
        elif ev.button == 1 and (self.currentROI != None or any([roi.hover for roi in self.rois])):
            if ev.press_event != None:
                if ev.press_event.type == 'mouse_release':
                    if self.currentROI != None:
                        self.currentROI.translate_finished()
                        self.currentROI = None
                if ev.press_event.type == 'mouse_move' and self.currentROI != None:
                    self.sigROITranslated.emit(self.currentROI)
                    last = self.mapToCamera(ev.last_event.pos)
                    self.currentROI.translate(pos-last)
                else:
                    self.canvas.scene.__class__._process_mouse_event(self.canvas.scene, ev)
            else:
                for roi in self.rois:
                    if roi.hover:
                        self.currentROI = roi
                        break
        else:
            self.canvas.scene.__class__._process_mouse_event(self.canvas.scene, ev)

    def update(self, data=[], filters=None, autoRange=True):
        if np.size(data) != 0:
            self.data = data
        if filters != None:
            for f in filters:
                if f == 'Default':
                    self.filters['Default'] = filters['Default']
                else:
                    if f not in self.filters:
                        self.filters[f] = filters[f]
                    else:
                        self.filters[f].update(filters[f])

        colors = self.getColors()
        pos = np.transpose([self.data['Xc'], self.data['Yc']])
        self.scatter.set_data(pos, edge_color=None, face_color=colors, size=3)
        if autoRange:
            w, h = np.ptp(pos, 0)
            x, y = np.min(pos, 0)
            self.vb.camera.rect = (x, y, w, h)


class MainWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.resize(1000, 800)
        self.installEventFilter(self)

        fileMenu = self.menuBar().addMenu('File')
        fileMenu.addAction("Open File", self.open_file_gui)
        self.recentMenu = fileMenu.addMenu('Recent Files')
        viewMenu = self.menuBar().addMenu('View')
        viewMenu.addAction('Console', self.show_console)


        widget = QtGui.QWidget()
        layout = QtGui.QGridLayout(widget)
        widget.setLayout(layout)

        self.optionsWidget = QtGui.QWidget()
        self.optionsWidget.setMaximumWidth(200)
        self.optionsWidget.setMinimumWidth(200)
        self.options_layout = QtGui.QVBoxLayout(self.optionsWidget)
        self.infoEdit = QtGui.QTextEdit("Information Here")
        self.infoEdit.setReadOnly(True) 
        self.scanWidget = DBScanWidget(self)
        self.options_layout.addWidget(self.infoEdit)
        self.options_layout.addWidget(self.scanWidget)

        self.dockarea = DockArea()

        layout.addWidget(self.optionsWidget, 0, 0)
        layout.addWidget(self.dockarea, 0, 1)
        layout.setColumnStretch(0, 1)

        self.setAcceptDrops(True)
        self.setCentralWidget(widget)
        self.update_history()

    def update_history(self):
        self.recentMenu.clear()
        fs = fm.recent_files()
        if len(fs) > 6:
            fs = fs[:6]
        for i in range(len(fs)):
            def lambda_open(s):
                return lambda : self.open_file(s)
            action = QtGui.QAction(fs[i], self.recentMenu, triggered=lambda_open(fs[i]))
            self.recentMenu.addAction(action)

    def open_file_gui(self):
        f = str(fm.getOpenFileName())
        self.open_file(f)

    def open_file(self, f):
        f = str(f)
        self.update_history()
        self.fileWidget = FileViewWidget(f)
        self.fileWidget.accepted.connect(lambda d: self.addDock(f, d))
        self.fileWidget.show()
    
    def showDockData(self, dock):
        self.infoEdit.setText(dock.dataStr())

    def addDock(self, f, data):
        dock = PlotDock(os.path.basename(f), data)
        dock.sigUpdated.connect(self.showDockData)
        self.dockarea.addDock(dock)

    def show_console(self):
        if not hasattr(self, 'c') or not self.c.isVisible():
            self.c = ConsoleWidget()
            self.c.localNamespace.update({'self': self, 'PlotDock': PlotDock, 'dock':lambda i: [d for d in self.dockarea.docks.values()][i]})
        self.c.show()

    def eventFilter(self, obj, event):
        if (event.type()==QtCore.QEvent.DragEnter):
            if event.mimeData().hasUrls():
                event.accept()   # must accept the dragEnterEvent or else the dropEvent can't occur !!!
            else:
                event.ignore()
        if (event.type() == QtCore.QEvent.Drop):
            if event.mimeData().hasUrls():   # if file or link is dropped
                url = event.mimeData().urls()[0]   # get first url
                filename=url.toString()
                filename=filename.split('file:///')[1]
                if filename.endswith('.txt'):
                    self.statusBar().showMessage('Loading points from %s' % (filename))
                    self.read_file(filename)
                    fm.update_history(filename)
                else:
                    self.statusBar().showMessage('No support for %s files...' % filename[-4])
                event.accept()
            else:
                event.ignore()
        return False # lets the event continue to the edit

    def closeEvent(self, evt):
        QtGui.QMainWindow.closeEvent(self, evt)
        if hasattr(self, 'c'):
            self.c.close()


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
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        layout.addRow(buttonBox)
        buttonBox.accepted.connect(self.import_data)
        buttonBox.rejected.connect(self.close)
        self.setWindowTitle(filename)

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
        self.accepted.emit(data)
        self.close()

        


if __name__ == '__main__':
    mw = MainWindow()
    mw.show()

    app.exec_()