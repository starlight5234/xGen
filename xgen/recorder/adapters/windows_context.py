"""
Windows Native Context Provider Adapter.
Implements the NativeContextProvider port on Windows using UI Automation (uiautomation) and Win32 APIs.
Zero Qt dependencies.
"""
from __future__ import annotations

import ctypes
import logging
import os
import time
from ctypes import wintypes
from typing import Dict, List, Optional, Sequence, Tuple

try:
    import uiautomation as auto
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    HAS_WINDOWS_DEPS = True
except (ImportError, AttributeError):
    auto = None
    user32 = None
    kernel32 = None
    HAS_WINDOWS_DEPS = False

from xgen.recorder.models import (
    Bounds, CapturedContext, ContextCapabilities, ElementChain, ElementFacts,
    ProcessFacts, ResolutionMethod, SimilarFacts, WindowFacts
)

logger = logging.getLogger("xgen.recorder.context.windows")


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class WindowsContextProvider:
    """
    Windows implementation of NativeContextProvider.
    Extracts element facts, ancestor hierarchies, window metadata, and process info.
    """
    def __init__(self, max_ancestors: int = 15):
        self.max_ancestors = max_ancestors
        self._desktop_handle = int(auto.GetRootControl().NativeWindowHandle) if (auto and hasattr(auto, "GetRootControl")) else 0
        self._awakened_hwnds: set[int] = set()

    def _wake_chromium_accessibility(self, hwnd: int) -> None:
        """Activates Chromium's Blink accessibility engine on demand if needed."""
        if not hwnd or hwnd in self._awakened_hwnds:
            return
        try:
            import comtypes
            OBJID_CLIENT = 0xFFFFFFFC
            IID_IAccessible = comtypes.GUID("{618736E0-3C3D-11CF-810C-00AA00389B71}")
            p_acc = ctypes.c_void_p()
            ctypes.windll.oleacc.AccessibleObjectFromWindow(
                wintypes.HWND(hwnd),
                wintypes.DWORD(OBJID_CLIENT & 0xFFFFFFFF),
                ctypes.byref(IID_IAccessible),
                ctypes.byref(p_acc)
            )
            self._awakened_hwnds.add(hwnd)
        except Exception:
            pass

    def capabilities(self) -> ContextCapabilities:
        return ContextCapabilities(
            has_native_accessibility=True,
            supports_cache_request=True,
            supports_fast_popup_hook=True
        )

    def cursor_position(self) -> Tuple[int, int]:
        """Returns physical screen coordinates of the cursor."""
        pt = POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        return (int(pt.x), int(pt.y))

    def process_of_point(self, x: int, y: int) -> Optional[int]:
        """Returns PID of the window under the point."""
        pt = POINT(x, y)
        hwnd = user32.WindowFromPoint(pt)
        if not hwnd:
            return None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return int(pid.value) if pid.value else None

    def window_still_exists(self, window_handle: int) -> bool:
        """Checks if HWND is still valid."""
        return bool(user32.IsWindow(wintypes.HWND(window_handle)))

    def same_title_windows(self, window: WindowFacts) -> int:
        """Counts open desktop windows matching the given window title."""
        if not window.title:
            return 1

        matches = 0

        def enum_cb(hwnd: int, lparam: int) -> bool:
            nonlocal matches
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    if buf.value == window.title:
                        matches += 1
            return True

        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
        return max(1, matches)

    def capture_at(self, x: int, y: int, *, deadline_ms: int = 250) -> Optional[CapturedContext]:
        """Captures element and ancestor chain under cursor (x, y)."""
        t0 = time.monotonic()
        try:
            pt = POINT(x, y)
            hwnd = int(user32.WindowFromPoint(pt) or 0)
            if hwnd:
                self._wake_chromium_accessibility(hwnd)

            ctrl = auto.ControlFromPoint(x, y)

            # Fallback for fast/popup windows: if ControlFromPoint returned None or Desktop, query HWND directly
            if not ctrl or int(getattr(ctrl, "NativeWindowHandle", 0) or 0) == self._desktop_handle or getattr(ctrl, "ClassName", "") == "#32769":
                if hwnd and hwnd != self._desktop_handle:
                    try:
                        ctrl = auto.ControlFromHandle(hwnd)
                    except Exception:
                        pass

            # Fast window appearance retry: if control not yet ready, brief pause and retry before deadline
            if not ctrl and (time.monotonic() - t0) * 1000 < deadline_ms - 40:
                time.sleep(0.025)
                try:
                    ctrl = auto.ControlFromPoint(x, y)
                    if not ctrl and hwnd and hwnd != self._desktop_handle:
                        ctrl = auto.ControlFromHandle(hwnd)
                except Exception:
                    pass

            if not ctrl:
                return None

            # If ctrl is a container (window, menu, list, etc.), drill down to the innermost child containing (x, y)
            if hasattr(ctrl, "GetChildren"):
                try:
                    for child in ctrl.GetChildren():
                        rect = getattr(child, "BoundingRectangle", None)
                        if rect and hasattr(rect, "left"):
                            if rect.left <= x <= rect.right and rect.top <= y <= rect.bottom:
                                ctrl = child
                                break
                except Exception:
                    pass

            return self._build_context(ctrl, t0, deadline_ms, point_hwnd=hwnd)
        except Exception as e:
            logger.debug("Failed to capture element at (%d, %d): %s", x, y, e)
            return None

    def capture_focused(self, *, deadline_ms: int = 150) -> Optional[CapturedContext]:
        """Captures currently focused element and ancestor chain."""
        t0 = time.monotonic()
        try:
            ctrl = auto.GetFocusedControl()
            if not ctrl:
                return None
            return self._build_context(ctrl, t0, deadline_ms, point_hwnd=0)
        except Exception as e:
            logger.debug("Failed to capture focused element: %s", e)
            return None

    def find_similar(self, ctx: CapturedContext, *, limit: int = 10, deadline_ms: int = 80) -> SimilarFacts:
        """Finds same-named duplicate controls in the same window."""
        t0 = time.monotonic()
        target_name = ctx.chain.target.name
        if not target_name:
            return SimilarFacts(count=1, handles=(ctx.chain.target.native_handle,))

        win_hwnd = ctx.chain.window.handle
        if not win_hwnd:
            return SimilarFacts(count=1, handles=(ctx.chain.target.native_handle,))

        matches: List[int] = []
        try:
            win_ctrl = auto.ControlFromHandle(win_hwnd)
            if not win_ctrl:
                return SimilarFacts(count=1, handles=(ctx.chain.target.native_handle,))

            deadline = t0 + (deadline_ms / 1000.0)

            def walk(c: auto.Control):
                if time.monotonic() > deadline or len(matches) >= limit:
                    return
                if c.Name == target_name:
                    matches.append(int(c.NativeWindowHandle or 0))
                for child in c.GetChildren():
                    walk(child)

            walk(win_ctrl)
        except Exception as e:
            logger.debug("Error querying similar elements: %s", e)

        count = len(matches) if matches else 1
        return SimilarFacts(count=count, handles=tuple(matches))

    # -------------------------------------------------------------------------
    # Internal Helpers
    # -------------------------------------------------------------------------

    def _build_context(self, ctrl: auto.Control, start_time: float, deadline_ms: int,
                       point_hwnd: int = 0) -> Optional[CapturedContext]:
        target_facts = self._element_facts(ctrl)
        ancestors: List[ElementFacts] = []
        ancestor_ctrls: List[auto.Control] = []
        top_window_ctrl: Optional[auto.Control] = None

        curr = ctrl
        deadline = start_time + (deadline_ms / 1000.0)

        for _ in range(self.max_ancestors):
            if time.monotonic() > deadline:
                break
            try:
                parent = curr.GetParentControl()
                if not parent:
                    break
                p_handle = int(parent.NativeWindowHandle or 0)
                if p_handle == self._desktop_handle:
                    break

                # Track candidate top-level window or popup
                p_type = getattr(parent, "ControlTypeName", "")
                if p_type in ("WindowControl", "MenuControl") or "Window" in p_type:
                    top_window_ctrl = parent

                ancestors.append(self._element_facts(parent))
                ancestor_ctrls.append(parent)
                curr = parent
            except Exception:
                break

        # Fallback PID from target ctrl or ancestors if available
        fallback_pid = int(getattr(ctrl, "ProcessId", 0) or 0)
        if not fallback_pid:
            for p in ancestor_ctrls:
                pid_val = int(getattr(p, "ProcessId", 0) or 0)
                if pid_val:
                    fallback_pid = pid_val
                    break

        # Window facts
        win_facts = self._resolve_window_facts(
            ctrl,
            top_window_ctrl,
            ancestors=ancestor_ctrls,
            point_hwnd=point_hwnd
        )

        # Process facts
        proc_facts = self._resolve_process_facts(win_facts.handle, fallback_pid=fallback_pid)

        # Refine window title if needed (e.g. context menus / popups / explorer)
        win_facts = self._refine_window_title(win_facts, proc_facts)

        chain = ElementChain(
            target=target_facts,
            ancestors=tuple(ancestors),
            window=win_facts,
            process=proc_facts,
            complete=True
        )

        cost_ms = int((time.monotonic() - start_time) * 1000)
        mono_now_ms = int(time.monotonic() * 1000)

        return CapturedContext(
            chain=chain,
            resolution=ResolutionMethod.NATIVE_EXACT,
            captured_at_ms=mono_now_ms,
            snapshot_cost_ms=cost_ms
        )

    @staticmethod
    def _element_facts(ctrl: auto.Control) -> ElementFacts:
        c_type = getattr(ctrl, "ControlTypeName", "Unknown")
        if c_type.endswith("Control"):
            c_type = c_type[:-7]

        # Normalize multi-word control types to valid PascalCase XML identifiers (e.g. "Menu Item" -> "MenuItem")
        c_type = "".join(word.capitalize() for word in c_type.split()) if c_type else "Pane"

        rect = getattr(ctrl, "BoundingRectangle", None)
        bounds = None
        if rect and hasattr(rect, "left"):
            bounds = Bounds(
                left=int(rect.left),
                top=int(rect.top),
                right=int(rect.right),
                bottom=int(rect.bottom)
            )

        is_pw = bool(getattr(ctrl, "IsPassword", False))
        auto_id = str(getattr(ctrl, "AutomationId", "") or "")
        name = str(getattr(ctrl, "Name", "") or "")
        cls_name = str(getattr(ctrl, "ClassName", "") or "")
        h_text = str(getattr(ctrl, "HelpText", "") or "")
        handle = int(getattr(ctrl, "NativeWindowHandle", 0) or 0)

        # Fallback control type inference for anonymous or Unknown controls
        if not c_type or c_type == "Unknown":
            if cls_name == "#32768":
                c_type = "Menu"
            elif cls_name == "tooltips_class32":
                c_type = "ToolTip"
            elif "ComboLBox" in cls_name:
                c_type = "List"
            elif "Button" in cls_name:
                c_type = "Button"
            elif "Edit" in cls_name:
                c_type = "Edit"
            else:
                c_type = "Pane"

        # Fallback 1: Query native window title if accessible
        if not name and handle:
            name = WindowsContextAdapter._get_hwnd_text(handle)

        # Fallback 2: Check Value pattern or CurrentValue
        if not name:
            try:
                val = getattr(ctrl, "CurrentValue", None) or getattr(ctrl, "Value", None)
                if val:
                    name = str(val)
            except Exception:
                pass

        # Fallback 3: For composite popup items (e.g. WPF/Electron MenuItem/Button with child Text), check child text
        if not name and hasattr(ctrl, "GetChildren") and c_type in ("Button", "MenuItem", "ListItem", "TabItem", "SplitButton", "Pane"):
            try:
                for ch in ctrl.GetChildren():
                    ch_name = getattr(ch, "Name", "")
                    if ch_name:
                        name = str(ch_name)
                        break
            except Exception:
                pass

        return ElementFacts(
            control_type=c_type,
            name=name,
            automation_id=auto_id,
            class_name=cls_name,
            help_text=h_text,
            bounds=bounds,
            is_password=is_pw,
            native_handle=handle
        )

    @staticmethod
    def _get_hwnd_text(hwnd: int) -> str:
        if not hwnd:
            return ""
        try:
            length = user32.GetWindowTextLengthW(wintypes.HWND(hwnd))
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(wintypes.HWND(hwnd), buf, length + 1)
                return buf.value
        except Exception:
            pass
        return ""

    @staticmethod
    def _get_hwnd_class(hwnd: int) -> str:
        if not hwnd:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(wintypes.HWND(hwnd), buf, 256)
            return buf.value
        except Exception:
            pass
        return ""

    def _resolve_window_facts(
        self,
        target_ctrl: auto.Control,
        top_window_ctrl: Optional[auto.Control],
        ancestors: Sequence[auto.Control] = (),
        point_hwnd: int = 0
    ) -> WindowFacts:
        handle = 0
        win_ctrl = top_window_ctrl

        # 1. Attempt to find handle from candidate window control
        if win_ctrl:
            handle = int(getattr(win_ctrl, "NativeWindowHandle", 0) or 0)

        # 2. Check target control handle
        if not handle:
            handle = int(getattr(target_ctrl, "NativeWindowHandle", 0) or 0)

        # 3. Check ancestor controls for a non-zero NativeWindowHandle
        if not handle:
            for anc in ancestors:
                h = int(getattr(anc, "NativeWindowHandle", 0) or 0)
                if h:
                    handle = h
                    if not win_ctrl:
                        win_ctrl = anc
                    break

        # 4. Check point_hwnd
        if not handle and point_hwnd:
            handle = point_hwnd

        # Root and owner handles
        root_hwnd = 0
        owner_hwnd = 0
        if handle:
            try:
                root_hwnd = int(user32.GetAncestor(wintypes.HWND(handle), 2) or 0)  # GA_ROOT
            except Exception:
                pass
            try:
                owner_hwnd = int(user32.GetWindow(wintypes.HWND(handle), 4) or 0)  # GW_OWNER
            except Exception:
                pass

        if not win_ctrl:
            if root_hwnd:
                try:
                    win_ctrl = auto.ControlFromHandle(root_hwnd)
                except Exception:
                    pass
            if not win_ctrl and handle:
                try:
                    win_ctrl = auto.ControlFromHandle(handle)
                except Exception:
                    pass

        # Class name
        class_name = self._get_hwnd_class(handle) if handle else ""
        if not class_name and win_ctrl:
            class_name = str(getattr(win_ctrl, "ClassName", "") or "")
        if not class_name:
            class_name = str(getattr(target_ctrl, "ClassName", "") or "")

        # Bounds
        bounds = None
        if handle:
            try:
                rect = wintypes.RECT()
                if user32.GetWindowRect(wintypes.HWND(handle), ctypes.byref(rect)):
                    bounds = Bounds(int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
            except Exception:
                pass
        if not bounds and win_ctrl:
            rect = getattr(win_ctrl, "BoundingRectangle", None)
            if rect and hasattr(rect, "left"):
                bounds = Bounds(int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))

        # Classify window kind
        c_type = getattr(target_ctrl, "ControlTypeName", "")
        anc_types = [getattr(a, "ControlTypeName", "") for a in ancestors]

        is_menu = (
            class_name == "#32768"
            or "Menu" in c_type
            or any("Menu" in at for at in anc_types)
        )
        is_tooltip = (
            class_name == "tooltips_class32"
            or "ToolTip" in c_type
            or any("ToolTip" in at for at in anc_types)
        )
        is_popup = (
            "Popup" in class_name
            or "DropDown" in class_name
            or "ComboLBox" in class_name
            or "Popup" in c_type
            or "Flyout" in c_type
            or any("Popup" in at or "Flyout" in at for at in anc_types)
        )
        is_dialog = class_name == "#32770"

        if is_menu:
            kind = "menu"
        elif is_tooltip:
            kind = "tooltip"
        elif is_popup:
            kind = "popup"
        elif is_dialog:
            kind = "dialog"
        else:
            kind = "main"

        # Resolve window title
        raw_title = self._get_hwnd_text(handle) if handle else ""
        if not raw_title and win_ctrl:
            raw_title = str(getattr(win_ctrl, "Name", "") or "")

        title = ""
        if kind == "menu":
            owner_title = self._get_hwnd_text(owner_hwnd) if owner_hwnd else ""
            if not owner_title and root_hwnd and root_hwnd != handle:
                owner_title = self._get_hwnd_text(root_hwnd)
            if owner_title:
                title = f"Context Menu ({owner_title})"
            elif raw_title and raw_title not in ("Context", ""):
                title = f"Context Menu ({raw_title})"
            else:
                title = "Context Menu"
        elif kind == "popup":
            owner_title = self._get_hwnd_text(owner_hwnd) if owner_hwnd else ""
            if not owner_title and root_hwnd and root_hwnd != handle:
                owner_title = self._get_hwnd_text(root_hwnd)
            if owner_title:
                title = f"Popup ({owner_title})"
            elif raw_title:
                title = f"Popup ({raw_title})"
            else:
                title = "Popup Window"
        elif kind == "tooltip":
            title = raw_title if raw_title else "Tooltip"
        elif kind == "dialog":
            title = raw_title if raw_title else "Dialog"
        else:
            if root_hwnd:
                root_title = self._get_hwnd_text(root_hwnd)
                if root_title:
                    title = root_title
                elif raw_title:
                    title = raw_title
                # Use actual top-level root window HWND and class to prevent phantom child-pane window switches
                handle = root_hwnd
                root_cls = self._get_hwnd_class(root_hwnd)
                if root_cls:
                    class_name = root_cls
            elif raw_title:
                title = raw_title

        return WindowFacts(
            handle=handle,
            title=title,
            class_name=class_name,
            kind=kind,
            bounds=bounds
        )

    @staticmethod
    def _refine_window_title(win: WindowFacts, proc: ProcessFacts) -> WindowFacts:
        title = win.title
        app_name = proc.app_name or (os.path.splitext(proc.exe_name)[0] if proc.exe_name else "")
        is_explorer = app_name.lower() in ("explorer", "progman")

        if win.kind == "menu":
            if title == "Context Menu":
                if is_explorer:
                    title = "Desktop Context Menu"
                elif app_name:
                    title = f"Context Menu ({app_name})"
        elif win.kind == "popup":
            if title == "Popup Window":
                if app_name:
                    title = f"Popup ({app_name})"
        elif not title or title == "Unknown Window":
            if is_explorer:
                title = "Windows Explorer" if win.class_name not in ("Progman", "WorkerW") else "Program Manager"
            elif app_name:
                title = f"{app_name.capitalize()} Window"
            else:
                title = "Desktop Window"

        if title != win.title:
            import dataclasses
            return dataclasses.replace(win, title=title)
        return win

    @staticmethod
    def _resolve_process_facts(hwnd: int, fallback_pid: int = 0) -> ProcessFacts:
        process_id = 0
        if hwnd:
            try:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(pid))
                process_id = int(pid.value)
            except Exception:
                pass

        if not process_id and fallback_pid:
            process_id = fallback_pid

        if not process_id:
            return ProcessFacts(pid=0)

        exe_name = ""
        exe_path = ""
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        try:
            h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, process_id)
            if h_proc:
                try:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(1024)
                    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                        exe_path = buf.value
                        exe_name = os.path.basename(exe_path)
                finally:
                    kernel32.CloseHandle(h_proc)
        except Exception:
            pass

        return ProcessFacts(
            pid=process_id,
            exe_name=exe_name,
            exe_path=exe_path,
            app_name=os.path.splitext(exe_name)[0] if exe_name else ""
        )
