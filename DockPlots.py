
import dep_check

import pandas as pd
import numpy as np
import pyqtgraph as pg
import file_manager as fm

from pyqtgraph.dockarea import *
from pyqtgraph.console import *
from PyQt4.QtCore import *

import os, difflib, time, vispy.scene, threading

from tools._file import FileViewWidget
from tools._color import ColorWidget
from collections import defaultdict
from tools._dbscan import *
from PyQt4 import QtGui, QtCore
from visuals import MyROI, ROIVisual
from vispy.scene import visuals
from vispy.scene.cameras import MagnifyCamera, Magnify1DCamera, PanZoomCamera

app = QtGui.QApplication([])


class PlotDock(Dock):
    sigUpdated = Signal(object)
    sigROITranslated = Signal(object)
    def __init__(self, name, data, color=[]):
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
        self.canvas.on_resize = self.onResize

        self.currentROI = None
        self.rois = []
        self.pos = [0, 0]
        self.colors = {}
        if len(color) != 4:
            color = (np.random.random(), np.random.random(), np.random.random(), 1.)
        self.update(colors={'Default': color}, data=data)

    def resizeEvent(self, ev):
        Dock.resizeEvent(self, ev)
        self.rescale()

    def onResize(self, ev):
        vispy.scene.SceneCanvas.on_resize(self.canvas, ev)
        self.rescale()

    def dataStr(self):
        s = 'Name: %s\n' % self.name()
        s += "Mouse: (%.2f, %.2f)\n" % (self.pos[0], self.pos[1])
        s += 'N Points: %s\n' % len(self.data)
        s += '\n'
        return s

    def rescale(self):
        vb_x, vb_y = self.vb.size
        cam_x, cam_y = self.vb.camera.rect.size
        if cam_x > cam_y:
            A = (cam_x * vb_y) / (cam_y * vb_x)
            self.vb.camera.rect.size = (cam_x, A * cam_y)
        else:
            A = (cam_y * vb_x) / (cam_x * vb_y)
            self.vb.camera.rect.size = (cam_x * A, cam_y)
            
    def mapToCamera(self, pos):
        pos = pos / self.vb.size
        pos[1] = 1-pos[1]
        r = self.vb.camera.rect
        return r.pos + pos * r.size

    def exportROIs(self):
        fname = fm.getSaveFileName(filter='Text Files (*.txt)')
        if fname == '':
            return
        s = [repr(roi) for roi in self.rois]
        s = '\n'.join(s)
        open(fname, 'w').write(s)

    def getColors(self, data=[]):
        if len(data) == 0:
            data = self.data 
        colors = np.array([self.colors['Default']] * len(data))
        for f in self.colors:
            if f != 'Default':
                for v in self.colors[f]:
                    colors[data[f].values.astype(str) == v] = self.colors[f][v]
        return colors

    def importROIs(self):
        fname = fm.getOpenFileName(filter='Text Files (*.txt)')
        if fname == '':
            return
        ROIVisual.importROIs(fname, self)
        

    def clearROIs(self):
        while len(self.rois) > 0:
            self.rois[0].delete()

    def exportPoints(self):
        fname = fm.getSaveFileName(filter='Text Files (*.txt)')
        if fname == '':
            return
        open(fname, 'w').write(str(self.data))

    def addChannel(self, name=None, data=[], color=[]):
        if name == None:
            name = fm.getOpenFileName(filter='Text Files (*.txt)')
        if name == '':
            return

        if len(data) == 0:
            self.fileWidget = FileViewWidget(name)
            self.fileWidget.accepted.connect(lambda d : self.addChannel(name, d, color=self.fileWidget.color))
            self.fileWidget.show()
            return

        if len(color) != 4:
            color = (np.random.randint(255), np.random.randint(255), np.random.randint(255), 255)
        name = os.path.basename(name)
        if name in np.unique(self.data['File']):
            name += '_copy'
        data.insert(0, 'File', name)
        self.update(data=pd.concat([self.data, data]), colors={'File': {os.path.basename(name): color}})

    def showColorWidget(self):
        self.colorWidget = ColorWidget(self)
        self.colorWidget.show()

    def removeChannel(self, channel):
        data = self.data[self.data['File'] != channel]
        self.update(data=data)

    def raiseContextMenu(self, pos):
        self.menu = QtGui.QMenu(self.name())
        self.menu.addAction("Add File", self.addChannel)
        fs = np.unique(self.data['File'])
        if len(fs) > 1:
            removeMenu = self.menu.addMenu("Remove File")
            def removeChannel(name):
                return lambda : self.removeChannel(name)
            for f in fs:
                removeMenu.addAction(f, removeChannel(f))
        
        roiMenu = self.menu.addMenu("ROIs")
        roiMenu.addAction("Import from txt", self.importROIs)
        roiMenu.addAction("Export to txt", self.exportROIs)
        roiMenu.addAction("Clear All", self.clearROIs)
        self.menu.addAction("Export Points", self.exportPoints)
        self.menu.addAction("Change Color", self.showColorWidget)
        self.menu.addAction("Close Dock", self.close)
        self.menu.popup(pos)

    def mouseEvent(self, ev):
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
                                    self.sigUpdated.emit(self)
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
        self.sigUpdated.emit(self)

    def update(self, data=[], colors=None, autoRange=True):
        if np.size(data) != 0:
            self.data = data
        if colors != None:
            for f in colors:
                if f == 'Default':
                    self.colors['Default'] = colors['Default']
                else:
                    if f not in self.colors:
                        self.colors[f] = colors[f]
                    else:
                        self.colors[f].update(colors[f])

        colors = self.getColors()
        pos = np.transpose([self.data['Xc'], self.data['Yc']])
        self.scatter.set_data(pos, edge_color=None, face_color=colors, size=3)
        if autoRange:
            w, h = np.ptp(pos, 0)
            x, y = np.min(pos, 0)
            self.vb.camera.rect = (x, y, w, h)

        self.rescale()


