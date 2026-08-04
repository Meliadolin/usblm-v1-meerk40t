"""
USBLM-V1 Driver

Same driver as balormk's BalorDriver with the V1 controller in place of
the V2/V4 GalvoController. Everything else - spooler integration, plot
planner, queue bookkeeping, pedal polling - is inherited unchanged.

The only reason the __init__ is copied instead of calling super() is that
BalorDriver.__init__ hard-codes `GalvoController(service, ...)` at
balormk/driver.py:66.
"""

from meerk40t.balormk.driver import BalorDriver
from meerk40t.core.plotplanner import PlotPlanner

from usblm_v1.controller import V1Controller


class V1Driver(BalorDriver):
    """USBLM-V1 device driver (BalorDriver with the V1 controller)."""

    def __init__(self, service, force_mock=False):
        self.service = service
        self.native_x = 0x8000
        self.native_y = 0x8000
        self.name = str(self.service)

        self.connection = V1Controller(service, force_mock=force_mock)

        self.service.add_service_delegate(self.connection)
        self.paused = False

        self.is_relative = False
        self.laser = False

        self._shutdown = False

        self.queue = list()
        self._queue_current = 0
        self._queue_total = 0
        self.plot_planner = PlotPlanner(
            dict(),
            single=True,
            ppi=False,
            shift=False,
            group=True,
            require_uniform_movement=False,
        )
        self.value_penbox = None
        self.plot_planner.settings_then_jog = True
        self._aborting = False
        self._list_bits = None
        self.service.setting(bool, "signal_updates", True)

        # Footpedal polling thread (uses controller's _usb_lock for synchronization)
        self._pedal_thread = None
        self._pedal_thread_running = False
        self.last_foot_state = None
        self._pedal_poll_interval = 0.5  # 0.5 seconds

    def __repr__(self):
        return f"V1Driver({self.name})"
