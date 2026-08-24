<div align="center">

# ⚡ xGen — Windows XPath Inspector & Locator Studio
**The Modern, Resilient Selector Engine for Appium Windows Driver & WinAppDriver**

[![Python 3.10+](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13%20%7C%203.14-blue.svg)](https://www.python.org/)
[![Platform: Windows](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011%20%7C%20Server-0078D6.svg)](https://microsoft.com/windows)
[![UI: PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![Tests: Pytest](https://img.shields.io/badge/tests-60%20passed-brightgreen.svg)](https://pytest.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-purple.svg)](LICENSE)

</div>

---

## 📖 Overview

**xGen** is a standalone desktop application engineered to eliminate brittle, broken selectors in Windows test automation. Designed specifically for **Appium Windows Driver** and **WinAppDriver**, xGen combines deep UI Automation (UIA) tree walking, machine-learning volatility heuristics, real-time driver verification, and a sleek dark-mode GUI to generate **concise, unique, and resilient XPath expressions** in milliseconds.

---

## 🌟 Key Features & How xGen Works

### 1. 🎯 Continuous Inspect Mode (`F3`)
- Hover over any running desktop application to see an instant, high-DPI electric blue bounding box.
- Clicking an element locks it for inspection while **transparently suppressing native click actions** on external apps so buttons or menus aren't accidentally triggered during inspection.
- Full bypass for the Windows Taskbar, System Tray, and xGen's own UI.

### 2. 🧠 Multi-Tier XPath Generation Engine (T1–T8)
xGen generates ranked candidates strictly conforming to the subset supported by Appium Windows Driver:
- **Tier 1 (Semantic Name / ID)**: `//Button[@Name='Save']` or `//*[@AutomationId='btn_submit']`
- **Tier 2 (Starts-With / Contains Name)**: `//Window[starts-with(@Name, 'Untitled - Notepad')]` for dynamic windows with document titles or build numbers.
- **Tier 3 (Type + Substring)**: `//Edit[contains(@Name, 'Search')]`
- **Tier 4 (Iterative Ancestor Climbing)**: Discovers the closest unique parent container and generates scoped single-anchor selectors like `//Group[@Name='Toolbar']//Button[@Name='Save']`.
- **Tier 5/6 (Positional Fallbacks & Multi-Match Disambiguation)**: Automatically generates indexed variants `(//ListItem)[3]` with tree-ordered match inspection.

### 3. 📊 Stability Scoring & Volatility Classification
- **Volatility Heuristics**: Analyzes IDs with Shannon entropy and regex classifiers to detect temporary GUIDs, machine hashes, or dynamic counters (e.g. `btn_482910_temp`), downgrading their score.
- **Localization Risk (`🌐 Loc Risk`)**: Highlights selectors that depend on localized UI strings (`@Name`, `@HelpText`), warning test engineers when a selector might break across international language packs (e.g., German *'Speichern'*, French *'Enregistrer'*).
- **Hard Ceilings**: Indexed or purely positional selectors are capped at `45` (🔴 Fragile) to discourage brittle automation in CI/CD.

### 4. ▶ Live Driver Verification & Real-Time Actions
- **1-Click Verification (`▶ Test`)**: Instantly sends `POST /session/{id}/element` to your live Appium / WinAppDriver session, reporting real-world execution latency (e.g., `⚡ Found 1 match (28ms)`).
- **👆 Click Element**: Dispatches native W3C click actions.
- **🎯 Hover Element**: Moves the mouse cursor directly over the target element.
- **⌨️ SendKeys / Type Text**: Type custom text into input fields directly from xGen to verify element focus and keystroke behavior without writing test code.

### 5. ⚡ Transient & Ephemeral UI Capture (`F4`)
Inspect context menus, dropdowns, and flyout popups that normally vanish when focus leaves:
- **Instant Snapshot (`F4`)**: Freezes the element directly under the cursor without focus shifting.
- **Timed Countdown Capture**: Set a 3s / 5s countdown timer, interact with a complex multi-level menu, and xGen will snapshot the UI tree upon timer expiry.
- **Frozen Mode (`🔒 Frozen`)**: Locks the UI tree snapshot to prevent background polling from clearing transient popup nodes.

### 6. 📐 High-DPI & Multi-Monitor Support
- True Per-Monitor V2 DPI awareness.
- Precise physical-to-logical coordinate translation for fractional scaling (125%, 150%, 175%, 200%) and multi-monitor setups with negative monitor coordinates.

---

## ⌨️ Global Keyboard Shortcuts

| Shortcut | Action | Description |
|:---:|---|---|
| **`F3`** | **Toggle Inspect Mode** | Activates / deactivates continuous hover and click-to-inspect |
| **`F4`** | **Transient Snapshot** | Freezes the ephemeral menu/tooltip under the mouse cursor |
| **`Ctrl + R`** | **Refresh UI Tree** | Re-queries the full desktop UI tree from the driver |
| **`Esc`** | **Exit Inspect Mode** | Instantly closes overlay and restores standard cursor interaction |

---

## 🚀 Getting Started

### Prerequisites
- **Operating System**: Windows 10, Windows 11, or Windows Server
- **Python**: Python 3.10 or higher
- **Automation Driver**:
  - [Appium 2.x](https://appium.io/) with [`appium-windows-driver`](https://github.com/appium/appium-windows-driver)
  - *OR* Standalone [Windows Application Driver (WinAppDriver)](https://github.com/microsoft/WinAppDriver)

---

### Installation (Developer Setup)

```bash
# 1. Clone the repository
git clone https://github.com/your-username/xgen.git
cd xgen

# 2. Create and activate a Python virtual environment
python -m venv .venv
.venv\Scripts\activate

# 3. Install xGen in editable mode with development dependencies
pip install -e .[dev]

# 4. Launch xGen
python -m xgen
```

---

## 🖥️ Connecting to an Application

When launched, click **Connect Session** on the toolbar:

1. **Desktop Root Mode (Recommended)**:
   - Connects to the desktop root (`app: "Root"`).
   - Allows switching between any open top-level application window on your system.
2. **Launch Application (.exe path)**:
   - Launches a specific executable (e.g. `C:\Program Files\Notepad++\notepad++.exe`).
3. **Attach to Running Window (HWND)**:
   - Attaches directly to an existing window handle (e.g. `0x001A0B2C` or decimal `1706796`).

---

## 📦 How to Build Standalone Executable (.exe)

xGen includes a turnkey PyInstaller packaging script that creates a self-contained, standalone Windows distribution without requiring Python on the target machine.

```bash
# Activate your virtual environment with dev dependencies
.venv\Scripts\activate

# Run the build script
python build_exe.py
```

### Build Artifacts:
- **Output Directory**: `dist/xGen/`
- **Main Executable**: `dist/xGen/xGen.exe` (Windowed app, no console popups)

---

## 🔄 CI/CD & GitHub Releases

This repository includes a GitHub Actions workflow ([`.github/workflows/build-and-release.yml`](.github/workflows/build-and-release.yml)) configured for manual on-demand builds via `workflow_dispatch`:

- **Preview Builds**: Select **Actions → Build, Preview & Release xGen → Run workflow** (choose `build_type: preview`) to run tests and generate a standalone Windows zip archive (`xGen-preview-<sha>-windows-x64.zip`) uploaded as a GitHub Actions Artifact (available for 30 days).
- **Official Releases**: Run the workflow with `build_type: release` and your desired `release_tag` (e.g. `v1.0.0`) to build, verify, and publish a new **GitHub Release** with auto-generated release notes and downloadable `.zip` and `.sha256` assets.

---

## 🧪 Running Automated Tests

Run the full pytest suite:

```bash
pytest -v
```

---

## 📂 Project Architecture

```
xGen/
├── .github/workflows/       # CI/CD pipelines (preview artifacts & GitHub releases)
├── xgen/                    # Core application package
│   ├── capture/             # Mouse/keyboard hooks, overlay window, transient capture
│   ├── core/                # XPath generator, verifier, stability scorer, driver runner
│   ├── events/              # Decoupled application event bus
│   ├── ui/                  # PyQt6 UI panels, toolbar, cards, inspector tables, dialogs
│   ├── utils/               # Per-monitor DPI math, rectangle geometry, logging, privilege
│   └── main.py              # Application bootstrap & crash boundary
├── tests/                   # 60 automated unit and integration tests
├── build_exe.py             # PyInstaller standalone distribution builder
├── xgen.spec                # PyInstaller build specification
└── pyproject.toml           # PEP 517/518 build configuration
```

---

## 📄 License

Distributed under the **MIT License**. See `LICENSE` for more information.
