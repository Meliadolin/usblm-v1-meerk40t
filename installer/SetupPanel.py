#!/usr/bin/env python3
"""SetupPanel - control center for the USBLM-V1 + MeerK40t package.
Buttons: install software, bind driver, self-test, launch app.
Logs everything to logs\\panel_log.txt in this folder."""
import base64
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import zipfile
import tkinter as tk
from tkinter import messagebox, scrolledtext

__version__ = "1.1.0"

CREATE_NO_WINDOW = 0x08000000

if getattr(sys, "frozen", False):
    HERE = os.path.dirname(sys.executable)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))

LOG_DIR = os.path.join(HERE, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG = os.path.join(LOG_DIR, "panel_log.txt")

# Fully self-contained: the runtime is extracted into runtime/ and the app
# files run in place from app/ - nothing goes to %LOCALAPPDATA%.
RUNTIME_DIR = os.path.join(HERE, "runtime")
RUNTIME_PY = os.path.join(RUNTIME_DIR, "python.exe")
RUNTIME_PYW = os.path.join(RUNTIME_DIR, "pythonw.exe")
APP_DIR = os.path.join(HERE, "app")
CFG_DIR = os.path.join(os.environ.get("LOCALAPPDATA", ""), "MeerK40t")
CFG_PATH = os.path.join(CFG_DIR, "MeerK40t.cfg")

# Package subfolders are resolved against HERE at call time (HERE points at
# the package root when frozen, at installer/ when run from source):
#   app/     = the USBLM-V1 profile + USB stack, run in place
#   offline/ = bundled Python + wheels consumed by the install
#   tests/   = self-test / diagnostics
#   tools/   = zadig.exe (driver tool)
#   config/  = MeerK40t.cfg (deployed to the standard MeerK40t location)
#   logs/    = every log produced by the panel and the scripts

PIP_PACKAGES = ["meerk40t", "wxPython==4.2.2", "ezdxf", "pillow",
                "pyusb", "libusb", "numpy"]

ZADIG_EXE = "zadig.exe"
ZADIG_INI = "zadig.ini"
PRESET_INI = "usblm-v1.ini"

# zadig reads zadig.ini (next to the exe) at startup: list ALL devices
# (the driverless board is hidden otherwise), start in advanced mode and
# close by itself after a successful install.
ZADIG_INI_BODY = (
    "[general]\r\n"
    "advanced_mode=true\r\n"
    "exit_on_success=true\r\n"
    "[device]\r\n"
    "list_all=true\r\n"
)

# Optional preset (zadig menu File -> Open) that pre-fills VID/PID.
PRESET_INI_BODY = (
    "[device]\r\n"
    "VID=9588\r\n"
    "PID=9999\r\n"
    "Description=USBLM-V1\r\n"
)


def _clean_pip_line(line):
    """pip prints 'Downloading file:///...' even for local wheels - the
    install IS offline, so say so instead of showing a download line."""
    ln = line.rstrip()
    if ln.startswith("Downloading "):
        name = ln[len("Downloading "):].split(" ")[0]
        return f"installing {name} from the local package cache"
    return ln


def log_msg(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    try:
        with open(LOG, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass
    return line


def _run(cmd, cwd=None):
    """Run and stream stdout lines; returns (returncode, last line)."""
    return subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True,
                            bufsize=1, creationflags=CREATE_NO_WINDOW)


class Panel:
    def __init__(self, root):
        self.root = root
        self.q = queue.Queue()
        root.title("USBLM-V1 + MeerK40t - Setup")
        root.geometry("680x520")
        root.minsize(600, 440)
        root.resizable(True, True)
        root.grid_columnconfigure(0, weight=1)
        root.grid_rowconfigure(0, weight=1)

        frm = tk.Frame(root, padx=12, pady=12)
        frm.grid(row=0, column=0, sticky="nsew")
        frm.grid_columnconfigure(0, weight=1)
        frm.grid_rowconfigure(3, weight=1)

        tk.Label(frm, text="BJJCZ USBLM-V1 + MeerK40t",
                 font=("Segoe UI", 14, "bold")).grid(row=0, column=0,
                                                     sticky="w")
        tk.Label(frm, text="Everything needed is in this folder.",
                 font=("Segoe UI", 9)).grid(row=1, column=0, sticky="w",
                                            pady=(0, 10))

        btns = tk.Frame(frm)
        btns.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        btns.grid_columnconfigure(0, weight=1)
        btns.grid_columnconfigure(1, weight=0, minsize=220)
        btns.grid_columnconfigure(2, weight=1)

        self.btn_install = tk.Button(
            btns, text="1. Install Software",
            command=self.install_software)
        self.btn_install.grid(row=0, column=1, sticky="ew", pady=(0, 6))

        self.btn_driver = tk.Button(
            btns, text="2. Install USB Driver",
            command=self.install_driver)
        self.btn_driver.grid(row=1, column=1, sticky="ew", pady=(0, 6))

        self.btn_selftest = tk.Button(
            btns, text="3. Run Self-Test", command=self.run_selftest)
        self.btn_selftest.grid(row=2, column=1, sticky="ew", pady=(0, 6))

        self.btn_launch = tk.Button(
            btns, text="4. Launch MeerK40t", command=self.launch_meerk)
        self.btn_launch.grid(row=3, column=1, sticky="ew")

        self.txt = scrolledtext.ScrolledText(frm, height=14, state=tk.DISABLED,
                                             font=("Consolas", 9))
        self.txt.grid(row=3, column=0, sticky="nsew", pady=(6, 0))

        self.status = tk.Label(frm, text="Ready.", anchor=tk.W)
        self.status.grid(row=4, column=0, sticky="ew", pady=(6, 0))

        self.log(log_msg(f"panel started from {HERE}"))
        self.log("status: " + ("software installed" if self.runtime_ok()
                               else "software not installed yet - "
                                    "run step 1 first"))
        self.refresh_buttons()
        self.root.after(100, self._poll)

    def runtime_ok(self):
        return os.path.exists(RUNTIME_PY)

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.txt.config(state=tk.NORMAL)
                    self.txt.insert(tk.END, val + "\n")
                    self.txt.see(tk.END)
                    self.txt.config(state=tk.DISABLED)
                elif kind == "status":
                    self.status.config(text=val)
                elif kind == "busy":
                    self._busy_now(val)
                elif kind == "refresh":
                    self.refresh_buttons()
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _busy_now(self, on):
        state = tk.DISABLED if on else tk.NORMAL
        self.btn_install.config(state=state)
        self.btn_driver.config(state=state)
        self.btn_launch.config(state=state)
        if on:
            self.btn_selftest.config(state=state)
        else:
            self.refresh_buttons()

    def refresh_buttons(self):
        ok = self.runtime_ok()
        self.btn_selftest.config(state=tk.NORMAL if ok else tk.DISABLED,
                                 text="3. Run Self-Test" if ok
                                 else "3. Run Self-Test (needs step 1)")

    def log(self, msg):
        self.q.put(("log", msg))

    def set_status(self, msg):
        self.q.put(("status", msg))

    def install_software(self):
        self.q.put(("busy", True))
        self.set_status("installing...")
        threading.Thread(target=self._install_job, daemon=True).start()

    def _install_job(self):
        try:
            self._do_install()
            self.log("=== INSTALL FINISHED ===")
            self.set_status("install finished")
        except Exception as e:
            self.log(f"INSTALL FAILED: {e}")
            self.set_status("install FAILED - see log")
        finally:
            self.q.put(("busy", False))

    def _do_install(self):
        # 1. bundled Python runtime
        if not self.runtime_ok():
            self.log("step 1/5: extracting bundled Python...")
            zip_path = os.path.join(HERE, "offline", "python-embed.zip")
            if not os.path.exists(zip_path):
                raise SystemExit("python-embed.zip missing next to this panel")
            os.makedirs(RUNTIME_DIR, exist_ok=True)
            with zipfile.ZipFile(zip_path) as z:
                names = z.namelist()
                for i, n in enumerate(names):
                    z.extract(n, RUNTIME_DIR)
                    if i % 10 == 0:
                        self.log(f"  extracted {i + 1}/{len(names)}")
            with open(os.path.join(RUNTIME_DIR, "python312._pth"), "w") as f:
                f.write("python312.zip\n.\nLib\nsite-packages\nimport site\n")
            if not self.runtime_ok():
                raise SystemExit("runtime extraction failed")
            self.log("  runtime ready")
        else:
            self.log("step 1/5: runtime already present - skipping")

        # 2. pip
        if not os.path.exists(os.path.join(RUNTIME_DIR, "Scripts", "pip.exe")):
            self.log("step 2/5: installing pip...")
            p = _run([RUNTIME_PY, os.path.join(HERE, "offline", "get-pip.py"),
                      "--no-warn-script-location"])
            for line in p.stdout:
                self.log("  " + line.rstrip())
            p.wait()
            if p.returncode != 0:
                raise SystemExit("pip install failed")
        else:
            self.log("step 2/5: pip already present - skipping")

        # 3. packages
        self.log("step 3/5: installing packages (~45 MB, 1-3 minutes)...")
        wh = os.path.join(HERE, "offline", "wheelhouse")
        if not os.path.isdir(wh):
            raise SystemExit("wheelhouse folder missing next to this panel")
        p = _run([RUNTIME_PY, "-m", "pip", "install", "--no-index",
                  "--no-warn-script-location", "--find-links", wh]
                 + PIP_PACKAGES)
        for line in p.stdout:
            self.log("  " + _clean_pip_line(line))
        p.wait()
        if p.returncode != 0:
            raise SystemExit("package install failed - see log above")
        p = _run([RUNTIME_PY, "-c", "import wx, usb.core, meerk40t"])
        p.wait()
        if p.returncode != 0:
            raise SystemExit("package verification failed")
        self.log("  packages installed and verified")

        # 4. pre-configured MeerK40t settings
        self.log("step 4/5: deploying device settings...")
        if not os.path.exists(CFG_PATH):
            os.makedirs(CFG_DIR, exist_ok=True)
            shutil.copy2(os.path.join(HERE, "config", "MeerK40t.cfg"),
                         CFG_PATH)
            self.log("  device settings deployed (Galvo-Fiber, 30% power)")
        else:
            self.log("  existing settings kept")

        # 5. desktop shortcut (app files run in place from app/)
        self.log("step 5/5: creating desktop shortcut...")
        ps = ("$ws = New-Object -ComObject WScript.Shell; "
              "$sc = $ws.CreateShortcut([Environment]::GetFolderPath("
              "'Desktop') + '\\MeerK40t V1.lnk'); "
              f"$sc.TargetPath = '{RUNTIME_PYW}'; "
              f"$sc.Arguments = '{os.path.join(APP_DIR, 'run_meerk40t.py')}'; "
              f"$sc.WorkingDirectory = '{APP_DIR}'; "
              "$sc.Description = 'MeerK40t - BJJCZ USBLM-V1 laser'; "
              "$sc.Save()")
        r = subprocess.run(["powershell", "-NoProfile", "-WindowStyle",
                            "Hidden", "-Command", ps], capture_output=True,
                           text=True, creationflags=CREATE_NO_WINDOW)
        if r.returncode != 0:
            self.log(f"  shortcut failed: {r.stderr.strip()}")
        else:
            self.log("  shortcut created")

    # Shown in the popup and written to the log: once a user clicks the
    # popup away, panel_log.txt is the only place that still has it.
    DRIVER_GUIDANCE = (
        "A Zadig window opens now.",
        "1. Pick the board from the dropdown - it is listed as",
        "   'USBLM-V1' (VID 9588, PID 9999 or 9990).",
        "2. Click 'Install Driver' - WinUSB is already selected.",
        "3. The window closes by itself when the install is done.",
        "Can't find the board? File -> Open -> usblm-v1.ini",
        "fills in the VID/PID automatically.",
    )

    def install_driver(self):
        zadig = os.path.join(HERE, "tools", ZADIG_EXE)
        if not os.path.exists(zadig):
            self.log("MISSING: tools\\zadig.exe not found in this package")
            return
        try:
            for name, body in ((ZADIG_INI, ZADIG_INI_BODY),
                               (PRESET_INI, PRESET_INI_BODY)):
                with open(os.path.join(HERE, "tools", name), "w") as f:
                    f.write(body)
        except OSError as e:
            self.log(f"could not write the zadig config: {e}")
            return
        self.log("installing the WinUSB driver with zadig.exe - the "
                 "signed driver tool that ships in this folder")
        self.log("zadig is pre-configured (zadig.ini): it lists all "
                 "devices, preselects WinUSB and closes by itself "
                 "after a successful install")
        self.log("a permission dialog will appear - click Yes")
        for line in self.DRIVER_GUIDANCE:
            self.log("  " + line)
        messagebox.showinfo(
            "Zadig - Install the USB driver",
            "\n".join(self.DRIVER_GUIDANCE))
        self.set_status("driver install in progress...")
        self.q.put(("busy", True))
        threading.Thread(target=self._driver_job, daemon=True).start()

    def _driver_job(self):
        try:
            zadig = os.path.join(HERE, "tools", ZADIG_EXE)
            out_log = os.path.join(LOG_DIR, "bind_winusb_log.txt")
            try:
                os.remove(out_log)
            except OSError:
                pass
            inner = (
                "try {{ "
                "$z = '{zadig}'; "
                "$p = Start-Process -FilePath $z -WorkingDirectory "
                "(Split-Path -Parent $z) -PassThru; "
                "$p.WaitForExit(); "
                "$d = Get-PnpDevice -PresentOnly -InstanceId "
                "'USB\\VID_9588*' -ErrorAction SilentlyContinue; "
                "$ok = @($d | Where-Object {{ $_.Service -eq 'WinUSB' "
                "-and $_.Status -eq 'OK' }}).Count -gt 0; "
                "'EXITCODE=' + $p.ExitCode | Out-File '{out}'; "
                "'WINUSB_OK=' + $ok | Out-File '{out}' -Append; "
                "if ($d) {{ 'SERVICE=' + ($d.Service -join ',') + "
                "' STATUS=' + ($d.Status -join ',') | "
                "Out-File '{out}' -Append }}; "
                "if ($ok) {{ exit 0 }} else {{ exit 1 }} "
                "}} catch {{ "
                "Write-Output ('ERROR=' + $_.Exception.Message) | "
                "Out-File '{out}'; exit 2 }}"
            ).format(zadig=zadig.replace("'", "''"),
                     out=out_log.replace("'", "''"))
            inner_enc = base64.b64encode(
                inner.encode("utf-16-le")).decode("ascii")
            outer = (
                "try { "
                "$e = '%s'; "
                "$p = Start-Process -FilePath 'powershell.exe' "
                "-ArgumentList '-NoProfile','-WindowStyle','Hidden',"
                "'-EncodedCommand',$e -Verb RunAs -Wait -PassThru "
                "-WindowStyle Hidden; exit $p.ExitCode "
                "} catch { Write-Error $_.Exception.Message; exit 3 }"
            ) % inner_enc
            outer_enc = base64.b64encode(
                outer.encode("utf-16-le")).decode("ascii")
            r = subprocess.run(
                ["powershell", "-NoProfile", "-WindowStyle", "Hidden",
                 "-EncodedCommand", outer_enc],
                capture_output=True, text=True,
                creationflags=CREATE_NO_WINDOW)
            for line in self._read_log(out_log):
                self.log("  " + line)
            if r.returncode == 0:
                self.log("  WinUSB driver installed")
                self.log("  Device Manager: 'USBLM-V1' with service "
                         "'WinUSB', no warning triangle")
                self.log("  loader mode still shows 'Unknown Device #1' "
                         "until the firmware upload switches it to "
                         "normal mode - also normal")
                self.set_status("driver installed")
            elif r.returncode == 3:
                self.log("  permission was declined - the driver was NOT "
                         "installed; click the button again and click Yes")
                self.set_status("driver install FAILED (declined)")
            else:
                err = self._clean_err(r.stderr)
                if err:
                    self.log("  " + err)
                self.log("  driver install did not complete - the board "
                         "is not bound to WinUSB yet "
                         "(see bind_winusb_log.txt)")
                self.log("  if 'USBLM-V1' did not show up in zadig's "
                         "dropdown: plug the board in, then retry")
                self.set_status("driver install FAILED")
        except Exception as e:
            self.log(f"driver install failed: {e}")
            self.set_status("driver install error")
        finally:
            self.q.put(("busy", False))

    @staticmethod
    def _read_log(path):
        if not os.path.exists(path):
            return []
        with open(path, "rb") as f:
            data = f.read()
        if data.startswith(b"\xff\xfe"):
            text = data.decode("utf-16", errors="replace")
        elif data.startswith(b"\xef\xbb\xbf"):
            text = data.decode("utf-8-sig", errors="replace")
        else:
            text = data.decode("utf-8", errors="replace")
        return [ln.strip() for ln in text.splitlines() if ln.strip()]

    @staticmethod
    def _clean_err(stderr):
        if not stderr:
            return ""
        text = re.sub(r"<[^>]*>", " ", stderr)
        text = text.replace("_x000D_", "\r").replace("_x000A_", "\n")
        text = re.sub(r"\s+", " ", text)
        return text.strip()[:400]

    def run_selftest(self):
        if not self.runtime_ok():
            self.log("software not installed yet - run step 1 first")
            return
        self.q.put(("busy", True))
        self.set_status("self-test running...")
        threading.Thread(target=self._selftest_job, daemon=True).start()

    def _selftest_job(self):
        try:
            self.log("running self-test...")
            p = _run([RUNTIME_PY, os.path.join(HERE, "tests", "selftest.py")],
                     cwd=HERE)
            for line in p.stdout:
                self.log("  " + line.rstrip())
            p.wait()
            if p.returncode == 0:
                self.set_status("self-test passed")
            else:
                self.set_status("self-test FAILED - see log above")
        except Exception as e:
            self.log(f"self-test failed: {e}")
            self.set_status("self-test error")
        finally:
            self.q.put(("busy", False))

    def launch_meerk(self):
        exe = os.path.join(HERE, "MeerK40t-V1.exe")
        if not os.path.exists(exe):
            self.log("MeerK40t-V1.exe not found next to this panel")
            return
        self.log("launching MeerK40t-V1.exe")
        try:
            subprocess.Popen([exe], cwd=HERE)
        except Exception as e:
            self.log(f"launch failed: {e}")


def main():
    if "--version" in sys.argv:
        print(f"SetupPanel {__version__}")
        sys.exit(0)
    root = tk.Tk()
    Panel(root)
    root.mainloop()


if __name__ == "__main__":
    main()
