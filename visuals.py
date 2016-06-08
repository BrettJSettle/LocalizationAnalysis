from vispy.scene import visuals
from vispy.scene.visuals import Text
from vispy.visuals import PolygonVisual, LinePlotVisual
from analysis import *
from PyQt4 import QtGui, QtCore
import pyqtgraph as pg
import numpy as np
import file_manager as fm
import pyqtgraph.opengl as gl

class ROIVisual(PolygonVisual):
    def __init__(self, dock, pos, color=[1, 1, 0]):
        self.dock = dock
        num = set(range(1, len(self.dock.rois)+2))
        num ^= {r.id for r in self.dock.rois}
        self.id = min(num)
        PolygonVisual.__init__(self, color=None, border_color='yellow')
        self.text = Text("%d" % self.id, color='white')
        self.text.font_size=20
        self.hover = False
        self.selected = False
        self._selected_color = color
        if np.ndim(pos) < 2:
            self.text.pos = pos
            self.points = np.array([pos],dtype=np.float32)
            self.finished = False
        else:
            self.text.pos = pos[0]
            self.points = np.array(pos[:-1], dtype=np.float32)
            self.draw_finished()
        
        self.colorDialog=QtGui.QColorDialog()
        self.colorDialog.colorSelected.connect(self.colorSelected)
        self._make_menu()

    def setId(self, num):
        self.id = num
        self.text.text = "%d" % self.id

    @staticmethod
    def importROIs(fname, parent):
        rois = []
        text = open(fname, 'r').read()
        kind=None
        pts=None
        for line in text.split('\n'):
            line = line.strip()
            if kind is None:
                kind=line
                pts=[]
            elif line=='':
                pts = np.array(pts)
                roi = MyROI(parent, pts, parent=parent.canvas.scene)
                roi.transform = parent.vb._camera._transform
                parent.rois.append(roi)
                kind=None
                pts=None
            elif kind == 'freehand':
                pts.append([int(i) for i in line.split()])

    def __repr__(self):
        s = 'freehand\n'
        s += '\n'.join(['%.1f\t%.1f' % (p[0], p[1]) for p in self.points])
        s += '\n'
        return s

    def colorSelected(self, color):
        self.border_color = (color.redF(), color.greenF(), color.blueF())
        self._selected_color = self.border_color

    def mouseIsOver(self, pos):
        self.hover = self.contains(pos)
        if self.hover:
            self.select()
        else:
            self.deselect()
        return self.hover

    def _make_menu(self):
        self.menu = QtGui.QMenu('ROI   Menu')
        self.menu.addAction(QtGui.QAction("Change Color", self.menu, triggered = self.colorDialog.show))
        self.menu.addAction(QtGui.QAction("Remove Points in ROI", self.menu, triggered = self.removeInternalPoints))
        self.menu.addAction(QtGui.QAction("Export points in ROI", self.menu, triggered = self.exportInternalPoints))
        if 'Zc' in self.dock.data.keys():
            self.menu.addAction(QtGui.QAction("Plot Points in 3D", self.menu, triggered=self.plot3D))
        self.menu.addAction(QtGui.QAction("Remove", self.menu, triggered=self.delete))

    def removeInternalPoints(self):
        ids = np.where([not self.contains(p) for p in zip(self.dock.data.Xc.values, self.dock.data.Yc.values)])[0]
        data = self.dock.data.iloc[ids.astype(int)]
        self.dock.update(data=data, autoRange=False)
        self.analyze()

    def plot3D(self):
        ids = np.where([self.contains(p[:2]) for p in zip(self.dock.data.Xc.values, self.dock.data.Yc.values)])[0]
        pos = self.dock.data.iloc[ids.astype(int)]
        colors = self.dock.getColors(pos)
        pos = np.transpose([pos.Xc.values, pos.Yc.values, pos.Zc.values])
        item = gl.GLScatterPlotItem(pos=pos, color=colors, size=4)
        widget = gl.GLViewWidget()
        widget.addItem(item)

        center = list(np.average(pos, 0))
        atX, atY, atZ = widget.cameraPosition()
        widget.pan(-atX, -atY, -atZ)
        widget.opts['distance'] = 100
        widget.opts['center'] = QtGui.QVector3D(*center)

        dock = self.dock.window().dockarea.addDock(name="ROI %d" % self.id, size=(300, 300), widget=widget, closable=True)


    def exportInternalPoints(self, writer=None):
        if writer == None or type(writer) == bool:
            writer = str(fm.getSaveFileName(filter='Excel Files (*.xls)'))
        if writer == '': 
            return
        ids = np.where([self.contains(p) for p in zip(self.dock.data.Xc.values, self.dock.data.Yc.values)])[0]
        data = self.dock.data.iloc[ids.astype(int)]
        data.to_excel(writer, 'ROI #%d' % self.id)

    def raiseContextMenu(self, pos):
        self.menu.popup(pos)

    def extend(self, pos):
        if not self.finished:
            self.points = np.array(np.vstack((self.points, pos)), dtype=np.float32)
            self.pos = self.points
        
    def select(self):
        if not self.selected:
            self.selected = True
            self.border_color = np.array([1, 0, 0], dtype=np.float32)

    def deselect(self):
        if self.selected:
            self.selected = False
            self.border_color = self._selected_color

    def analyze(self):
        ids = np.where([self.contains(p) for p in zip(self.dock.data.Xc.values, self.dock.data.Yc.values)])[0]
        self.internal_points = self.dock.data.iloc[ids.astype(int)]
        self.analysis_data = {}
        for file in np.unique([str(f) for f in self.internal_points.File]):
            self.analysis_data[file] = {'nPoints': 0, 'centroid': (0,0), 'avg_dist': 0, 'points': []}
            self.analysis_data[file]['points'] = self.internal_points[self.internal_points['File'] == file]
            pts = np.transpose([self.analysis_data[file]['points'].Xc.values, self.analysis_data[file]['points'].Yc.values])
            if len(pts) != 0:
                self.analysis_data[file]['nPoints'] = len(pts)
                self.analysis_data[file]['centroid'] = np.mean(pts, 0)
                dists = []
                for i in range(len(pts)):
                    dists.append(distance(pts[i], self.analysis_data[file]['centroid']))
                self.analysis_data[file]['avg_dist'] = np.mean(dists)
        self.dataStr = self.asStr()

        self.dock.sigUpdated.emit(self.dock)

    def asStr(self):
        s = 'ROI %s:\n' % self.id
        if not hasattr(self, 'data'):
            self.analyze()
            return self.dataStr
        fs = [i for i in self.analysis_data.keys() if i != 'nan']
        for i, f in enumerate(fs):
            s += '''\
File: %s
    Points: %d
    Centroid: (%0.2f, %0.2f)
    Avg. Dist.: %0.2f\n''' % (f, self.analysis_data[f]['nPoints'], self.analysis_data[f]['centroid'][0], self.analysis_data[f]['centroid'][1], self.analysis_data[f]['avg_dist'])

        return s
        

    def draw_finished(self):
        self.points = np.vstack((self.points, self.points[0]))
        self.pos = self.points
        self.analyze()
        self.finished = True
        self.select()

    def contains(self, pt):
        if not hasattr(self, 'path_item'):
            self.path_item = QtGui.QPainterPath()
            self.path_item.moveTo(*self.points[0])
            for i in self.points[1:]:
                self.path_item.lineTo(*i)
            self.path_item.lineTo(*self.points[0])
        return self.path_item.contains(QtCore.QPointF(*pt))

    def translate(self, dxy):
        self.points += dxy
        self.pos = self.points
        self.text.pos = self.pos[0]
        if hasattr(self, 'path_item'):
            self.path_item.translate(*dxy)

    def translate_finished(self):
        self.analyze()

    def delete(self):
        self.remove_parent(self.parent)
        if self in self.dock.rois:
            self.dock.rois.remove(self)
    
    def draw(self, tr_sys):
        if not self.finished:
            color = np.ones((len(self.points), 3)).astype(np.float32)
            lp = LinePlotVisual(data=self.points, color=color, marker_size=1)
            lp.draw(tr_sys)
        elif len(self.points) > 2:
            PolygonVisual.draw(self, tr_sys)
            self.text.draw(tr_sys)

MyROI = visuals.create_visual_node(ROIVisual)

class ClusterVisual(PolygonVisual):
    def __init__(self, points):
        PolygonVisual.__init__(self, color=None, border_color='white')
        self.points = points
        self.border_points = getBorderPoints(self.points)
        self.pos = np.array(self.border_points, dtype=np.float32)

MyCluster = visuals.create_visual_node(ClusterVisual)

class Cluster():
    def __init__(self, points):
        self.points = points
        self.centroid = np.mean(self.points, 0)
        self.averageDistance = averageDistance(self.points)

    def visual(self, dock):
        self._visual = MyCluster(self.points, parent=dock.canvas.scene)
        self._visual.transform = dock.vb._camera._transform

    def remove(self):
        self._visual.remove_parent(self._visual.parent)