from sklearn.cluster import DBSCAN
from PyQt4 import QtGui, QtCore
from PyQt4.QtCore import *
from visuals import MyCluster

import pyqtgraph as pg
import numpy as np


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