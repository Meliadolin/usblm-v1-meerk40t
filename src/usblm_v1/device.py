"""
USBLM-V1 Galvo Device

Defines how the V1 device interacts with the scene, and accepts data via the
spooler. Mirrors MeerK40t's BalorDevice (same command family, later board
generation) minus the choices that do not apply to the V1: there is no
source selection (the V1 board is a fiber driver board - the controller
forces source "fiber"), no correction file (the board refuses 0x0015
payloads) and no MOPA pulse width presets.
"""

from usblm_v1.driver import V1Driver
from meerk40t.core.spoolers import Spooler
from meerk40t.core.units import Angle, Length
from meerk40t.core.view import View
from meerk40t.device.devicechoices import get_effect_choices, get_operation_choices
from meerk40t.device.mixins import Status
from meerk40t.kernel import Service, signal_listener


class V1Device(Service, Status):
    """
    The V1Device is a MeerK40t service for the device type. It should be the
    main method of interacting with the rest of meerk40t. It defines how the
    scene should look and contains a spooler which meerk40t will give jobs
    to. This class additionally defines commands which exist as console
    commands while this service is activated.
    """

    def __init__(self, kernel, path, *args, choices=None, **kwargs):
        Service.__init__(self, kernel, path)
        Status.__init__(self)
        self.name = "usblmv1"
        self.extension = "lmc"
        self.job = None
        if choices is not None:
            for c in choices:
                attr = c.get("attr")
                default = c.get("default")
                if attr is not None and default is not None:
                    setattr(self, attr, default)

        _ = kernel.translation
        self.register("frequency", (0, 1000))
        self.register(
            "format/op cut",
            "{danger}{defop}{enabled}{pass}{element_type} {speed}mm/s @{power} {frequency}kHz {colcode} {opstop}",
        )
        self.register(
            "format/op engrave",
            "{danger}{defop}{enabled}{pass}{element_type} {speed}mm/s @{power} {frequency}kHz {colcode} {opstop}",
        )
        self.register(
            "format/op hatch",
            "{danger}{defop}{enabled}{penpass}{pass}{element_type} {speed}mm/s @{power} {frequency}kHz {colcode} {opstop}",
        )
        self.register(
            "format/op raster",
            "{danger}{defop}{enabled}{pass}{element_type}{direction}{speed}mm/s @{power} {frequency}kHz {colcode} {opstop}",
        )
        self.register(
            "format/op image",
            "{danger}{defop}{enabled}{penvalue}{pass}{element_type}{direction}{speed}mm/s @{power} {frequency}kHz {colcode}",
        )
        self.register(
            "format/op dots",
            "{danger}{defop}{enabled}{pass}{element_type} {dwell_time}ms dwell {frequency}kHz {colcode} {opstop}",
        )
        self.register("format/util console", "{enabled}{command}")
        # This device prefers to display power level in percent
        self.setting(bool, "use_percent_for_power_display", True)
        self.setting(bool, "use_mm_min_for_speed_display", False)
        # Tuple contains 4 value pairs: Speed Low, Speed High, Power Low, Power High, each with enabled, value
        self.setting(
            list, "dangerlevel_op_cut", (False, 0, False, 0, False, 0, False, 0)
        )
        self.setting(
            list, "dangerlevel_op_engrave", (False, 0, False, 0, False, 0, False, 0)
        )
        self.setting(
            list, "dangerlevel_op_hatch", (False, 0, False, 0, False, 0, False, 0)
        )
        self.setting(
            list, "dangerlevel_op_raster", (False, 0, False, 0, False, 0, False, 0)
        )
        self.setting(
            list, "dangerlevel_op_image", (False, 0, False, 0, False, 0, False, 0)
        )
        self.setting(
            list, "dangerlevel_op_dots", (False, 0, False, 0, False, 0, False, 0)
        )
        # Not exposed as choices (the V1 has no MOPA pulse width presets),
        # but operation defaults resolve them.
        self.setting(bool, "pulse_width_enabled", False)
        self.setting(int, "default_pulse_width", 4)
        choices = [
            {
                "attr": "label",
                "object": self,
                "default": "USBLM-V1",
                "type": str,
                "label": _("Label"),
                "tip": _("What is this device called."),
                "section": "_00_General",
                "priority": "10",
                "signals": "device;renamed",
            },
            {
                "attr": "lens_size",
                "object": self,
                "default": "110mm",
                "type": Length,
                "label": _("Width"),
                "tip": _("Lens Size"),
                "section": "_00_General",
                "subsection": "_00_",
                "priority": "20",
                "nonzero": True,
                # intentionally not bed_size
            },
            {
                "attr": "laserspot",
                "object": self,
                "default": "0.3mm",
                "type": Length,
                "label": _("Laserspot"),
                "tip": _("Laser spot size"),
                "section": "_00_General",
                "subsection": "_00_",
                "priority": "20",
                "nonzero": True,
            },
            {
                "attr": "flip_x",
                "object": self,
                "default": False,
                "type": bool,
                "label": _("Flip X"),
                "tip": _("Flip the X axis for the device"),
                "section": "_10_Parameters",
                "subsection": "_10_Axis corrections",
            },
            {
                "attr": "flip_y",
                "object": self,
                "default": True,
                "type": bool,
                "label": _("Flip Y"),
                "tip": _("Flip the Y axis for the device"),
                "section": "_10_Parameters",
                "subsection": "_10_Axis corrections",
            },
            {
                "attr": "swap_xy",
                "object": self,
                "default": True,
                "type": bool,
                "label": _("Swap XY"),
                "tip": _("Swap the X and Y axis for the device"),
                "section": "_10_Parameters",
                "subsection": "_10_Axis corrections",
            },
            {
                "attr": "rotate",
                "object": self,
                "default": 0,
                "type": int,
                "style": "combo",
                "trailer": "°",
                "choices": [
                    0,
                    90,
                    180,
                    270,
                ],
                "label": _("Rotate View"),
                "tip": _("Rotate the device field"),
                "section": "_10_Parameters",
                "subsection": "_10_Axis corrections",
            },
            {
                "attr": "user_margin_x",
                "object": self,
                "default": "0",
                "type": str,
                "label": _("X-Margin"),
                "tip": _(
                    "Margin for the X-axis. This will be a kind of unused space at the left side."
                ),
                "section": "_10_Parameters",
                "subsection": "_30_User Offset",
                "ignore": True,  # Does not work yet, so don't show
            },
            {
                "attr": "user_margin_y",
                "object": self,
                "default": "0",
                "type": str,
                "label": _("Y-Margin"),
                "tip": _(
                    "Margin for the Y-axis. This will be a kind of unused space at the top."
                ),
                "section": "_10_Parameters",
                "subsection": "_30_User Offset",
                "ignore": True,  # Does not work yet, so don't show
            },
            {
                "attr": "interp",
                "object": self,
                "default": 5,
                "type": int,
                "label": _("Curve Interpolation"),
                "section": "_10_Parameters",
                "tip": _("Number of curve interpolation points"),
            },
            {
                "attr": "mock",
                "object": self,
                "default": False,
                "type": bool,
                "label": _("Run mock-usb backend"),
                "tip": _(
                    "This starts connects to fake software laser rather than real one for debugging."
                ),
                "section": "_00_General",
                "priority": "30",
            },
            {
                "attr": "machine_index",
                "object": self,
                "default": 0,
                "type": int,
                "label": _("Machine index to select"),
                "tip": _(
                    "Which machine should we connect to? -- Leave at 0 if you have 1 machine."
                ),
                "section": "_00_General",
                "subsection": "_10_Device Selection",
            },
            {
                "attr": "serial_enable",
                "object": self,
                "default": False,
                "type": bool,
                "label": _("Check serial no"),
                "tip": _("Does the machine need to have a specific serial number?"),
                "section": "_00_General",
                "subsection": "_10_Device Selection",
            },
            {
                "attr": "serial",
                "object": self,
                "default": "",
                "type": str,
                "tip": _("Does the machine need to have a specific serial number?"),
                "label": "",
                "section": "_00_General",
                "subsection": "_10_Device Selection",
                "conditional": (self, "serial_enable"),
            },
            {
                "attr": "footpedal_pin",
                "object": self,
                "default": 15,
                "type": int,
                "label": _("Footpedal"),
                "tip": _("What pin is your foot pedal hooked to on the GPIO"),
                "section": "_10_Parameters",
                "subsection": "_30_Pin-Index",
                "signals": "balorpin",
            },
            {
                "attr": "light_pin",
                "object": self,
                "default": 8,
                "type": int,
                "label": _("Redlight laser"),
                "tip": _("What pin is your redlight hooked to on the GPIO"),
                "section": "_10_Parameters",
                "subsection": "_30_Pin-Index",
                "signals": "balorpin",
            },
            {
                "attr": "pedal_mode",
                "object": self,
                "default": "ignore",
                "type": str,
                "style": "combo",
                "choices": [
                    "ignore",
                    "pause_resume_toggle",
                    "pause_while_pressed",
                    "stop",
                ],
                "display": [
                    _("Ignore (only act on input operation)"),
                    _("Pause/Resume Job on Press"),
                    _("Pause While Pressed"),
                    _("Stop Job"),
                ],
                "label": _("Pedal action"),
                "tip": _(
                    "What action should be taken when the foot pedal is pressed during a job execution?"
                ),
                "section": "_10_Parameters",
                "subsection": "_31_Footpedal",
                "signals": "balorpin",
            },
            {
                "attr": "pedal_active_low",
                "object": self,
                "default": True,
                "type": bool,
                "label": _("Active on low signal"),
                "tip": _(
                    "Should the pedal be considered pressed when the signal is low?"
                ),
                "section": "_10_Parameters",
                "subsection": "_31_Footpedal",
                "conditional": (
                    self,
                    "pedal_mode",
                    ("pause_resume_toggle", "pause_while_pressed", "stop"),
                ),
                "signals": "balorpin",
            },
            {
                "attr": "signal_updates",
                "object": self,
                "default": True,
                "type": bool,
                "label": _("Device Position"),
                "tip": _(
                    "Do you want to see some indicator about the current device position?"
                ),
                "section": "_95_" + _("Screen updates"),
                "signals": "restart",
            },
            {
                "attr": "device_coolant",
                "object": self,
                "default": "",
                "type": str,
                "style": "option",
                "label": _("Coolant"),
                "tip": _(
                    "Does this device has a method to turn on / off a coolant associated to it?"
                ),
                "section": "_99_" + _("Coolant Support"),
                "dynamic": self.cool_helper,
                "signals": "coolant_changed",
            },
        ]
        # Section names must match the lookups in the reused balormk panels
        # (balorconfig.py options tuple) - the Configuration window renders
        # whatever choices are registered under these names.
        self.register_choices("balor", choices)

        def _use_percent_for_power():
            return getattr(self, "use_percent_for_power_display", True)

        def _use_minute_for_speed():
            return getattr(self, "use_mm_min_for_speed_display", False)

        self.register_choices("balor-effects", get_effect_choices(self))
        self.register_choices(
            "balor-defaults",
            get_operation_choices(
                self,
                default_cut_speed=150,
                default_engrave_speed=250,
                default_raster_speed=500,
            ),
        )

        choices = [
            {
                "attr": "redlight_speed",
                "object": self,
                "default": "3000",
                "type": int,
                "label": _("Redlight travel speed"),
                "tip": _("Speed of the galvo when using the red laser."),
            },
            {
                "attr": "redlight_delay_dark",
                "object": self,
                "default": 1,
                "type": int,
                "trailer": "µs",
                "label": _("Dark"),
                "tip": _("Delay for dark movement."),
                "subsection": "Delays",
            },
            {
                "attr": "redlight_delay_light",
                "object": self,
                "default": 1,
                "type": int,
                "trailer": "µs",
                "label": _("Light"),
                "tip": _("Delay for light movement."),
                "subsection": "Delays",
            },
            {
                "attr": "redlight_offset_x",
                "object": self,
                "default": "0mm",
                "type": Length,
                "label": _("X-Offset"),
                "tip": _("Offset the redlight positions by this amount in x"),
                "subsection": "Redlight-Offset",
            },
            {
                "attr": "redlight_offset_y",
                "object": self,
                "default": "0mm",
                "type": Length,
                "label": _("Y-Offset"),
                "tip": _("Offset the redlight positions by this amount in y"),
                "subsection": "Redlight-Offset",
            },
            {
                "attr": "redlight_angle",
                "object": self,
                "default": "0deg",
                "type": Angle,
                "label": _("Angle Offset"),
                "tip": _(
                    "Offset the redlight positions by this angle, curving around center"
                ),
                "subsection": "Redlight-Offset",
            },
            {
                "attr": "redlight_preferred",
                "object": self,
                "default": False,
                "type": bool,
                "label": _("Prefer redlight on"),
                "tip": _(
                    "Redlight preference will turn toggleable redlights on after a job completes."
                ),
                "priority": "0",
            },
            {
                "attr": "restart_light_jobs",
                "object": self,
                "default": False,
                "type": bool,
                "label": _("Restart light jobs"),
                "tip": _(
                    "If enabled, light jobs will be restarted automatically after a job completes."
                ),
                "priority": "0",
                "signals": "restart",
            },
        ]
        self.register_choices("balor-redlight", choices)

        choices = [
            {
                "attr": "default_power",
                "object": self,
                "default": 500.0,
                "type": float,
                "style": "power",
                "percent": _use_percent_for_power,
                "label": _("Power"),
                "subsection": "_10_Cut/Engrave",
                "tip": _("What power level do we cut at?")
                + "\n"
                + _(
                    "This is global setting that will be overruled by operation settings."
                ),
            },
            {
                "attr": "default_speed",
                "object": self,
                "default": 100.0,
                "type": float,
                "style": "speed",
                "perminute": _use_minute_for_speed,
                "label": _("Speed"),
                "subsection": "_10_Cut/Engrave",
                "tip": _("How fast do we cut?")
                + "\n"
                + _(
                    "This is global setting that will be overruled by operation settings."
                ),
            },
            {
                "attr": "default_frequency",
                "object": self,
                "default": 30.0,
                "type": float,
                "trailer": "kHz",
                "label": _("Q Switch Frequency"),
                "subsection": "_50_Miscellaneous",
                "tip": _("QSwitch Frequency value"),
            },
            {
                "attr": "default_fpk",
                "object": self,
                "default": 10.0,
                "type": float,
                "trailer": "%",
                "label": _("First Pulse Killer"),
                "subsection": "_50_Miscellaneous",
                "tip": _("Percent of First Pulse Killer"),
            },
            {
                "attr": "default_rapid_speed",
                "object": self,
                "default": 2000.0,
                "type": float,
                "label": _("Speed"),
                "style": "speed",
                "perminute": _use_minute_for_speed,
                "subsection": "_30_Travel",
                "tip": _("How fast do we travel when not cutting?"),
            },
        ]
        self.register_choices("balor-global", choices)

        choices = [
            {
                "attr": "delay_laser_on",
                "object": self,
                "default": 100.0,
                "type": float,
                "label": _("Laser On"),
                "trailer": "µs",
                "tip": _(
                    "Start delay (Start TC) at the beginning of each mark command"
                ),
                "section": "_10_General",
                "subsection": "Delays",
                "priority": "00",
            },
            {
                "attr": "delay_laser_off",
                "object": self,
                "default": 100.0,
                "type": float,
                "label": _("Laser Off"),
                "trailer": "µs",
                "tip": _(
                    "The delay time of the laser shutting down after marking finished"
                ),
                "section": "_10_General",
                "subsection": "Delays",
                "priority": "10",
            },
            {
                "attr": "delay_polygon",
                "object": self,
                "default": 100.0,
                "type": float,
                "label": _("Polygon Delay"),
                "trailer": "µs",
                "lower": 0,
                "upper": 655350,
                "tip": _("Delay amount between different points in the path travel."),
                "section": "_10_General",
                "subsection": "Delays",
                "priority": "30",
            },
            {
                "attr": "delay_end",
                "object": self,
                "default": 300.0,
                "type": float,
                "label": _("End Delay"),
                "trailer": "µs",
                "tip": _("Delay amount for the end TC"),
                "section": "_10_General",
                "subsection": "Delays",
                "priority": "20",
            },
            {
                "attr": "delay_jump_long",
                "object": self,
                "default": 200.0,
                "type": float,
                "label": _("Long jump delay"),
                "trailer": "µs",
                "tip": _("Delay for a long jump distance"),
                "section": "_10_General",
                "subsection": "Jump-Settings",
            },
            {
                "attr": "delay_jump_short",
                "object": self,
                "default": 8,
                "type": float,
                "label": _("Short jump delay"),
                "trailer": "µs",
                "tip": _("Delay for a short jump distance"),
                "section": "_10_General",
                "subsection": "Jump-Settings",
            },
            {
                "attr": "delay_distance_long",
                "object": self,
                "default": "10mm",
                "type": Length,
                "label": _("Long jump distance"),
                "tip": _("Distance divide between long and short jump distances"),
                "section": "_10_General",
                "subsection": "Jump-Settings",
            },
            {
                "attr": "delay_openmo",
                "object": self,
                "default": 8.0,
                "type": float,
                "label": _("Open MO delay"),
                "trailer": "ms",
                "tip": _("OpenMO delay in ms"),
                "section": "_90_Other",
            },
        ]
        self.register_choices("balor-global-timing", choices)

        choices = [
            {
                "attr": "first_pulse_killer",
                "object": self,
                "default": 200,
                "type": int,
                "label": _("First Pulse Killer"),
                "trailer": "µs",
                "tip": _(
                    "First Pulse Killer (F.P.K): the lasting time for the first pulse suppress"
                ),
                "section": "First Pulse Killer",
            },
            {
                "attr": "pwm_half_period",
                "object": self,
                "default": 125,
                "type": int,
                "label": _("PWM Half Period"),
                "tip": _("Pulse Period: the frequency of the preionization signal"),
                "subsection": "Pulse-Width-Modulation",
            },
            {
                "attr": "pwm_pulse_width",
                "object": self,
                "default": 125,
                "type": int,
                "label": _("PWM Pulse Width"),
                "tip": _("Pulse Width: the pulse width of the preionization signal"),
                "subsection": "Pulse-Width-Modulation",
            },
            {
                "attr": "standby_param_1",
                "object": self,
                "default": 2000,
                "type": int,
                "label": _("Parameter 1"),
                "subsection": "Standby-Parameter",
            },
            {
                "attr": "standby_param_2",
                "object": self,
                "default": 20,
                "type": int,
                "label": _("Parameter 2"),
                "subsection": "Standby-Parameter",
            },
            {
                "attr": "timing_mode",
                "object": self,
                "default": 1,
                "type": int,
                "label": _("Timing Mode"),
                "subsection": "Modes",
            },
            {
                "attr": "delay_mode",
                "object": self,
                "default": 1,
                "type": int,
                "label": _("Delay Mode"),
                "subsection": "Modes",
            },
            {
                "attr": "laser_mode",
                "object": self,
                "default": 1,
                "type": int,
                "label": _("Laser Mode"),
                "subsection": "Modes",
            },
            {
                "attr": "control_mode",
                "object": self,
                "default": 0,
                "type": int,
                "label": _("Control Mode"),
                "subsection": "Modes",
            },
            {
                "attr": "fpk2_p1",
                "object": self,
                "default": 0xFFB,
                "type": int,
                "label": _("Max Voltage"),
                "trailer": "V",
                "section": "First Pulse Killer",
                "subsection": "Parameters",
            },
            {
                "attr": "fpk2_p2",
                "object": self,
                "default": 1,
                "type": int,
                "label": _("Min Voltage"),
                "trailer": "V",
                "section": "First Pulse Killer",
                "subsection": "Parameters",
            },
            {
                "attr": "fpk2_p3",
                "object": self,
                "default": 409,
                "type": int,
                "label": _("T1"),
                "trailer": "µs",
                "section": "First Pulse Killer",
                "subsection": "Parameters",
            },
            {
                "attr": "fpk2_p4",
                "object": self,
                "default": 100,
                "type": int,
                "label": _("T2"),
                "trailer": "µs",
                "section": "First Pulse Killer",
                "subsection": "Parameters",
            },
            {
                "attr": "fly_res_p1",
                "object": self,
                "default": 0,
                "type": int,
                "label": _("Param 1"),
                "subsection": "Fly Resolution",
            },
            {
                "attr": "fly_res_p2",
                "object": self,
                "default": 99,
                "type": int,
                "label": _("Param 2"),
                "subsection": "Fly Resolution",
            },
            {
                "attr": "fly_res_p3",
                "object": self,
                "default": 1000,
                "type": int,
                "label": _("Param 3"),
                "subsection": "Fly Resolution",
            },
            {
                "attr": "fly_res_p4",
                "object": self,
                "default": 25,
                "type": int,
                "label": _("Param 4"),
                "subsection": "Fly Resolution",
            },
            {
                "attr": "input_passes_required",
                "object": self,
                "default": 3,
                "type": int,
                "label": _("Input Signal Hold"),
                "tip": _(
                    "How long does the input operation need to hold for to count as a pass"
                ),
            },
            {
                "attr": "input_operation_hardware",
                "object": self,
                "default": False,
                "type": bool,
                "label": _("Input Operation Hardware"),
                "tip": _("Use hardware based input operation command"),
            },
        ]
        self.register_choices("balor-extra", choices)
        self.kernel.root.coolant.claim_coolant(self, self.device_coolant)

        self.state = 0

        unit_size = float(Length(self.lens_size))
        galvo_range = 0xFFFF
        units_per_galvo = unit_size / galvo_range
        self.view = View(
            self.lens_size,
            self.lens_size,
            native_scale_x=units_per_galvo,
            native_scale_y=units_per_galvo,
        )
        self.realize()

        self.spooler = Spooler(self)
        if self.restart_light_jobs:
            self.spooler.reinsert_stopped_priority_jobs = True
        self.driver = V1Driver(self)
        self.spooler.driver = self.driver

        self.add_service_delegate(self.spooler)

        self.viewbuffer = ""
        self._simulate = False
        self.laser_status = "idle"

    @property
    def safe_label(self):
        """
        Provides a safe label without spaces or / which could cause issues when used in timer or other names.
        @return:
        """
        if not hasattr(self, "label"):
            return self.name
        name = self.label.replace(" ", "-")
        return name.replace("/", "-")

    @property
    def supports_pwm(self):
        """
        Returns whether this device supports PWM.
        """
        return True

    def service_attach(self, *args, **kwargs):
        if hasattr(self.driver, "service_attach"):
            self.driver.service_attach()
        self.realize()

    def service_detach(self, *args, **kwargs):
        if hasattr(self.driver, "service_detach"):
            self.driver.service_detach()

    @signal_listener("lens_size")
    @signal_listener("rotate")
    @signal_listener("flip_x")
    @signal_listener("flip_y")
    @signal_listener("swap_xy")
    @signal_listener("user_margin_x")
    @signal_listener("user_margin_y")
    def realize(self, origin=None, *args):
        if origin is not None and origin != self.path:
            return
        try:
            unit_size = float(Length(self.lens_size))
        except ValueError:
            return
        if unit_size == 0:
            print(f"Warning: lens_size cannot be zero, skipping realize")
            return
        galvo_range = 0xFFFF
        units_per_galvo = unit_size / galvo_range

        self.view.set_dims(self.lens_size, self.lens_size)
        self.view.set_margins(self.user_margin_x, self.user_margin_y)
        self.view.set_native_scale(units_per_galvo, units_per_galvo)
        self.view.transform(
            flip_x=self.flip_x,
            flip_y=self.flip_y,
            swap_xy=self.swap_xy,
        )
        if self.rotate >= 90:
            self.view.rotate_cw()
        if self.rotate >= 180:
            self.view.rotate_cw()
        if self.rotate >= 270:
            self.view.rotate_cw()
        self.signal("view;realized")

    @property
    def current(self):
        """
        @return: the location in units for the current known position.
        """
        return self.view.iposition(self.driver.native_x, self.driver.native_y)

    @property
    def native(self):
        """
        @return: the location in device native units for the current known position.
        """
        return self.driver.native_x, self.driver.native_y

    @property
    def calibration_file(self):
        return None

    @signal_listener("light_simulate")
    def simulate_state(self, origin, v=True):
        self._simulate = False

    def outline(self):
        if not self._simulate:
            self._simulate = True
            self("full-light\n")
        else:
            self._simulate = False
            self("stop\n")

    def cool_helper(self, choice_dict):
        self.kernel.root.coolant.coolant_choice_helper(self)(choice_dict)

    def location(self):
        """
        Returns the current connection type for the device.
        If the device is in mock mode, returns 'mock', otherwise returns 'usb'.
        """
        return "mock" if self.mock else "usb"

    def get_operation_defaults(self, op_type: str) -> dict:
        """
        Returns the default operation settings for the device.
        """
        settings = {
            "timing_enabled": False,
            "delay_polygon": self.delay_polygon,
            "delay_laser_off": self.delay_laser_off,
            "delay_laser_on": self.delay_laser_on,
            "pulse_width_enabled": self.pulse_width_enabled,
            "pulse_width": self.default_pulse_width,
            "rapid_enabled": False,
            "rapid_speed": self.default_rapid_speed,
            "frequency": self.default_frequency,
        }
        ps_settings = self.get_operation_power_speed_defaults(op_type)
        settings.update(ps_settings)
        return settings
