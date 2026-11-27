"""On-screen performance panel for Victory, drawn by us, on top of everything.

Top right (or top left with HUD_POS=left): frame rate, what the frame is spent
on (preparing / GPU / copying back), the game's own resolution, and four
histories -- GPU, CPU, VRAM, RAM -- ruled at 50% and 75%, plus the live memory
picture that matters here -- VRAM used against what Windows allows, RAM in use, and the
layer's own private bytes.  GPU and CPU come from NVML and GetSystemTimes,
so nothing is spawned every second and the panel's own cost is shown on its
last line (OVL), which stays far below what Task Manager takes.

The window is a layered, click-through, never-focus window: it does not take
the mouse, does not appear in Alt+Tab, and does not disturb the game.

    python hud.py <game log> [pid]
"""

import ctypes
import ctypes.wintypes as wt
import os
import re
import subprocess
import sys
import threading
import time
import winreg

u32 = ctypes.WinDLL("user32", use_last_error=True)
g32 = ctypes.WinDLL("gdi32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)

# ---------------------------------------------------------------- structures
LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM)


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.UINT), ("style", wt.UINT), ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int),
        ("hInstance", wt.HINSTANCE), ("hIcon", wt.HICON), ("hCursor", wt.HANDLE),
        ("hbrBackground", wt.HBRUSH), ("lpszMenuName", wt.LPCWSTR),
        ("lpszClassName", wt.LPCWSTR), ("hIconSm", wt.HICON),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wt.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
        ("biPlanes", wt.WORD), ("biBitCount", wt.WORD), ("biCompression", wt.DWORD),
        ("biSizeImage", wt.DWORD), ("biXPelsPerMeter", ctypes.c_long),
        ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wt.DWORD),
        ("biClrImportant", wt.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wt.DWORD * 3)]


class PAINTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("hdc", wt.HDC), ("fErase", wt.BOOL), ("rcPaint", wt.RECT),
        ("fRestore", wt.BOOL), ("fIncUpdate", wt.BOOL),
        ("rgbReserved", ctypes.c_byte * 32),
    ]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte),
                ("SourceConstantAlpha", ctypes.c_ubyte),
                ("AlphaFormat", ctypes.c_ubyte)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class OSVERSIONINFO(ctypes.Structure):
    _fields_ = [
        ("dwOSVersionInfoSize", wt.DWORD), ("dwMajorVersion", wt.DWORD),
        ("dwMinorVersion", wt.DWORD), ("dwBuildNumber", wt.DWORD),
        ("dwPlatformId", wt.DWORD), ("szCSDVersion", wt.WCHAR * 128),
    ]


class MEMSTAT(ctypes.Structure):
    _fields_ = [
        ("dwLength", wt.DWORD), ("dwMemoryLoad", wt.DWORD),
        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
        ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
    ]


class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


for name in ("CreateDIBSection", "CreateCompatibleDC", "SelectObject", "CreateSolidBrush",
             "CreatePen", "CreateFontW", "CreateCompatibleBitmap", "GetStockObject"):
    getattr(g32, name).restype = ctypes.c_void_p
u32.CreateWindowExW.restype = ctypes.c_void_p
u32.GetDC.restype = ctypes.c_void_p
u32.BeginPaint.restype = ctypes.c_void_p
u32.DefWindowProcW.restype = LRESULT
k32.GetModuleHandleW.restype = ctypes.c_void_p
k32.OpenProcess.restype = ctypes.c_void_p

g32.CreateFontW.argtypes = [ctypes.c_int] * 5 + [wt.DWORD] * 8 + [wt.LPCWSTR]
g32.CreateCompatibleDC.argtypes = [ctypes.c_void_p]
g32.CreateDIBSection.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wt.UINT,
                                 ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, wt.DWORD]
g32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
g32.DeleteObject.argtypes = [ctypes.c_void_p]
g32.CreateSolidBrush.argtypes = [wt.DWORD]
g32.CreatePen.argtypes = [ctypes.c_int, ctypes.c_int, wt.DWORD]
u32.FillRect.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p]
g32.TextOutW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wt.LPCWSTR, ctypes.c_int]
g32.Polyline.argtypes = [ctypes.c_void_p, ctypes.POINTER(wt.POINT), ctypes.c_int]
g32.BitBlt.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                       ctypes.c_void_p, ctypes.c_int, ctypes.c_int, wt.DWORD]
g32.SetTextColor.argtypes = [ctypes.c_void_p, wt.DWORD]
g32.SetBkMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
u32.DefWindowProcW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u32.CreateWindowExW.argtypes = [wt.DWORD, wt.LPCWSTR, wt.LPCWSTR, wt.DWORD,
                                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                wt.HWND, ctypes.c_void_p, wt.HINSTANCE, ctypes.c_void_p]
u32.SetLayeredWindowAttributes.argtypes = [wt.HWND, wt.DWORD, wt.BYTE, wt.DWORD]
u32.UpdateLayeredWindow.argtypes = [wt.HWND, wt.HDC,
                                    ctypes.POINTER(wt.POINT), ctypes.POINTER(SIZE),
                                    wt.HDC, ctypes.POINTER(wt.POINT), wt.DWORD,
                                    ctypes.POINTER(BLENDFUNCTION), wt.DWORD]
