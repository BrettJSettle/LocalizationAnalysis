from vispy.scene import visuals
from vispy.scene.visuals import Text
from vispy.visuals import PolygonVisual, LinePlotVisual
from analysis import *
from PyQt4 import QtGui, QtCore
import pyqtgraph as pg

class ROIVisual(PolygonVisual):
    def __init__(self, dock, pos, color=[1, 1, 0]):
        self.dock = dock
        num = set(range(1, len(self.dock.rois)+2))
        num ^= {r.id for r in self.dock.rois}
        self.id = min(num)
        PolygonVisual.__init__(self, color=None, border_color='yellow')
        self.text = Text("%d" % self.id, color='white')
        self.text.font_size=20
        self.text.pos = pos
        self.points = np.array([pos],dtype=np.float32)
        self.finished = False
        self.hover = False
        self.selected = False
        self._selected_color = color
        self.colorDialog=QtGui.QColorDialog()
        self.colorDialog.colorSelected.connect(self.colorSelected)
        self._make_menu()

    def setId(self, num):
        self.id = num
        self.text.text = "%d" % self.id

    @staticmethod
    def importROIs(fname):
        rois = []
        text = open(fname, 'r').read()
        kind=None
        pts=None
        for line in text.split('\n'):
            if kind is None:
                kind=line
                pts=[]
            elif line=='':
                rois.append(ROIVisual(1, pts[0]))
                for p in pts[1:]:
                    rois[-1].extend(p)
                rois[-1].draw_finished()
                kind=None
                pts=None
            elif kind == 'freehand':
                pts.append(tuple(int(i) for i in line.split()))
        return rois

    def __repr__(self):
        s = 'freehand\n'
        s += '\n'.join(['%d\t%d' % (p[0], p[1]) for p in self.points])
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
        self.menu = QtGui.QMenu('ROI Menu')
        self.menu.addAction(QtGui.QAction("Change Color", self.menu, triggered = self.colorDialog.show))
        self.menu.addAction(QtGui.QAction("Remove Points in ROI", self.menu, triggered = self.removeInternalPoints))
        self.menu.addAction(QtGui.QAction("Export points in ROI", self.menu, triggered = self.exportInternalPoints))
        self.menu.addAction(QtGui.QAction("Remove", self.menu, triggered=self.delete))

    def removeInternalPoints(self):
        pts = [not self.contains(p) for p in zip(self.dock.data.Xc.values, self.dock.data.Yc.values)]
        data = self.dock.data[pts]
        self.dock.setData(data)

    def exportInternalPoints(self, writer=None):
        if writer == None or type(writer) == bool:
            writer = str(fm.getOpenFileName())
        pts = [self.contains(p) for p in zip(self.dock.data.Xc.values, self.dock.data.Yc.values)]
        data = self.dock.data[pts]
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
        pts = np.transpose([self.dock.data['Xc'], self.dock.data['Yc']])
        self.internal_points = [pt for pt in pts if self.contains(pg.Point(*pt))]
        if len(self.internal_points) == 0:
            self.centroid = [np.nan, np.nan]
            self.avg_distance = np.nan
        else:
            self.centroid = np.mean(self.internal_points, 0)
            dists = []
            for i in range(len(self.internal_points)):
                dists.append(np.linalg.norm(np.subtract(self.internal_points[i], self.centroid)))
            #   dists.extend([np.linalg.norm(np.subtract(self.internal_points[i], other)) for other in self.internal_points[i+1:]])
            self.avg_distance = np.mean(dists)
        self.dock.sigUpdated.emit(self.dock)
        
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

    def dataStr(self):
        return 'ROI %s:\n  Points: %d\n  Centroid: (%0.2f, %0.2f)\n  Avg. Dist.: %0.2f\n' % (self.id, len(self.internal_points), self.centroid[0], self.centroid[1], self.avg_distance)

MyROI = visuals.create_visual_node(ROIVisual)

class ClusterVisual(PolygonVisual):
    def __init__(self, active_points):
        PolygonVisual.__init__(self, color=None, border_color='white')
        self.points = active_points
        pos = [p for p in active_points]
        self.centroid = np.mean(pos, 0)
        #self.box_area = boxArea(pos)#concaveArea([p.pos for p in active_points])
        #self.grid_area = gridArea(pos)
        self.averageDistance = averageDistance(pos)
        #self.density = len(self.points) / self.box_area
        self.border_points = getBorderPoints(pos)
        self.pos = np.array(self.border_points, dtype=np.float32)

MyCluster = visuals.create_visual_node(ClusterVisual)