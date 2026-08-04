"""
USBLM-V1 scene registration.

balormk's scene module is almost entirely its correction-file widget
(test patterns, corfile geometry editor). The V1 board refuses correction
file uploads (the 0x0015 payload format is undecoded - see controller.py
write_correction_file), so that UI is dead on this device and nothing is
registered here. Kept as a module so gui.py can call register_scene()
symmetrically with balormk's structure.
"""


def register_scene(service):
    pass