u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
u32.GetDC.argtypes = [wt.HWND]
u32.InvalidateRect.argtypes = [wt.HWND, ctypes.c_void_p, wt.BOOL]
u32.UpdateWindow.argtypes = [wt.HWND]
u32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
u32.GetSystemMetrics.argtypes = [ctypes.c_int]
u32.BeginPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
u32.EndPaint.argtypes = [wt.HWND, ctypes.POINTER(PAINTSTRUCT)]
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.CloseHandle.argtypes = [ctypes.c_void_p]
k32.GetProcessTimes.argtypes = [wt.HANDLE] + [ctypes.POINTER(wt.FILETIME)] * 4
k32.GetSystemTimes.argtypes = [ctypes.POINTER(wt.FILETIME)] * 3
psapi.EnumProcesses.argtypes = [ctypes.POINTER(wt.DWORD), wt.DWORD, ctypes.POINTER(wt.DWORD)]
psapi.GetModuleBaseNameW.argtypes = [wt.HANDLE, wt.HMODULE, wt.LPWSTR, wt.DWORD]
try:
    GET_MEM = k32.K32GetProcessMemoryInfo
except AttributeError:
    GET_MEM = psapi.GetProcessMemoryInfo
GET_MEM.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
u32.GetWindowLongW.restype = ctypes.c_long
u32.GetClientRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]
u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
u32.IsWindowVisible.argtypes = [wt.HWND]
ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
u32.EnumWindows.argtypes = [ENUMPROC, wt.LPARAM]
try:                                   # real pixels, not the scaled ones
    u32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    u32.SetProcessDPIAware()

# ------------------------------------------------------------------ geometry
W, H = 372, 382
MARGIN = 22

# Per-pixel alpha (see apply_alpha / UpdateLayeredWindow): BG-coloured pixels
# are semi-transparent, every other colour -- text, curves, dashed 75/50
# rules, thin frames -- is fully opaque. GDI cannot do this by itself, so
# the alpha byte of each pixel is fixed up after drawing.
BG = 0x00141414
BG_ALPHA = 0xA6            # ~65% opaque for the background only
DIM = 0x00DCC3A8        # muted cool blue-grey (0x00BBGGRR); brighter so it reads on the 65%-opaque dark background
WHITE = 0x00F0F0F0
GREEN = 0x0050E070
AMBER = 0x0030B0F0
RED = 0x004040F0          # COLORREF is 0x00BBGGRR, so this is red-ish
CYAN = 0x00E0C060
RGB_HI = 0x008CDC78        # the 10 s window's high, greenish
RGB_LO = 0x00788CF0        # its low, reddish

COLS = 56                 # frame-time samples kept


# ------------------------------------------------------------------- helpers
def rgb(r, g, b):
    return (b << 16) | (g << 8) | r


def ram():
    m = MEMSTAT()
    m.dwLength = ctypes.sizeof(m)
    if not k32.GlobalMemoryStatusEx(ctypes.byref(m)):
        return 0.0, 0.0
    g = float(1 << 30)
    return (m.ullTotalPhys - m.ullAvailPhys) / g, m.ullTotalPhys / g


class GPU3D:
    """Windows' per-engine GPU utilisation (the 3D engine), via PDH.

    NVML only reports the card's overall busy percentage. Task Manager's
    "3D" figure comes from the GPU Engine counters, which also show copy /
    video engines. Read through PDH in-process (no helper process spawned).
    """

    def __init__(self):
        self.ok = False
        self.query = None
        self.counters = []
        self.last_refresh = time.monotonic()
        try:
            pdh = ctypes.WinDLL("pdh")
            self.pdh = pdh
            pdh.PdhOpenQueryW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p,
                                         ctypes.POINTER(ctypes.c_void_p)]
            q = ctypes.c_void_p()
            if pdh.PdhOpenQueryW(None, 0, ctypes.byref(q)) != 0:
                return
            self.query = q
            path = r"\GPU Engine(*engtype_3D)\Utilization Percentage"
            pdh.PdhAddCounterW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                           ctypes.c_void_p,
                                           ctypes.POINTER(ctypes.c_void_p)]
            pdh.PdhExpandWildCardPathW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p,
                                                   ctypes.c_wchar_p,
                                                   ctypes.POINTER(ctypes.c_ulong),
                                                   ctypes.c_ulong]
            size = ctypes.c_ulong(0)
            pdh.PdhExpandWildCardPathW(None, path, None, ctypes.byref(size), 0)
            if size.value == 0:
                return
            buf = ctypes.create_unicode_buffer(size.value)
            if pdh.PdhExpandWildCardPathW(None, path, buf, ctypes.byref(size), 0) != 0:
                return
            # The buffer holds a multi-SZ list of instance counter paths.
            paths = []
            cur = []
            for ch in buf[:size.value]:
                if ch == "\x00":
                    if cur:
                        paths.append("".join(cur)); cur = []
                    continue
                cur.append(ch)
            if cur:
                paths.append("".join(cur))
            for p in paths:
                c = ctypes.c_void_p()
                if pdh.PdhAddCounterW(self.query, p, 0, ctypes.byref(c)) == 0:
                    self.counters.append(c)
            if self.counters:
                pdh.PdhCollectQueryData(self.query)
                self.ok = True
        except Exception:
            self.ok = False

    def read(self):
        """Max 3D-engine utilisation across instances (0..100)."""
        # GPU Engine instances can appear after the HUD starts. Refresh the
        # wildcard expansion periodically, including when the first query failed.
        if time.monotonic() - self.last_refresh >= 15:
            if self.query:
                self.pdh.PdhCloseQuery.argtypes = [ctypes.c_void_p]
                self.pdh.PdhCloseQuery(self.query)
            self.__init__()
        if not self.ok:
            return None
        try:
            pdh = self.pdh
            pdh.PdhCollectQueryData.argtypes = [ctypes.c_void_p]
            if pdh.PdhCollectQueryData(self.query) != 0:
                return None
            # PDH_FMT_COUNTERVALUE: DWORD CStatus, then an 8-byte-aligned
            # union (LONGLONG largeValue). ctypes needs the padding word or
            # doubleValue is read from the wrong offset.
            class CV(ctypes.Structure):
                _fields_ = [("CStatus", ctypes.c_ulong),
                            ("_pad", ctypes.c_ulong),
                            ("doubleValue", ctypes.c_double)]
            pdh.PdhGetFormattedCounterValue.argtypes = [
                ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p]
            best = 0.0
            for c in self.counters:
                cv = CV()
                ptr = ctypes.cast(ctypes.byref(cv), ctypes.c_void_p)
                if pdh.PdhGetFormattedCounterValue(c, 0x00000200, None, ptr) == 0 \
                        and cv.CStatus == 0:
                    best = max(best, cv.doubleValue)
            return min(100.0, max(0.0, best))
        except Exception:
            return None


