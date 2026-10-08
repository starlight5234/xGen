"""
Action-XPath Playback Engine.
Executes test automation workflows directly from the action_xpath_json dictionary
against an Appium / WinAppDriver session.
Zero Qt dependencies.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence

from xgen.recorder.options import PlaybackOptions

logger = logging.getLogger("xgen.recorder.playback")


@dataclass
class PlaybackResult:
    """Outcome of a PlaybackRunner execution."""
    success: bool
    total_steps: int
    executed_steps: int
    failed_step: Optional[int] = None
    error_message: Optional[str] = None
    step_timings: Dict[int, float] = field(default_factory=dict)


class PlaybackRunner:
    """
    Drives Appium test replay directly from action_xpath_json positional mappings:
      {
        "1": ["click", "//Button[@Name='Submit']"],
        "2": ["type", "//Edit[@AutomationId='txtUsername']", "admin@test.com"], ...
      }
    """
    def __init__(self, driver: Any, options: Optional[PlaybackOptions] = None):
        self.driver = driver
        self.options = options or PlaybackOptions()

    def run_file(
        self,
        path: str | Path,
        on_step_progress: Optional[Callable[[int, str, bool], None]] = None
    ) -> PlaybackResult:
        """Loads action JSON from disk and executes playback."""
        actions = load_actions_from_file(path)
        return self.run(actions, on_step_progress=on_step_progress)

    def run(
        self,
        actions_map: Mapping[str, Sequence[Any]],
        on_step_progress: Optional[Callable[[int, str, bool], None]] = None
    ) -> PlaybackResult:
        """
        Executes the provided action dictionary in sequence order.
        """
        # Sort keys numerically (e.g. "1", "2", "10")
        sorted_keys = sorted(actions_map.keys(), key=lambda k: int(k) if k.isdigit() else 999999)
        total = len(sorted_keys)
        timings: Dict[int, float] = {}

        executed_count = 0
        first_failure: Optional[tuple[int, str]] = None

        for i, key in enumerate(sorted_keys):
            seq = int(key) if key.isdigit() else (i + 1)
            item = actions_map[key]
            if not item:
                continue

            action = str(item[0])
            xpath = str(item[1]) if len(item) > 1 else ""
            args = list(item[2:]) if len(item) > 2 else []

            t0 = time.monotonic()
            try:
                self._dispatch_action(action, xpath, args)
                executed_count += 1
                dt = round(time.monotonic() - t0, 3)
                timings[seq] = dt

                if on_step_progress:
                    on_step_progress(seq, action, True)

                if self.options.action_delay_seconds > 0:
                    time.sleep(self.options.action_delay_seconds)

            except Exception as e:
                dt = round(time.monotonic() - t0, 3)
                timings[seq] = dt
                logger.error("Playback failed at step %d (%s): %s", seq, action, e)

                if on_step_progress:
                    on_step_progress(seq, action, False)

                if first_failure is None:
                    first_failure = (seq, str(e))

                if not self.options.continue_on_failure:
                    return PlaybackResult(
                        success=False,
                        total_steps=total,
                        executed_steps=executed_count,
                        failed_step=seq,
                        error_message=str(e),
                        step_timings=timings
                    )

        if first_failure is not None:
            return PlaybackResult(
                success=False,
                total_steps=total,
                executed_steps=executed_count,
                failed_step=first_failure[0],
                error_message=first_failure[1],
                step_timings=timings
            )

        return PlaybackResult(
            success=True,
            total_steps=total,
            executed_steps=executed_count,
            step_timings=timings
        )

    def _dispatch_action(self, action: str, xpath: str, args: List[Any]) -> None:
        """Locates element if XPath is present and dispatches action verb."""
        el = None
        if xpath:
            el = self._find_element(xpath, timeout=self.options.explicit_wait_seconds)

        if action == "click":
            if el is not None:
                el.click()
            else:
                self._fallback_coordinate_action("click", args)

        elif action == "double_click":
            if el is not None:
                self._perform_double_click(el)
            else:
                self._fallback_coordinate_action("double_click", args)

        elif action == "right_click":
            if el is not None:
                self._perform_context_click(el)
            else:
                self._fallback_coordinate_action("right_click", args)

        elif action == "type":
            text = str(args[0]) if args else ""
            if el is not None:
                el.send_keys(text)
            else:
                raise RuntimeError(f"Cannot type text '{text}' without located element")

        elif action == "key_press":
            key_name = str(args[0]) if args else ""
            self._send_key(key_name, el)

        elif action == "scroll":
            dx = int(args[0]) if len(args) > 0 else 0
            dy = int(args[1]) if len(args) > 1 else 0
            self._scroll(dx, dy, el)

        elif action == "wait":
            dur = float(args[0]) if args else 1.0
            time.sleep(dur)

        elif action == "switch_window":
            title = str(args[0]) if args else ""
            self._switch_window(title)

        else:
            logger.warning("Unrecognized playback action '%s', skipping", action)

    def _find_element(self, xpath: str, timeout: float) -> Any:
        """Finds an element by XPath with explicit wait."""
        # 1. Try Appium/Selenium WebDriverWait
        try:
            from appium.webdriver.common.appiumby import AppiumBy
            by = AppiumBy.XPATH
        except ImportError:
            by = "xpath"

        try:
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            return WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located((by, xpath))
            )
        except Exception:
            # 2. Direct driver.find_element fallback (supports mocks and basic drivers)
            if hasattr(self.driver, "find_element"):
                return self.driver.find_element(by, xpath)
            raise

    def _perform_double_click(self, el: Any) -> None:
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            ActionChains(self.driver).double_click(el).perform()
        except Exception:
            # Fallback
            el.click()
            el.click()

    def _perform_context_click(self, el: Any) -> None:
        from selenium.webdriver.common.action_chains import ActionChains
        ActionChains(self.driver).context_click(el).perform()

    def _send_key(self, key_name: str, el: Optional[Any] = None) -> None:
        try:
            from selenium.webdriver.common.keys import Keys
            from selenium.webdriver.common.action_chains import ActionChains

            mod_aliases = {"CTRL": "CONTROL", "WIN": "COMMAND", "CMD": "COMMAND"}

            if "+" in key_name:
                parts = key_name.split("+")
                vals = []
                for p in parts:
                    mapped_name = mod_aliases.get(p.upper(), p.upper())
                    vals.append(getattr(Keys, mapped_name, p.lower() if len(p) == 1 else p))
                if el is not None:
                    el.send_keys(*vals)
                else:
                    ActionChains(self.driver).send_keys(*vals).perform()
                return

            mapped_name = mod_aliases.get(key_name.upper(), key_name.upper())
            val = getattr(Keys, mapped_name, key_name)
            if el is not None:
                el.send_keys(val)
            else:
                ActionChains(self.driver).send_keys(val).perform()
        except Exception:
            if el is not None:
                el.send_keys(key_name)

    def _scroll(self, dx: int, dy: int, el: Optional[Any] = None) -> None:
        try:
            from selenium.webdriver.common.action_chains import ActionChains
            ac = ActionChains(self.driver)
            if hasattr(ac, "scroll_by_amount"):
                ac.scroll_by_amount(dx, dy).perform()
        except Exception as e:
            logger.debug("Scroll execution fallback: %s", e)

    def _switch_window(self, title: str) -> None:
        if not title or not hasattr(self.driver, "window_handles"):
            return
        for handle in self.driver.window_handles:
            try:
                self.driver.switch_to.window(handle)
                if title.lower() in getattr(self.driver, "title", "").lower():
                    return
            except Exception:
                pass

    def _fallback_coordinate_action(self, action_name: str, args: List[Any]) -> None:
        logger.warning("Element XPath missing for %s; attempted with args %s", action_name, args)


def load_actions_from_file(path: str | Path) -> Dict[str, List[Any]]:
    """Convenience helper to read an action_xpath_json dictionary from disk."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data)}")
    return data
