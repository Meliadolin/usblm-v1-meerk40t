"""V1 live-light job: the ENTIRE path is built as one buffered list and
executed once, then the board is allowed to finish. balormk's version
streams records mid-execution - the V1 board overwrites its buffer, so
nothing would ever run.
"""
from math import isinf

import numpy as np

from meerk40t.balormk.livelightjob import LiveLightJob
from meerk40t.core.geomstr import Geomstr
from meerk40t.core.node.node import Node


class V1LiveLightJob(LiveLightJob):
    def trace_redlight(self, con):
        """V1 live-trace pass: build the ENTIRE path as one buffered list,
        then execute it once and wait for the board to finish."""
        con.light_mode()
        delay_dark = self.service.redlight_delay_dark
        delay_between = self.service.redlight_delay_light
        move = True
        first = True
        first_x, first_y = None, None
        for i, e in enumerate(self.points):
            if self.stopped or self.changed:
                return
            if e is None:
                move = True
                continue
            x, y = e.real, e.imag
            if np.isnan(x) or np.isnan(y):
                move = True
                continue
            x = int(x)
            y = int(y)
            if x < 0 or x > 0xFFFF or y < 0 or y > 0xFFFF:
                if self.bounded:
                    continue
                x = max(min(x, 0xFFFF), 0)
                y = max(min(y, 0xFFFF), 0)
            if first:
                first_x, first_y = x, y
                first = False
            if move:
                con.dark(x, y, long=delay_dark, short=delay_dark)
                move = False
                continue
            con.light(x, y, long=delay_between, short=delay_between)
        if first_x is not None and first_y is not None:
            con.dark(first_x, first_y, long=delay_dark, short=delay_dark)
        con.light_off()
        con.write_port()
        con.v1_execute_light_list()

    def setup_listen(self, start):
        """Live-light listeners including element lifecycle signals.
        Upstream balormk gap (not V1-specific): balormk only listens to
        emphasis/edit signals - deleting an element fires 'element_removed'
        / 'tree_changed' which the light job missed, so deleted shapes kept
        being traced (stale simulation)."""
        if not self.listen:
            return
        methods = [
            "emphasized",
            "modified_by_tool",
            "updating",
            "view;realized",
            "update_group_labels",
            "element_property_reload",
            "element_removed",
            "tree_changed",
        ]
        for method in methods:
            if start:
                self.service.listen(method, self.on_emphasis_changed)
            else:
                self.service.unlisten(method, self.on_emphasis_changed)

    def copy_for_reinsertion(self):
        """V1: never re-run the light job after a real job. balormk stops
        the running light job when a real job starts and - with
        restart_light_jobs enabled - reinserts a copy, which then re-traces
        the selection (looks like an unprovoked re-run) and its stop can
        leave the board paused. The copy is inert instead."""
        c = super().copy_for_reinsertion()
        c.stopped = True
        return c

    def update_hull(self):
        """Hull tracing with numpy 2.x: meerk40t's quickhull implementation
        uses np.cross on 2D arrays (numpy 1.x only) and throws on numpy 2.
        Fall back to the selection's bounds box when the hull computation
        fails, so hull modes never crash."""

        def create_hull_geometry(elemlist):
            geometry = Geomstr()
            for node in elemlist:
                try:
                    e = None
                    if hasattr(node, "convex_hull"):
                        e = node.convex_hull()
                    if e is None:
                        e = node.as_geometry()
                except AttributeError:
                    continue
                geometry.append(e)
            if geometry.index == 0:
                return None
            try:
                return Geomstr.hull(geometry, distance=500)
            except Exception:
                bounds = Node.union_bounds(elemlist)
                if bounds is None or isinf(bounds[0]):
                    return None
                xmin, ymin, xmax, ymax = bounds
                return Geomstr.lines(
                    (xmin, ymin),
                    (xmax, ymin),
                    (xmax, ymax),
                    (xmin, ymax),
                    (xmin, ymin),
                )

        self._update_common(create_hull_geometry, "hull")