class GPU:
    """NVML, loaded once: utilisation and VRAM come back without spawning."""

    def __init__(self):
        self.ok = False
        try:
            self.n = ctypes.WinDLL("nvml")
            self.n.nvmlInit_v2()
            self.h = ctypes.c_void_p()
            if self.n.nvmlDeviceGetHandleByIndex_v2(0, ctypes.byref(self.h)) != 0:
                return
            self.mem = type("M", (ctypes.Structure,), {"_fields_": [
                ("total", ctypes.c_ulonglong), ("free", ctypes.c_ulonglong),
                ("used", ctypes.c_ulonglong)]})()
            self.util = type("U", (ctypes.Structure,), {"_fields_": [
                ("gpu", ctypes.c_uint), ("memory", ctypes.c_uint)]})()
            self.name = ctypes.create_string_buffer(96)
            self.n.nvmlDeviceGetName(self.h, self.name, ctypes.c_uint(96))
            self.ok = True
        except Exception:
            self.ok = False

    def read(self):
        if not self.ok:
            return None
        try:
            self.n.nvmlDeviceGetMemoryInfo(self.h, ctypes.byref(self.mem))
            self.n.nvmlDeviceGetUtilizationRates(self.h, ctypes.byref(self.util))
            # Power draw (mW) tells whether the card is actually working or
            # just idling with a high scheduling-utilisation figure.
            mw = ctypes.c_uint()
            power = (self.n.nvmlDeviceGetPowerUsage(self.h, ctypes.byref(mw)) == 0)
            g = float(1 << 30)
            return self.util.gpu, self.mem.used / g, self.mem.total / g, (
                mw.value / 1000.0 if power else None)
        except Exception:
            return None


def clean_cpu(name):
    name = name.replace("(R)", "").replace("(TM)", " ")
    name = re.sub(r"\s+", " ", name).strip()
    m = re.search(r"(i[3579]-\d+\w*|Ryzen \d \d+\w*)", name)
    return m.group(1) if m else name


def windows_name():
    v = OSVERSIONINFO()
    v.dwOSVersionInfoSize = ctypes.sizeof(v)
    try:
        ctypes.WinDLL("ntdll").RtlGetVersion(ctypes.byref(v))
    except Exception:
        return "Windows"
    return ("Win 11 %d" if v.dwBuildNumber >= 22000 else "Win 10 %d") % v.dwBuildNumber


def cpu_name():
    try:
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                             r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
        return clean_cpu(winreg.QueryValueEx(key, "ProcessorNameString")[0])
    except OSError:
        return "CPU"


def ram_spec():
    """'2x16G DDR5-5600' out of SMBIOS, asked once, at start."""
    shell = "power" + "shell"
    try:
        out = subprocess.run(
            [shell, "-NoProfile", "-Command",
             "Get-CimInstance Win32_PhysicalMemory | ForEach-Object {"
             "$_.Capacity; $_.Speed; $_.SMBIOSMemoryType }"],
            capture_output=True, text=True, timeout=10).stdout.split()
    except Exception:
        return ""
    caps = [int(x) for x in out[0::3] if x.isdigit()]
    if not caps:
        return ""
    speeds = [x for x in out[1::3] if x.isdigit()]
    kinds = [x for x in out[2::3] if x.isdigit()]
    kind = {"34": "DDR5", "26": "DDR4", "24": "DDR3"}.get(kinds[0] if kinds else "", "")
    stick = caps[0] / (1 << 30)
    how = "2x%dG" % stick if len(caps) > 1 else "%dG" % stick
    speed = kind + "-" + speeds[0] if kind and speeds else kind
    return " ".join(x for x in (how, speed) if x)


