from PyQt4 import QtGui, QtCore
import dep_check

import pandas as pd
import numpy as np
import pyqtgraph as pg
import file_manager as fm

from pyqtgraph.dockarea import *
from pyqtgraph.console import *
from PyQt4.QtCore import *

import os, difflib, time, vispy.scene, threading
from visuals import MyROI, MyCluster
from vispy.scene import visuals
from vispy.scene.cameras import MagnifyCamera, Magnify1DCamera, PanZoomCamera

from sklearn.cluster import DBSCAN

app = QtGui.QApplication([])

class PlotDock(Dock):
    sigUpdated = Signal(object)
    sigROITranslated = Signal(object)
    def __init__(self, name, data):
        Dock.__init__(self, name, closable=True)
        self.canvas = vispy.scene.SceneCanvas(keys='interactive')
        self.grid = self.canvas.central_widget.add_grid()
        self.vb = self.grid.add_view(row=0, col=0)
        self.layout.addWidget(self.canvas.native)
        
        self.scatter = visuals.Markers()

        self.gridLines = visuals.GridLines(parent=self.vb.scene)
        self.vb.camera = PanZoomCamera()
        self.canvas.scene._process_mouse_event = self.mouseEvent
        self.canvas.resize_event = self.resizeEvent

        self.currentROI = None
        self.rois = []
        self.pos = [0, 0]
        self.setData(data)


    def dataStr(self):
        s = 'Name: %s\n' % self.name()
        s += "Mouse: (%f, %f)\n" % (self.pos[0], self.pos[1])
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

    def setData(self, data):
        pos = np.transpose([data['Xc'], data['Yc']])
        self.data = data
        self.scatter.set_data(pos, edge_color=None, face_color=(0, 1, 0, 1), size=3)
        self.vb.add(self.scatter)
        w, h = np.ptp(pos, 0)
        x, y = np.min(pos, 0)
        self.vb.camera.rect = (x, y, w, h)

class DensityBasedScanner(QtCore.QThread):
    '''
    Density Based Clustering algorithm on a list of ActivePoint objects. returns a list of clustered point lists, and a list of noise points
    '''
    messageEmit = Signal(str)
    scanFinished = Signal(object, object)
    def __init__(self, points = [], epsilon = 30, minP = 5, minNeighbors = 1):
        QtCore.QThread.__init__(self)
        self.points = points
        self.epsilon = epsilon
        self.minP = minP
        self.minNeighbors = minNeighbors
        self.clusters = []
        self.roi = None
        self.scanner = DBSCAN(eps=self.epsilon, min_samples=self.minNeighbors)

    def update(self, roi, epsilon=None, minP = None, minNeighbors = None):
        if self.roi != None and roi != self.roi:
            self.roi.dock.sigROITranslated.disconnect(self.roiTranslated)
        if epsilon != None:
            self.epsilon = epsilon
        if minP != None:
            self.minP = minP
        if minNeighbors != None:
            self.minNeighbors = minNeighbors
        self.roi = roi
        self.roi.dock.sigROITranslated.connect(self.roiTranslated)
        self.points = self.roi.internal_points
        self.scanner = DBSCAN(eps=self.epsilon, min_samples=self.minNeighbors)

    def roiTranslated(self, roi):
        if roi == self.roi:
            self.clearClusters()

    def clearClusters(self):
        for cl in self.clusters:
            cl.remove_parent(cl.parent)
        self.clusters = []

    def run(self):
        self.clearClusters()
        if len(self.points) == 0:
            return
        labels = self.scanner.fit_predict([p for p in self.points])
        noise = [self.points[p] for p in np.where(labels == -1)[0]]
        for i in range(1, max(labels) + 1):
            clust = []
            for p in np.where(labels == i)[0]:
                clust.append(self.points[p])
            if len(clust) >= self.minP:
                cl = MyCluster(clust, parent=self.roi.dock.canvas.scene)
                cl.transform = self.roi.dock.vb._camera._transform
                self.clusters.append(cl)
            else:
                noise.extend(clust)
            self.messageEmit.emit("Analyzed %d of %d clusters" % (i, max(labels)))
        self.scanFinished.emit(self.clusters, noise)


