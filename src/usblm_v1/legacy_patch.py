"""Temporary: the legacy class swap used by the interim v1_meerk40t.py
shim. Deleted once the profile registers itself as a device (Phase 2).
"""
import meerk40t.balormk.controller as mk_ctrl
import meerk40t.balormk.driver as mk_driver
import meerk40t.balormk.livelightjob as mk_light
import meerk40t.balormk.usb_connection as mk_usb

from .controller import V1Controller
from .lightjob import V1LiveLightJob
from .transport import V1Connection


def patch():
    """Swap the balormk classes for the V1 versions (all import sites)."""
    mk_usb.USBConnection = V1Connection
    mk_ctrl.USBConnection = V1Connection
    mk_ctrl.GalvoController = V1Controller
    mk_driver.GalvoController = V1Controller
    mk_light.LiveLightJob.trace_redlight = V1LiveLightJob.trace_redlight
    mk_light.LiveLightJob.update_hull = V1LiveLightJob.update_hull
    mk_light.LiveLightJob.setup_listen = V1LiveLightJob.setup_listen
    # super() cannot be used here: the assigned function runs on plain
    # LiveLightJob instances, which are not V1LiveLightJob subtypes.
    _orig_copy = mk_light.LiveLightJob.copy_for_reinsertion

    def _inert_copy(self):
        c = _orig_copy(self)
        c.stopped = True
        return c

    mk_light.LiveLightJob.copy_for_reinsertion = _inert_copy