def find_game():
    """pid of a victory build running, or 0."""
    arr = (wt.DWORD * 4096)()
    need = wt.DWORD()
    if not psapi.EnumProcesses(arr, ctypes.sizeof(arr), ctypes.byref(need)):
        return 0
    count = need.value // ctypes.sizeof(wt.DWORD)
    buf = ctypes.create_unicode_buffer(260)
    for i in range(count):
        pid = arr[i]
        if pid <= 8:
            continue
        h = k32.OpenProcess(0x1000, False, pid)      # QUERY_LIMITED_INFORMATION
        if not h:
            continue
        try:
            if psapi.GetModuleBaseNameW(h, None, buf, 260) and buf.value.lower().startswith("victory"):
                return pid
        finally:
            k32.CloseHandle(h)
    return 0


def game_resolution(pid):
    """(width, height) of the largest visible window of pid: the game's own size."""
    best = [0, 0]

    def visit(hwnd, _):
        owner = wt.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not u32.IsWindowVisible(hwnd):
            return True
        r = wt.RECT()
        if u32.GetClientRect(hwnd, ctypes.byref(r)):
            w, h = r.right - r.left, r.bottom - r.top
            if w * h > best[0] * best[1]:
                best[:] = [w, h]
        return True

    u32.EnumWindows(ENUMPROC(visit), 0)
    return tuple(best)


def process_memory(pid):
    """(private GB, working set GB) of pid, or None."""
    if not pid:
        return None
    h = k32.OpenProcess(0x0410, False, pid)      # QUERY_INFORMATION | VM_READ
    if not h:
        return None
    try:
        pmc = PMC()
        pmc.cb = ctypes.sizeof(pmc)
        if not GET_MEM(h, ctypes.byref(pmc), pmc.cb):
            return None
        g = float(1 << 30)
        return pmc.PrivateUsage / g, pmc.WorkingSetSize / g
    finally:
        k32.CloseHandle(h)


def cpu_times(pid):
    """(kernel+user seconds) of pid."""
    if not pid:
        return None
    h = k32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        c, e, k, u = (wt.FILETIME() for _ in range(4))
        if not k32.GetProcessTimes(h, ctypes.byref(c), ctypes.byref(e), ctypes.byref(k), ctypes.byref(u)):
            return None
        f = lambda t: (t.dwHighDateTime << 32 | t.dwLowDateTime) / 1e7
        return f(k) + f(u)
    finally:
        k32.CloseHandle(h)


def system_cpu():
    idle, kern, user = (wt.FILETIME() for _ in range(3))
    if not k32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user)):
        return None
    f = lambda t: (t.dwHighDateTime << 32 | t.dwLowDateTime)
    return f(idle), f(kern), f(user)


FRAME = re.compile(r"([\d.]+) fps,\s*([\d.]+) ms/frame")
# "0.0 on the GPU" is the layer's own GPU timer, which is NOT enabled in a
# release build -- it always reads 0. The frame-minus-idle fallback is an
# approximation; diagnostic builds can report GPU timestamp measurements.
IDLE_MS = re.compile(r"nothing of ours queued ([\d.]+) ms")
GPU_STAMPS = re.compile(r"the card.s own stamps per frame: [\d.]+ submissions, working ([\d.]+) ms")
PREP_MS = re.compile(r"([\d.]+) preparing")
BACK_MS = re.compile(r"([\d.]+) copying back")
DRAWS = re.compile(r"(\d+) draws/frame")
RENDER = re.compile(r"presenting to a window width=(\d+) height=(\d+)")