class DBScanWidget(QtGui.QWidget):
    def __init__(self, window):
        QtGui.QWidget.__init__(self)
        self.window = window
        layout = QtGui.QFormLayout()
        self.setLayout(layout)
        self.epsilonSpin = pg.SpinBox(value=4)
        self.densitySpin = pg.SpinBox(value=1, int=True, step=1)
        self.minSizeSpin = pg.SpinBox(value=3, int=True, step=1)
        self.roiComboBox = pg.ComboBox()
        self.roiComboBox.mousePressEvent = self.comboBoxClicked
        self.roiComboBox.updating = False
        self.scanButton = QtGui.QPushButton("Cluster")
        self.scanButton.pressed.connect(self.scan)
        self.table = pg.TableWidget()
        layout.addRow("Epsilon:", self.epsilonSpin)
        layout.addRow("Min Density:", self.densitySpin)
        layout.addRow("Min N Points:", self.minSizeSpin)
        layout.addRow("ROI:", self.roiComboBox)
        layout.addRow(self.table)
        layout.addRow(self.scanButton)
        self.table.setMinimumHeight(200)

        self.table.save = self.save

        self.scanThread = DensityBasedScanner()
        self.scanThread.scanFinished.connect(self.scanFinished)

    def save(self, data):
        fileName = QtGui.QFileDialog.getSaveFileName(self, "Save As..", "", "Text File (*.txt)")
        if fileName == '':
            return
        data = '\t'.join(["N Points", 'Xc', 'Yc', 'Average Internal Distance']) + '\n' + data
        open(fileName, 'w').write(data)

    def scan(self):
        if not hasattr(self, 'rois'):
            return
        eps = self.epsilonSpin.value()
        density = self.densitySpin.value()
        minSize = self.minSizeSpin.value()
        self.scanThread.update(self.rois[self.roiComboBox.currentIndex()], epsilon=eps, minNeighbors=density, minP=minSize)
        self.window.statusBar().showMessage('Clustering %d points.' % len(self.rois[self.roiComboBox.currentIndex()].internal_points))
        self.scanThread.start_time = time.time()
        self.scanThread.start()

    def scanFinished(self, clusters, noise):
        values = []
        self.clusters = clusters
        for cluster in clusters[:100]:
            values.append([len(cluster.points), cluster.centroid[0], cluster.centroid[1], cluster.averageDistance])
        self.table.setData(values)

        self.table.setHorizontalHeaderLabels(["N Points", 'Xc', 'Yc', 'Average Internal Distance'])
        self.window.statusBar().showMessage('%d clusters found (%s s)' % (len(clusters), time.time() - self.scanThread.start_time))

    def comboBoxClicked(self, ev):
        txt = self.roiComboBox.currentText()
        self.roiComboBox.updating = True
        self.roiComboBox.clear()
        self.rois = []
        for d in self.window.dockarea.docks.values():
            self.rois.extend(d.rois)
        if len(self.rois) == 0:
            self.roiComboBox.addItem("No Trace Selected")
        else:
            model = self.roiComboBox.model()
            for roi in self.rois:
                item = QtGui.QStandardItem("ROI #%d" % (roi.id))
                item.setBackground(pg.mkBrush(roi.color.rgb))
                model.appendRow(item)
        self.roiComboBox.updating = False
        QtGui.QComboBox.mousePressEvent(self.roiComboBox, ev)

