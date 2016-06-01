import numpy as np
from scipy.spatial import ConvexHull

def distance(ptA, ptB):
    return np.linalg.norm(np.subtract(ptA[:2], ptB[:2]))

def getBorderPoints(points):
    if len(points) > 2:
        ch = ConvexHull(points)
        outerwalls = order_walls(ch.simplices.tolist())
        return [points[i] for i in outerwalls]
    return []

def nearestDistances(points, points2=[]):
    if len(points2) == 0:
        points2 = points
    dists = []
    for p in points:
        dists.append(np.inf)
        for p2 in points2:
            dists[-1] = min(dists[-1], distance(p, p2))
            
    return dists

def order_walls(walls):
    new_wall = walls.pop(0)
    while walls:
        add = [wall for wall in walls if new_wall[-1] in wall][0]
        walls.remove(add)
        add.remove(new_wall[-1])
        new_wall.extend(add)
    return new_wall

def averageDistance(points):
    dists = []
    for i in range(len(points)):
        for j in range(i+1, len(points)):
            dists.append(np.linalg.norm(points[i] - points[j]))
    return sum(dists) / len(dists)