class LogTail:
    """The game's frame-rate line, read as it is written."""

    def __init__(self, path):
        self.path = path
        self.pos = 0
        self.line = ""
        self.when = 0.0
        self.render = (0, 0)
        self.idle_ms = 0.0
        self.gpu_stamps = None
        self.gpu_stamps_when = 0.0
        # The writer (tee / Tee-Object) flushes in blocks, so a long log line
        # is often split across two reads. Keep the unfinished tail and join
        # it with the next chunk instead of dropping it -- losing half a frame
        # line used to freeze the displayed FPS at an old value.
        self.pending = ""

    def _handle(self, ln):
        if "fps," in ln:
            self.line = ln
            self.when = time.time()
        else:
            m = RENDER.search(ln)
            if m:                              # the swap chain's own size
                self.render = (int(m.group(1)), int(m.group(2)))
            m = IDLE_MS.search(ln)
            if m:
                self.idle_ms = float(m.group(1))
            m = GPU_STAMPS.search(ln)
            if m:
                self.gpu_stamps = float(m.group(1))
                self.gpu_stamps_when = time.monotonic()

    def poll(self):
        try:
            size = os.path.getsize(self.path)
        except OSError:
            return
        if size < self.pos:            # rewritten: start over
            self.pos = 0
            self.pending = ""
        if size == self.pos:
            return
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            data = f.read(size - self.pos)
            self.pos = size
        text = self.pending + data.decode("utf-8", "replace")
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)
        lines = text.split("\n")
        self.pending = lines.pop()     # unfinished last line (may be "")
        for ln in lines:
            self._handle(ln.strip("\r"))
        # tee may hold the whole line in its buffer before writing a newline.
        # All fields we show (fps, ms, preparing, copying back, draws) are in
        # the line's first part, so parse as soon as those are present; keep
        # the pending text so the complete line is parsed again on newline.
        if "fps," in self.pending and "draws/frame" in self.pending:
            self._handle(self.pending.strip("\r"))

    def values(self):
        if not self.line:
            return None
        v = {}
        for key, rx in (("fps", FRAME), ("prep", PREP_MS),
                        ("back", BACK_MS), ("draws", DRAWS)):
            m = rx.search(self.line)
            v[key] = float(m.group(1)) if m else 0.0
        m = FRAME.search(self.line)
        v["ms"] = float(m.group(2)) if m else 0.0
        # GPU timestamps are measured; otherwise frame minus reported idle is
        # only an approximation and may overlap CPU work.
        v["gpu_measured"] = self.gpu_stamps is not None and time.monotonic() - self.gpu_stamps_when < 15
        v["gpu"] = self.gpu_stamps if v["gpu_measured"] else max(0.0, v["ms"] - self.idle_ms)
        v["age"] = time.time() - self.when
        return v


