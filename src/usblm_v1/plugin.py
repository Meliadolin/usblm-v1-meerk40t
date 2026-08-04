"""
USBLM-V1 plugin entry point.

Registers the V1 device provider with the MeerK40t kernel, mirroring how
meerk40t.balormk.plugin registers the later-generation (9899) boards.
"""


def plugin(kernel, lifecycle):
    if lifecycle == "plugins":
        from usblm_v1 import commands
        from usblm_v1 import gui

        return [gui.plugin, commands.plugin]
    if lifecycle == "invalidate":
        try:
            import usb.core
            import usb.util
        except ImportError:
            print("Galvo plugin could not load because pyusb is not installed.")
            return True
    if lifecycle == "register":
        from usblm_v1.device import V1Device

        kernel.register("provider/device/usblmv1", V1Device)
        kernel.register("provider/friendly/usblmv1", ("USBLM-V1", 3))
        _ = kernel.translation
        kernel.register(
            "dev_info/usblmv1",
            {
                "provider": "provider/device/usblmv1",
                "friendly_name": _("USBLM-V1 (BJJCZ)"),
                "extended_info": _(
                    "The BJJCZ USBLM-V1 is an EZCAD2-era galvo laser controller "
                    "(VID 9588 / PID 9999). It boots as a firmware loader "
                    "(PID 9990) and needs its firmware uploaded before it "
                    "becomes a marking device - this profile handles that "
                    "automatically."
                ),
                "family": _("Generic Fibre-Laser"),
                "priority": 9,
                "choices": [
                    {"attr": "label", "default": "USBLM-V1"},
                ],
            },
        )
    if lifecycle == "preboot":
        prefix = "usblmv1"
        for d in kernel.settings.section_startswith(prefix):
            kernel.root(f"service device start -p {d} {prefix}\n")