class MainWindow(QtGui.QMainWindow):
    def __init__(self):
        QtGui.QMainWindow.__init__(self)

        fileMenu = self.menuBar().addMenu('File')
        openAction = QtGui.QAction("Open File", fileMenu, triggered=self.open_file_gui)
        fileMenu.addAction(openAction)
        self.recentMenu = QtGui.QMenu('Recent Files')
        fileMenu.addMenu(self.recentMenu)
        viewMenu = self.menuBar().addMenu('View')
        consoleAction = QtGui.QAction('Console', viewMenu, triggered=self.show_console)
        viewMenu.addAction(consoleAction)

        widget = QtGui.QWidget()
        layout = QtGui.QGridLayout(widget)
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        self.optionsWidget = QtGui.QWidget()
        self.optionsWidget.setMaximumWidth(200)
        self.optionsWidget.setMinimumWidth(200)
        self.options_layout = QtGui.QVBoxLayout(self.optionsWidget)
        self.infoEdit = QtGui.QTextEdit("Information Here")
        #self.infoEdit.setMaximumHeight(300)
        self.scanWidget = DBScanWidget(self)
        self.options_layout.addWidget(self.infoEdit)
        self.options_layout.addWidget(self.scanWidget)

        layout.addWidget(self.optionsWidget, 0, 0)

        self.dockarea = DockArea()
        layout.addWidget(self.dockarea, 0, 1)
        layout.setColumnStretch(0, 1)

        self.resize(1000, 800)
        self.installEventFilter(self)
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
        self.read_file(f)
    
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
                    dataWindow.statusBar().showMessage('Loading points from %s' % (filename))
                    import_channels(filename)
                    file_manager.update_history(filename)
                else:
                    obj.statusBar().showMessage('%s widget does not support %s files...' % (obj.__name__, filetype))
                event.accept()
            else:
                event.ignore()
        return False # lets the event continue to the edit

    def closeEvent(self, evt):
        QtGui.QMainWindow.closeEvent(self, evt)
        if hasattr(self, 'c'):
            self.c.close()


    def read_file(self, filename):
        self.fileWidget = QtGui.QWidget()
        layout = QtGui.QFormLayout()
        self.fileWidget.setLayout(layout)
        data = [l.strip().split('\t') for l in open(filename, 'r').readlines()[:20]]

        dataWidget = pg.TableWidget(editable=True, sortable=False)
        dataWidget.setData(data)
        dataWidget.setMaximumHeight(300)
        layout.addRow(dataWidget)
        headerCheck = QtGui.QCheckBox('Skip First Row As Headers')
        headerCheck.setChecked('Xc' in data[0])
        xComboBox = QtGui.QComboBox()
        yComboBox = QtGui.QComboBox()
        names = data[0]

        for i in range(dataWidget.columnCount()):
            xComboBox.addItem(str(i+1))
            yComboBox.addItem(str(i+1))

        Xc = data[0].index('Xc') if 'Xc' in data[0] else 0
        Yc = data[0].index('Yc') if 'Yc' in data[0] else 1
        xComboBox.setCurrentIndex(Xc)   
        yComboBox.setCurrentIndex(Yc)
        
        layout.addRow('Headers', headerCheck)
        layout.addRow('Xc Column', xComboBox)
        layout.addRow('Yc Column', yComboBox)
        buttonBox = QtGui.QDialogButtonBox(QtGui.QDialogButtonBox.Ok | QtGui.QDialogButtonBox.Cancel)
        layout.addRow(buttonBox)
        self.fileWidget.show()

        def import_data():
            if headerCheck.isChecked():
                data = pd.read_table(filename)
                if 'Xc' not in data or 'Yc' not in data:
                    cols = list(data.columns)
                    cols[int(xComboBox.currentText())-1] = 'Xc'
                    cols[int(yComboBox.currentText())-1] = 'Yc'
                    data.columns = cols
            else:
                data = np.loadtxt(filename, usecols=[int(xComboBox.currentText())-1, int(yComboBox.currentText())-1], dtype={'names': ['Xc', 'Yc'], 'formats':[np.float, np.float]})
            self.addDock(filename, data)
            self.fileWidget.close()
            del self.fileWidget

        buttonBox.accepted.connect(import_data)
        buttonBox.rejected.connect(self.fileWidget.close)
        self.fileWidget.setWindowTitle(filename)


if __name__ == '__main__':
    mw = MainWindow()
    mw.show()

    app.exec_()