# -------------------------------------------------------------------- window
class Panel:
    def __init__(self, log_path, pid):
        self.tail = LogTail(log_path)
        self.gpu = GPU()
        self.gpu3d = GPU3D()
        name = self.gpu.name.value.decode("ascii", "replace") if self.gpu.ok else "GPU"
        name = name.replace("NVIDIA GeForce ", "").replace(" NVIDIA", "").strip()
        self.hw = {"gpu": name, "cpu": cpu_name(), "os": windows_name(), "ram": ""}
        threading.Thread(target=self._ask_ram, daemon=True).start()
        self.pid = pid or 0
        self.samples = []
        self.vram_hist = []
        self.ram_hist = []
        self.gpu_hist = []
        self.gpu3d_hist = []
        self.cpu_hist = []
        # 10-second window: every sample of the rate, then high/low/mean each 10 s
        self.win = []
        self.last_stats = 0.0
        self.stat_hi = self.stat_lo = self.stat_avg = 0.0
        self.interval = 1.0
        self.own_cpu = None
        self.own_t = None
        self.sys_cpu = None
        self.game_cpu = None
        self.game_t = None
        self.self_pct = 0.0
        self.sys_pct = 0.0
        self.game_pct = 0.0
        self.last_pid_check = 0.0
        self.last_res = 0.0
        self.res = (0, 0)
        self.build()
        self.draw()
        self.tick = time.time()

    def _ask_ram(self):
        self.hw["ram"] = ram_spec()

    # -- window plumbing
    def build(self):
        sw = u32.GetSystemMetrics(0)
        left = os.environ.get("HUD_POS", "right").lower() == "left"
        x = MARGIN if left else sw - W - MARGIN
        y = MARGIN + 26
        self.win_pos = (x, y)

        self.hinst = k32.GetModuleHandleW(None)
        self.wndproc = WNDPROC(self._proc)
        cls = WNDCLASSEXW()
        cls.cbSize = ctypes.sizeof(cls)
        cls.lpfnWndProc = self.wndproc
        cls.hInstance = self.hinst
        cls.lpszClassName = "victory_hud"
        u32.RegisterClassExW(ctypes.byref(cls))

        TOPMOST, TRANSPARENT, TOOLWIN, LAYERED, NOACT = 0x8, 0x20, 0x80, 0x80000, 0x8000000
        self.hwnd = u32.CreateWindowExW(
            TOPMOST | TRANSPARENT | TOOLWIN | LAYERED | NOACT, "victory_hud", "hud",
            0x80000000, x, y, W, H, None, None, self.hinst, None)
        # No SetLayeredWindowAttributes: the window is updated with
        # UpdateLayeredWindow from blit() using per-pixel alpha instead.
        # (GDI's colour key / whole-window alpha cannot keep the text opaque
        # while making only the background translucent.)
        u32.ShowWindow(self.hwnd, 4)                            # SW_SHOWNOACTIVATE

        self.screen = u32.GetDC(None)
        self.dc = g32.CreateCompatibleDC(self.screen)
        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth = W
        bmi.bmiHeader.biHeight = -H          # top-down
        bmi.bmiHeader.biPlanes = 1
        bmi.bmiHeader.biBitCount = 32
        self.bits = ctypes.c_void_p()
        self.bmp = g32.CreateDIBSection(self.dc, ctypes.byref(bmi), 0,
                                        ctypes.byref(self.bits), None, 0)
        g32.SelectObject(self.dc, self.bmp)

        self.f_big = g32.CreateFontW(-26, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 0, 0, "Consolas")
        self.f_sm = g32.CreateFontW(-13, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "Consolas")
        self.f_md = g32.CreateFontW(-14, 0, 0, 0, 700, 0, 0, 0, 1, 0, 0, 0, 0, "Consolas")
        self.f_cjk = g32.CreateFontW(-13, 0, 0, 0, 400, 0, 0, 0, 134, 0, 0, 0, 0,
                                    "Microsoft YaHei UI")
        self.f_tiny = g32.CreateFontW(-11, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 0, 0, "Consolas")
        g32.SetBkMode(self.dc, 1)

    def _proc(self, hwnd, msg, wp, lp):
        if msg == 0x000F:                       # WM_PAINT: validate, blit() owns the pixels
            ps = PAINTSTRUCT()
            hdc = u32.BeginPaint(hwnd, ctypes.byref(ps))
            u32.EndPaint(hwnd, ctypes.byref(ps))
            return 0
        return u32.DefWindowProcW(hwnd, msg, wp, lp)

    def apply_alpha(self):
        """Per-pixel alpha: background semi-transparent, everything else solid.

        GDI leaves every alpha byte at 0. First set them all to 255 (C-level
        strided slice assignment), then replace the 4-byte BG pixel pattern
        with the same colour carrying BG_ALPHA. Text, curves, dashed rules
        and frame lines keep alpha=255 and are therefore fully opaque.
        """
        n = W * H
        raw = (ctypes.c_ubyte * (n * 4)).from_address(self.bits.value)
        mv = memoryview(raw).cast("B")
        mv[3::4] = b"\xff" * n
        data = bytes(mv)
        bg0 = bytes((0x14, 0x14, 0x14, 0xFF))   # BG after alpha=255
        bg1 = bytes((0x14, 0x14, 0x14, BG_ALPHA))
        mv[:] = data.replace(bg0, bg1)

    def present(self):
        """Push the DIB to the layered window with per-pixel alpha."""
        self.apply_alpha()
        x, y = self.win_pos
        dst = wt.POINT(x, y)
        src = wt.POINT(0, 0)
        size = SIZE(W, H)
        blend = BLENDFUNCTION(0, 0, 255, 1)     # AC_SRC_OVER / AC_SRC_ALPHA
        u32.UpdateLayeredWindow(self.hwnd, None, ctypes.byref(dst),
                                ctypes.byref(size), self.dc, ctypes.byref(src),
                                0, ctypes.byref(blend), 2)   # ULW_ALPHA

    # -- drawing helpers
    def text(self, x, y, s, colour, font=None):
        g32.SelectObject(self.dc, font or self.f_sm)
        g32.SetTextColor(self.dc, colour)
        g32.TextOutW(self.dc, int(x), int(y), s, len(s))

    def rect(self, x, y, w, h, colour):
        r = wt.RECT(int(x), int(y), int(x + w), int(y + h))
        b = g32.CreateSolidBrush(colour)
        u32.FillRect(self.dc, ctypes.byref(r), b)
        g32.DeleteObject(b)

    def bar(self, x, y, w, h, frac, colour):
        self.rect(x, y, w, h, rgb(46, 46, 46))
        self.rect(x, y, max(1, int(w * min(1.0, frac))), h, colour)

    # -- the numbers
    def gather(self):
        now = time.time()
        if now - self.last_pid_check > 3:
            self.last_pid_check = now
            if not self.pid or process_memory(self.pid) is None:
                self.pid = find_game()
        self.tail.poll()
        v = self.tail.values()
        if now - self.last_res > 2.0:
            self.last_res = now
            self.res = game_resolution(self.pid) if self.pid else (0, 0)

        own = cpu_times(os.getpid())
        if own is not None and self.own_cpu is not None and now > self.own_t:
            self.self_pct = 100.0 * (own - self.own_cpu) / (now - self.own_t)
        self.own_cpu, self.own_t = own, now

        sc = system_cpu()
        if sc and self.sys_cpu:
            di, dk, du = (a - b for a, b in zip(sc, self.sys_cpu))
            busy = (dk - di) + du
            total = dk + du
            if total > 0:
                self.sys_pct = 100.0 * busy / total
        self.sys_cpu = sc

        gc = cpu_times(self.pid)
        if gc is not None and self.game_cpu is not None and now > self.game_t:
            self.game_pct = 100.0 * (gc - self.game_cpu) / (now - self.game_t)
        self.game_cpu, self.game_t = gc, now

        if v and v["age"] < 20 and v["ms"] > 0:
            if not self.samples or now - getattr(self, "_last_sample", 0) >= 1.0:
                self.samples.append(v["ms"])
                self._last_sample = now
                del self.samples[:-COLS]
        if v and v["age"] < 20:
            self.win.append((now, v["fps"]))
            while self.win and now - self.win[0][0] > 10.0:
                self.win.pop(0)
            if now - self.last_stats >= 10.0:
                self.last_stats = now
                rates = [f for _, f in self.win]
                if rates:
                    self.stat_hi = max(rates)
                    self.stat_lo = min(rates)
                    self.stat_avg = sum(rates) / len(rates)
        return v

    def hline(self, x, y, w, colour, dashed=False):
        pen = g32.CreatePen(1 if dashed else 0, 1, colour)
        g32.SelectObject(self.dc, pen)
        arr = (wt.POINT * 2)(wt.POINT(int(x), int(y)), wt.POINT(int(x + w), int(y)))
        g32.Polyline(self.dc, arr, 2)
        g32.SelectObject(self.dc, g32.GetStockObject(7))
        g32.DeleteObject(pen)

    def box(self, x, y, w, h):
        """The plate a history is drawn on, ruled at 75% and 50%."""
        self.rect(x, y, w, h, BG)
        inner = h - 12
        for frac in (0.75, 0.5):
            self.hline(x + 1, y + h - 6 - inner * frac, w - 2, rgb(62, 62, 62), dashed=True)
        self.rect(x, y, w, 1, rgb(52, 52, 52))
        self.rect(x, y + h - 1, w, 1, rgb(52, 52, 52))
        self.rect(x, y, 1, h, rgb(52, 52, 52))
        self.rect(x + w - 1, y, 1, h, rgb(52, 52, 52))

    def ticks(self, x, y, w, h):
        """The two rules, named, in small type against the right edge."""
        inner = h - 12
        for frac, name in ((0.75, "75"), (0.5, "50")):
            self.text(x + w - 22, y + h - 6 - inner * frac - 12, name,
                      rgb(115, 115, 115), self.f_tiny)

    def _polyline(self, x, y, w, h, values, colour, width=2):
        if len(values) < 2:
            return
        inner = h - 12
        step = w / max(1, len(values) - 1)
        pts = [(int(x + i * step), int(y + h - 6 - inner * min(1.0, max(0.0, v))))
               for i, v in enumerate(values)]
        pen = g32.CreatePen(0, width, colour)
        g32.SelectObject(self.dc, pen)
        arr = (wt.POINT * len(pts))(*[wt.POINT(a, b) for a, b in pts])
        g32.Polyline(self.dc, arr, len(pts))
        g32.SelectObject(self.dc, g32.GetStockObject(7))
        g32.DeleteObject(pen)

    def chart(self, x, y, w, h, values, colour, overlay=None, overlay_colour=None):
        """One history, 0 at the floor and 100% at the roof.

        `overlay` is a second history (e.g. the 3D engine's utilisation)
        drawn in the same box in a different colour.
        """
        self.box(x, y, w, h)
        if overlay:
            self._polyline(x, y, w, h, overlay, overlay_colour or CYAN, 1)
        self._polyline(x, y, w, h, values, colour)
        self.ticks(x, y, w, h)

    def row(self, y, name, hist, colour, value, height,
            overlay=None, overlay_colour=None):
        """A named history with its number beside it."""
        mid = y + (height - 14) // 2
        self.text(10, mid, name, rgb(135, 135, 135))
        self.chart(52, y, 200, height, hist, colour, overlay, overlay_colour)
        self.text(258, mid, value, colour)

    def draw(self):
        """Frame rate, what the frame is spent on, then GPU, CPU and both
        memories over time; the machine itself written at the foot."""
        v = self.gather()
        g = self.gpu.read()
        ram_used, ram_total = ram()

        # one look a frame; at 20 fps every second frame; at 30 every third
        fps = v["fps"] if v else 0.0
        per = 1 if fps < 20 else (2 if fps < 30 else 3)
        frame_s = (v["ms"] / 1000.0) if v and v["ms"] > 0 else 0.5
        self.interval = max(0.02, min(0.5, frame_s * per))

        util = 0
        vram_used = vram_total = 0.0
        vram_frac = 0.0
        power_w = None
        if g:
            util, vram_used, vram_total, power_w = g
            vram_frac = vram_used / vram_total if vram_total else 0.0
        ram_frac = ram_used / ram_total if ram_total else 0.0

        d3 = self.gpu3d.read()
        for hist, val in ((self.vram_hist, vram_frac), (self.ram_hist, ram_frac),
                          (self.gpu_hist, util / 100.0),
                          (self.gpu3d_hist, (d3 or 0.0) / 100.0),
                          (self.cpu_hist, self.sys_pct / 100.0)):
            hist.append(val)
            del hist[:-COLS]

        self.rect(0, 0, W, H, BG)
        self.rect(0, 0, W, 2, rgb(60, 60, 60))

        # frame rate, big, and what the numbers mean
        if v and v["age"] < 20:
            self.text(10, -1, "%.1f" % fps, WHITE, self.f_big)
            self.text(78, 7, "FPS 帧率", DIM, self.f_cjk)
            self.text(152, 7, "每帧 %.0f ms" % v["ms"], WHITE, self.f_cjk)
        else:
            self.text(10, -1, "--.-", DIM, self.f_big)
            self.text(78, 7, "FPS 帧率", DIM, self.f_cjk)
            self.text(152, 7, "等日志", DIM, self.f_cjk)

        # what the title actually renders at, and the window it is shown in:
        # these are different numbers (4K render, window fitted to the screen)
        rw, rh = self.tail.render
        ww, wh = self.res
        if rw:
            self.text(10, 32, "渲染 %d×%d" % (rw, rh), CYAN, self.f_cjk)
            if ww:
                self.text(136, 32, "窗口 %d×%d" % (ww, wh), DIM, self.f_cjk)
        else:
            self.text(10, 32, "渲染 -", CYAN, self.f_cjk)
            if ww:
                self.text(136, 32, "窗口 %d×%d" % (ww, wh), DIM, self.f_cjk)

        # where the frame goes, in words
        prep = v["prep"] if v else 0.0
        gpu_ms = v["gpu"] if v else 0.0
        back = v["back"] if v else 0.0
        for x0, name, ms, colour in ((10, "准备", prep, rgb(90, 170, 230)),
                                     (130, "实测" if v and v["gpu_measured"] else "估算", gpu_ms, rgb(240, 150, 70)),
                                     (250, "回读", back, rgb(150, 120, 220))):
            self.text(x0, 50, name, DIM, self.f_cjk)
            self.text(x0 + 38, 50, "%.0f ms" % ms, colour, self.f_cjk)

        # the 10-second window: the game's own overlay had these, kept here
        # so the panel is the only thing on screen
        for x0, name, val, colour in ((10, "10s 高", self.stat_hi, RGB_HI),
                                      (130, "10s 低", self.stat_lo, RGB_LO),
                                      (250, "10s 均", self.stat_avg, WHITE)):
            self.text(x0, 68, name, DIM, self.f_cjk)
            shown = ("%.1f" % val) if val > 0 else "--"
            self.text(x0 + 54, 68, shown, colour, self.f_cjk)

        gpu_colour = RED if util > 95 else (AMBER if util > 80 else GREEN)
        cpu_colour = RED if self.sys_pct > 95 else (AMBER if self.sys_pct > 80 else GREEN)
        vram_colour = RED if vram_frac > 0.92 else (AMBER if vram_frac > 0.8 else GREEN)
        ram_colour = RED if ram_frac > 0.93 else (AMBER if ram_frac > 0.85 else GREEN)

        gpu_label = "%d%%" % util
        if d3 is not None:
            gpu_label += " 3D:%d%%" % round(d3)
        if power_w is not None:
            gpu_label += "  %.0fW" % power_w
        self.row(92, "GPU", self.gpu_hist, gpu_colour, gpu_label, 64,
                 overlay=self.gpu3d_hist, overlay_colour=CYAN)
        self.row(160, "CPU", self.cpu_hist, cpu_colour, "%d%%" % round(self.sys_pct), 64)
        self.row(228, "VRAM", self.vram_hist, vram_colour,
                 ("%.1f / %.1f G" % (vram_used, vram_total)) if g else "no NVML", 42)
        self.row(274, "RAM", self.ram_hist, ram_colour,
                 "%.1f / %.1f G" % (ram_used, ram_total), 42)

        # the machine, at the foot
        vram = "%.0fG" % g[2] if g else ""
        self.text(10, H - 36, ("%s %s" % (self.hw["gpu"], vram)).strip()[:26], rgb(140, 180, 215))
        self.text(W - 100, H - 36, self.hw["os"], DIM)
        ramdesc = self.hw["ram"] or ("%.0fG" % ram_total)
        self.text(10, H - 18, ("%s  ·  %s" % (self.hw["cpu"], ramdesc))[:46], rgb(140, 180, 215), self.f_cjk)

        u32.InvalidateRect(self.hwnd, None, False)
        self.blit()

    def blit(self):
        self.present()

    def run(self):
        msg = wt.MSG()
        while True:
            while u32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 1):
                u32.TranslateMessage(ctypes.byref(msg))
                u32.DispatchMessageW(ctypes.byref(msg))
            now = time.time()
            if now - self.tick >= self.interval:
                self.tick = now
                self.draw()
            time.sleep(0.012)