class MainWindow(QtGui.QMainWindow):
    dockCreated = Signal(object)
    def __init__(self):
        QtGui.QMainWindow.__init__(self)
        self.resize(1200, 800)
        self.installEventFilter(self)

        widget = QtGui.QSplitter(Qt.Horizontal)

        self.infoEdit = QtGui.QTextEdit("Information Here")
        self.infoEdit.setReadOnly(True) 
        self.infoEdit.setMinimumHeight(200)
        self.synapseWidget = SynapseWidget(self)
        self.roiData = pg.TableWidget()
        self.roiData.setMinimumHeight(200)

        self.optionsArea = DockArea()
        self.optionsArea.setMaximumWidth(300)
        self.optionsArea.setMinimumWidth(200)
        self.optionsDock = self.optionsArea.addDock(name="Information", size=(200, 400), widget=self.infoEdit, hideTitle=True)
        self.roiDock = self.optionsArea.addDock(name="ROI Data", size=(200, 400), widget=self.roiData, hideTitle=True)
        self.synapseDock = self.optionsArea.addDock(name="Synapse Analysis", size=(200, 200), widget=self.synapseWidget)
        
        self.dockarea = DockArea()
        widget.addWidget(self.optionsArea)
        widget.addWidget(self.dockarea)

        fileMenu = self.menuBar().addMenu('File')
        fileMenu.addAction("Open File(s)", self.open_file_gui)
        self.recentMenu = fileMenu.addMenu('Recent Files')
        viewMenu = self.menuBar().addMenu('View')
        self.synapseCheck = QtGui.QAction('Synapse Widget', viewMenu, triggered=self.synapseDock.setVisible, checkable=True)
        viewMenu.addAction(self.synapseCheck)
        viewMenu.addAction('Console', self.show_console)
        self.synapseCheck.setChecked(True)
        self.roiData.save = self.save
        
        self.setAcceptDrops(True)
        self.setCentralWidget(widget)
        self.update_history()

    def save(self, data):
        fileName = fm.getSaveFileName(filter="Text File (*.txt)")
        if fileName == '':
            return
        data = '\t'.join(["Ch1 N", 'Ch2 N', 'Distance', 'Ch1 XY', 'Ch2 XY']) + '\n' + data
        open(fileName, 'w').write(data)


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
        fs = [str(i) for i in fm.getOpenFileNames(filter='Text Files (*.txt)')]
        if len(fs) == 0:
            return
        self.open_file(fs[0])
        def addFiles(d):
            for f in fs[1:]:
                d.addChannel(name=f)
            self.dockCreated.disconnect(addFiles)
        self.dockCreated.connect(addFiles)

    def open_file(self, f):
        f = str(f)
        self.update_history()
        self.fileWidget = FileViewWidget(f)
        self.fileWidget.accepted.connect(lambda d: self.addDock(f, d, color=self.fileWidget.color))
        self.fileWidget.show()
    
    def showDockData(self, dock):
        s = dock.dataStr()
        self.infoEdit.setText(s)
        data = []
        for roi in dock.rois:
            ch = list(roi.analysis_data.keys())
            if len(ch) == 0:
                data.append(["EMPTY"])
                continue
            elif len(ch) == 1:
                ch1, ch2 = ch[0], None
                c1 = roi.analysis_data[ch1]['centroid']
                data.append([roi.analysis_data[ch1]['nPoints'], 'NA', 'NA', '(%.2f, %.2f)' % (c1[0], c1[1]), 'NA'])
                continue 
            elif len(ch) == 2:
                ch1, ch2 = ch
            elif len(ch) > 2:
                ch1, ch2 = ch[:2]

            c1, c2 = roi.analysis_data[ch1]['centroid'], roi.analysis_data[ch2]['centroid']
            d = '%.2f' % distance(c1, c2)
            data.append([roi.analysis_data[ch1]['nPoints'], roi.analysis_data[ch2]['nPoints'], d, '(%.2f, %.2f)' % (c1[0], c1[1]), '(%.2f, %.2f)' % (c2[0], c2[1])])
            '''for ch in roi.analysis_data:
                others = [roi.analysis_data[d]['centroid'] for d in roi.analysis_data if d != ch]
                d = ('%.2f' % min([distance(roi.analysis_data[ch]['centroid'], o) for o in others])) if len(others) > 0 else 'NA'
                data.append([ch, roi.analysis_data[ch]['centroid'], roi.analysis_data[ch]['nPoints'], roi.analysis_data[ch]['avg_dist'], d])'''
        self.roiData.setData(data)
        self.roiData.setHorizontalHeaderLabels(['N Ch. 1', 'N Ch. 2', 'Dist.', 'Ch1 Centroid', 'Ch2 Centroid'])

    def addDock(self, f, data, **kwds):
        dock = PlotDock(os.path.basename(f), data, **kwds)
        dock.sigUpdated.connect(self.showDockData)
        self.dockarea.addDock(dock)
        dock.container().apoptose = lambda : None
        self.dockCreated.emit(dock)

    def show_console(self):
        if not hasattr(self, 'c') or not self.c.isVisible():
            self.c = ConsoleWidget()
            self.c.localNamespace.update({'self': self, 'PlotDock': PlotDock, 'dock':lambda i: [d for d in self.dockarea.docks.values() if d.isVisible()][i]})
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
        


if __name__ == '__main__':
    mw = MainWindow()
    mw.show()

    app.exec_()