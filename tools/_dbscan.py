from sklearn.cluster import DBSCAN
from PyQt4 import QtGui, QtCore
from visuals import Cluster
from analysis import *
from PyQt4.QtCore import *
from pyqtgraph.dockarea import *
import pyqtgraph as pg
import numpy as np
import time
import file_manager as fm

class SynapseWidget(QtGui.QWidget):
    '''
    Designed to cluster two channels within an ROI, 
    '''
    def __init__(self, window):
        QtGui.QWidget.__init__(self)
        self.window = window
        layout = QtGui.QFormLayout()
        self.channel1 = QtGui.QComboBox()
        self.channel2 = QtGui.QComboBox()
        
        self.epsilonSpin = pg.SpinBox(value=100)
        self.densitySpin = pg.SpinBox(value=1, int=True, step=1)
        self.minSizeSpin = pg.SpinBox(value=3, int=True, step=1)
        self.roiComboBox = pg.ComboBox()
        self.roiComboBox.mousePressEvent = self.comboBoxClicked
        self.roiComboBox.currentIndexChanged.connect(self.roiChanged)
        self.roiComboBox.updating = False
        self.scanButton = QtGui.QPushButton("Cluster")
        self.scanButton.pressed.connect(self.scan)
        self.simulateCheck = QtGui.QCheckBox("Simulated", checked=True)
        self.exportButton = QtGui.QPushButton("Export Distances")
        self.exportButton.pressed.connect(self.exportDistances)

        self.table = pg.TableWidget()
        layout.addRow("ROI:", self.roiComboBox)
        layout.addRow(self.channel1, self.channel2)
        layout.addRow("Epsilon:", self.epsilonSpin)
        layout.addRow("Min Density:", self.densitySpin)
        layout.addRow("Min N Points:", self.minSizeSpin)
        layout.addRow(self.table)
        layout.addRow(self.scanButton)
        layout.addRow(self.simulateCheck, self.exportButton)
        self.table.setMinimumHeight(200)

        self.table.save = self.save
        self.clusters = [[], []]

        self.setLayout(layout)

    def exportDistances(self):
        fname = fm.getSaveFileName(filter='Text Files (*.txt)')
        if fname == '':
            return
        centers1 = [cl.centroid for cl in self.clusters[0]]
        centers2 = [cl.centroid for cl in self.clusters[1]]
        self.window.statusBar().showMessage("Calculating distances...")
        if self.twoChannel:
            dists = nearestDistances(centers1, centers2)
        else:
            dists = nearestDistances(centers1)

        header = 'Nearest Distances'
        if self.simulateCheck.isChecked():
            self.window.statusBar().showMessage("Simulating centroid distances...")
            min1 = np.min(centers1, 0)
            min2 = np.min(centers2, 0)
            max1 = np.max(centers1, 0)
            max2 = np.max(centers2, 0)
            mi = np.min([min1, min2], 0)
            ma = np.max([max1, max2], 0)
            xRange, yRange = [mi[0], ma[0]], [mi[1], ma[1]]

            centers1 = np.random.random((len(centers1),2)) * [mi[1]-xRange[0], yRange[1]-yRange[0]] + [xRange[0], yRange[0]]
            centers2 = np.random.random((len(centers2),2)) * [xRange[1]-xRange[0], yRange[1]-yRange[0]] + [xRange[0], yRange[0]]

            sim_dists = nearestDistances(centers1, centers2)
            dists = np.transpose([dists, sim_dists])
            header += '\tSimulated'
        self.window.statusBar().showMessage("Saving distances to %s..." % fname)
        np.savetxt(fname, dists, header=header, delimiter='\t', fmt='%.3f')
        self.window.statusBar().showMessage("Distances successfully saved to %s..." % fname)

    def roiChanged(self, i):
        self.channel1.clear()
        self.channel2.clear()
        if i >= len(self.rois):
            return
        roi = self.rois[i]
        channels = list(roi.analysis_data.keys())
        self.channel1.addItems(channels)
        self.channel2.addItems(['None'] + channels)

    def save(self, data):
        fileName = fm.getSaveFileName(filter="Text File (*.txt)")
        if fileName == '':
            return
        data = '\t'.join(["N Points", 'Xc', 'Yc', 'Average Internal Distance']) + '\n' + data
        open(fileName, 'w').write(data)

    def scan(self):
        for ch in self.clusters:
            for cl in ch:
                cl.remove()

        self.clusters = [[], []]

        if not hasattr(self, 'rois'): 
            return
        eps = self.epsilonSpin.value()
        density = self.densitySpin.value()
        minSize = self.minSizeSpin.value()

        
        roi = self.rois[self.roiComboBox.currentIndex()]
        data = roi.analysis_data
        
        chan1 = self.channel1.currentText()
        chan2 = self.channel2.currentText()
        self.twoChannel = chan2 != 'None'
        
        pos1 = roi.analysis_data[chan1]['points']
        pos1 = np.transpose([pos1.Xc.values, pos1.Yc.values])

        self.thread1 = DensityBasedScanner(pos1, epsilon=eps, minNeighbors=density, minP=minSize)
        self.thread1.scanFinished.connect(lambda cl, no: self.scanFinished(0, cl))
        if self.twoChannel:
            pos2 = roi.analysis_data[chan2]['points']
            pos2 = np.transpose([pos2.Xc.values, pos2.Yc.values])
            self.thread2 = DensityBasedScanner(pos2, epsilon=eps, minNeighbors=density, minP=minSize)
            self.thread2.scanFinished.connect(lambda cl, no: self.scanFinished(1, cl))
            self.thread1.scanFinished.connect(self.thread2.start)
        self.thread1.start()


    def scanFinished(self, num, clusters):
        self.clusters[num] = clusters
        if num == 0:
            self.values = []
        roi = self.rois[self.roiComboBox.currentIndex()]
        for ch in self.clusters:
            for cluster in ch:
                self.values.append([len(cluster.points), cluster.centroid[0], cluster.centroid[1], cluster.averageDistance])
                cluster.visual(roi.dock)

        self.table.setData(self.values)
        self.table.setHorizontalHeaderLabels(["N", 'Xc', 'Yc', 'Avg. Internal Dist.'])

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
                c = 255 * np.array(roi.border_color.rgba)
                item.setBackground(pg.mkBrush(c))
                model.appendRow(item)

        self.roiComboBox.updating = False
        QtGui.QComboBox.mousePressEvent(self.roiComboBox, ev)


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
        self.scanner = DBSCAN(eps=self.epsilon, min_samples=self.minNeighbors)

    def update(self, points, epsilon=None, minP = None, minNeighbors = None):
        if epsilon != None:
            self.epsilon = epsilon
        if minP != None:
            self.minP = minP
        if minNeighbors != None:
            self.minNeighbors = minNeighbors
        self.points = points
        self.scanner = DBSCAN(eps=self.epsilon, min_samples=self.minNeighbors)

    def clearClusters(self):
        self.clusters = []

    def run(self):
        self.clearClusters()
        if len(self.points) == 0:
            return
        labels = self.scanner.fit_predict(self.points)
        noise = [self.points[p] for p in np.where(labels == -1)[0]]
        for i in range(0, max(labels) + 1):
            clust = []
            for p in np.where(labels == i)[0]:
                clust.append(self.points[p])
            if len(clust) >= self.minP:
                cl = Cluster(clust)
                self.clusters.append(cl)
            else:
                noise.extend(clust)
            self.messageEmit.emit("Analyzed %d of %d clusters" % (i, max(labels)))
        self.scanFinished.emit(self.clusters, noise)