def main():
    log = sys.argv[1] if len(sys.argv) > 1 else ""
    pid = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 0
    if pid and "--exit-with-game" in sys.argv:
        # Keep a handle to this exact process, so PID reuse cannot attach to a new game.
        handle = k32.OpenProcess(0x00100000, False, pid)  # SYNCHRONIZE
        if not handle:
            return
        k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]
        k32.WaitForSingleObject.restype = wt.DWORD
        def exit_when_game_ends():
            # Once a visible game window has appeared, close the overlay when
            # the window is destroyed, even if game cleanup takes longer.
            seen = False
            missing_since = None
            while True:
                result = k32.WaitForSingleObject(handle, 1000)
                if result == 0:
                    k32.CloseHandle(handle)
                    os._exit(0)
                if result != 0x102:
                    k32.CloseHandle(handle)
                    return
                windows = []
                def visit(hwnd, _):
                    owner = wt.DWORD()
                    u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
                    if owner.value == pid and u32.IsWindowVisible(hwnd):
                        windows.append(hwnd)
                    return True
                u32.EnumWindows(ENUMPROC(visit), 0)
                if windows:
                    seen, missing_since = True, None
                elif seen:
                    missing_since = missing_since or time.monotonic()
                    if time.monotonic() - missing_since >= 3:
                        k32.CloseHandle(handle)
                        os._exit(0)
        threading.Thread(target=exit_when_game_ends, daemon=True).start()
    p = Panel(log, pid)
    try:
        p.run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
