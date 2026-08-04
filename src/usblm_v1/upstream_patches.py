"""Bundled fixes for two upstream MeerK40t bugs.

These are NOT V1-specific - they are applied because the bundled
meerk40t 0.9.9100 + numpy 2.5.1 stack hits them. Remove when upstream
fixes land: Geomstr.hull numpy-2 rewrite, Elemental.remove_nodes
(reported upstream as meerk40t issue #3253).
"""
from meerk40t.core.geomstr import Geomstr


def _convex_hull_points(ipts):
    """Convex hull (Andrew's monotone chain) on interpolated points.
    numpy-2-safe replacement for meerk40t's quickhull, which uses
    np.cross on 2D arrays (numpy 1.x only)."""
    pts = sorted(set((p.real, p.imag) for p in ipts if p is not None))
    if len(pts) < 3:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _geomstr_hull(cls, geom, distance=50):
    """Replacement for Geomstr.hull - numpy 2 broke meerk40t's quickhull
    (np.cross on 2D arrays). This version computes the same hull with a
    numpy-2-safe monotone chain, so EVERY call site works: Live Hull,
    Trace Hull, and the console hull command."""
    ipts = list(geom.as_equal_interpolated_points(distance=distance))
    pts = _convex_hull_points(ipts)
    if len(pts) < 3:
        return cls()
    pts = [complex(x, y) for x, y in pts]
    pts.append(pts[0])
    return Geomstr.lines(*pts)


def _remove_nodes(self, node_list):
    """Replacement for Elemental.remove_nodes. Upstream MeerK40t bug
    (affects all users, not V1-specific): MeerK40t marks an element's
    reference nodes for deletion but never removes them (they live under
    the operations branch, not self.elems()). Deleted elements therefore
    stay in the operation's job - the 'shadow element' that keeps being
    simulated/engraved after deletion. This version removes the marked
    references too. (Reported upstream as meerk40t issue #3253.)"""
    self.set_start_time("remove_nodes")
    to_be_deleted = 0
    fastmode = False
    for node in node_list:
        for n in node.flat():
            n._mark_delete = True
            to_be_deleted += 1
            for ref in list(n._references):
                ref._mark_delete = True
                to_be_deleted += 1
    fastmode = to_be_deleted >= 100
    with self._node_lock:
        for n in reversed(list(self.elems())):
            if not hasattr(n, "_mark_delete"):
                continue
            if n.type in ("root", "branch elems", "branch reg", "branch ops"):
                continue
            n.remove_node(children=False, references=False, fast=fastmode)
        for op in list(self.ops()):
            for ref in list(op.flat()):
                if getattr(ref, "_mark_delete", False):
                    ref.remove_node(references=False, fast=fastmode)
    self.set_end_time("remove_nodes")
    if fastmode:
        self.signal("rebuild_tree", "all")
    else:
        self.signal("element_removed")


def apply_upstream_patches():
    """Idempotent; applied once at package import."""
    from meerk40t.core.elements.elements import Elemental

    if getattr(Geomstr.hull, "__func__", None) is not _geomstr_hull:
        Geomstr.hull = classmethod(_geomstr_hull)
    Elemental.remove_nodes = _remove_nodes
