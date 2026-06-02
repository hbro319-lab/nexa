# NEXA v2.1 -- Local System Intelligence
### Full System Control -- Powered by Ollama -- 100% offline -- No API keys

**Version:** 2.1.0

---

## What's New in v2.1

- **Web search** (`web_search`) -- search Google directly from the assistant
- **URL fetching** (`fetch_url`) -- read and extract content from any web page
- **Package installation** (`install_package`) -- auto-install via apt/snap/winget/choco/brew/pip
- **Script creation** (`create_script`) -- create executable script files on the fly
- **Keyboard & mouse automation** -- `type_text`, `press_key`, `hotkey`, `mouse_click`, `mouse_move`, `mouse_scroll` via pyautogui
- **Daemon mode** -- run the dispatch server in the background (`--daemon` flag)
- **Chat API endpoint** (`POST /chat`) -- send natural language to the server, auto-dispatches commands
- **62 total system_control actions** (up from 50)

## What's in v2.0

- **Cross-platform app search engine** (`nexa_app_finder.py`):
  - Linux: scans `.desktop` files, Flatpak, Snap, and PATH binaries
  - Windows: scans Start Menu (.lnk), Registry App Paths, PATH executables, UWP/MSIX apps
  - macOS: scans `/Applications` and `~/Applications`
  - Fuzzy matching with scoring -- finds any app even if you don't know the exact name
- **50 system_control actions** including clipboard, notifications, brightness, wallpaper, network/Wi-Fi, services, scheduling, battery, and more
- **App search bar** in the Web UI for instant app discovery and launch
- **Pipe commands** (`execute_pipe`) for complex shell operations
- **File search** (`find_files`) with regex patterns
- **Service management** (systemctl on Linux, net/sc on Windows)
- **Enhanced quick actions** in the Web UI

---

## Files

| File | Purpose |
|------|---------|
| `nexa_interface.html` | Web UI -- open in any browser, talks to local Ollama |
| `nexa_api_bridge.py` | CLI client -- streaming terminal interface |
| `nexa_dispatcher.py` | Module router -- executes system actions from JSON commands |
| `nexa_app_finder.py` | **NEW** Cross-platform application search engine |
| `nexa_dispatch_server.py` | HTTP server -- bridges browser UI to dispatcher |
| `nexa_gesture_engine.py` | Webcam gesture detection via MediaPipe |
| `nexa_config.json` | All configuration (model, host, modules, gestures, safety) |
| `requirements.txt` | Python dependencies |

---

## Prerequisites

### 1. Install Ollama
Download from **https://ollama.com** and install for your OS.

### 2. Start Ollama
```bash
ollama serve
```

For browser access (HTML interface), allow CORS:
```bash
OLLAMA_ORIGINS=* ollama serve
```
On Windows (PowerShell):
```powershell
$env:OLLAMA_ORIGINS="*"; ollama serve
```

### 3. Pull a model
```bash
ollama pull llama3        # recommended -- fast, capable
ollama pull mistral       # good alternative
ollama pull phi4          # lightweight, efficient
ollama pull deepseek-r1   # strong reasoning
```

### 4. Install Python dependencies
```bash
pip install -r requirements.txt
```

---

## Quick Start

### Web UI (easiest)
1. Start Ollama with `OLLAMA_ORIGINS=* ollama serve`
2. In a second terminal, run:
   ```bash
   python nexa_dispatch_server.py
   ```
   This indexes all installed apps and starts the dispatch server.
3. Open `nexa_interface.html` in your browser
4. Click **test connection** -- it will auto-load your available models
5. Use the **APP SEARCH** bar to find and launch any installed application
6. Type commands or click quick actions

### Daemon mode (background)
```bash
# Start as background daemon
python nexa_dispatch_server.py --daemon

# Check status
python nexa_dispatch_server.py --status

# Stop daemon
python nexa_dispatch_server.py --stop
```

### Chat API (send natural language to the server)
```bash
# Send a message — Ollama processes it and auto-dispatches commands
curl -X POST http://127.0.0.1:11435/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "search Google for Python tutorials"}'

# Reset conversation history
curl -X POST http://127.0.0.1:11435/reset
```

### Python CLI
```bash
pip install -r requirements.txt
python nexa_api_bridge.py
```

CLI commands:
- `reset` -- clear conversation history
- `model llama3.2` -- switch model mid-session
- `search <query>` -- search installed apps
- `exit` -- quit

---

## Architecture

```
User Input (text / voice transcript / gesture event)
        |
        v
  NEXA Reasoning Engine
  (local Ollama LLM -- llama3, mistral, etc.)
        |
        v (JSON command)
  nexa_dispatcher.py
        |
   +----+---------------------------------------+
   |  system_control  automation  memory         |
   |  voice_interface  gesture_interface         |
   |  knowledge  sensors  extensions             |
   |                                             |
   |  nexa_app_finder.py (cross-platform search) |
   +---------------------------------------------+
```

Everything runs on your machine. Zero cloud calls.

---

## Full Action List (62 actions)

### Application Launch & Search
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `open_app` | Launch any app by name (auto-searches system) | `name` |
| `open_app_advanced` | Launch with args and working dir | `name`, `args`, `cwd`, `background` |
| `search_apps` | Fuzzy search installed apps | `query`, `limit` |
| `list_installed_apps` | List all apps, optionally by category | `category`, `limit` |
| `list_app_categories` | Show available app categories | |
| `refresh_app_index` | Force re-scan of installed apps | |
| `open_with` | Open a file with a specific app | `path`, `app` |

### Process Management
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `close_app` | Terminate app by name | `name` |
| `kill_process` | Kill by PID or name | `pid` or `name`, `signal` |
| `list_processes` | Show running processes | `limit`, `sort` (cpu/memory/name) |

### Command Execution
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `execute_command` | Run any shell command | `command`, `args`, `shell`, `background`, `timeout`, `cwd` |
| `execute_pipe` | Run piped shell commands | `command` (full pipe string) |

### File & Directory Operations
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `open_file` | Open with default app | `path` |
| `open_directory` | Open in file explorer | `path` |
| `open_url` | Open in default browser | `url` |
| `create_file` | Create file with content | `path`, `content` |
| `read_file` | Read file | `path`, `max_lines`, `encoding` |
| `delete_file` | Remove file or directory | `path` |
| `copy_file` | Copy file or directory | `src`, `dst` |
| `move_file` | Move/rename | `src`, `dst` |
| `list_directory` | List contents | `path`, `recursive`, `pattern` |
| `create_directory` | Create directory | `path` |
| `find_files` | Search by name pattern | `path`, `pattern` (regex), `limit` |
| `get_file_info` | File metadata | `path` |

### Clipboard
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `get_clipboard` | Read clipboard | |
| `set_clipboard` | Write to clipboard | `text` |

### Screen
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `screenshot` | Capture screen | `output` |
| `record_screen` | Start/stop recording | `operation`, `duration_seconds` |
| `set_brightness` | Screen brightness | `level` (0-100) |
| `set_wallpaper` | Change wallpaper | `path` |

### Audio
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `set_volume` | System volume | `level` (0-100) |
| `get_volume` | Current volume | |
| `toggle_mute` | Mute/unmute | |

### Network
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `get_network_info` | Interfaces, IPs, traffic | |
| `get_wifi_networks` | Scan Wi-Fi | |
| `connect_wifi` | Connect to network | `ssid`, `password` |

### System Info
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `get_system_info` | Full specs (CPU, RAM, disk, temps) | |
| `get_disk_usage` | Disk usage | `path` |
| `get_battery_info` | Battery status | |
| `get_uptime` | Uptime and boot time | |
| `get_user_info` | Current user info | |

### Environment
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `set_environment_variable` | Set env var | `key`, `value`, `persistent` |
| `get_environment_variable` | Read env var | `key`, `default` |
| `list_environment_variables` | List env vars | `pattern` |

### Services
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `manage_service` | Start/stop/restart/status | `name`, `operation` |
| `list_services` | List running services | |

### Scheduling & Notifications
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `schedule_command` | Schedule a command | `command`, `time`, `repeat` |
| `notify` | Desktop notification | `title`, `message`, `urgency` |

### Power & Lock
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `power_action` | Shutdown/reboot/sleep/cancel | `type`, `force`, `delay_seconds` |
| `lock_screen` | Lock the screen | |

### Web Search (NEW in v2.1)
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `web_search` | Search Google | `query`, `num_results` |
| `fetch_url` | Read a web page | `url` |

### Package Management (NEW in v2.1)
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `install_package` | Install via apt/winget/choco/brew/pip | `name`, `manager` (auto/apt/snap/winget/choco/brew/pip) |

### Script Creation (NEW in v2.1)
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `create_script` | Create an executable script file | `path`, `content`, `executable` |

### Keyboard & Mouse Automation (NEW in v2.1)
| Action | Description | Key Parameters |
|--------|-------------|----------------|
| `type_text` | Type text via keyboard | `text`, `interval` |
| `press_key` | Press a single key | `key` |
| `hotkey` | Press a key combination | `keys` (list, e.g. `["ctrl", "c"]`) |
| `mouse_click` | Click at coordinates | `x`, `y`, `button`, `clicks` |
| `mouse_move` | Move cursor | `x`, `y` |
| `mouse_scroll` | Scroll mouse wheel | `amount` (+up / -down) |
| `get_mouse_position` | Get cursor position | |
| `get_screen_size` | Get screen resolution | |

---

## Dispatch Server API

When running `python nexa_dispatch_server.py`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Server status + indexed app count |
| `/search?q=<query>&limit=10` | GET | Search installed apps |
| `/apps?category=<cat>&limit=50` | GET | List all indexed apps |
| `/categories` | GET | List app categories |
| `/refresh` | GET | Force re-index apps |
| `/dispatch` | POST | Execute a NEXA JSON command |
| `/chat` | POST | Send natural language (Ollama + auto-dispatch) |
| `/reset` | POST | Clear chat history |

---

## Safety & Permissions

NEXA includes built-in safety checks:
- **Destructive actions** (delete, shutdown, kill) require LLM confirmation before execution
- Configurable blocked paths in `nexa_config.json`
- All file operations expand `~` to user's home directory
- Command execution has configurable timeouts

---

## Extending NEXA

Add a handler in `nexa_dispatcher.py`:
```python
def handle_my_module(action, params):
    if action == "my_action":
        # your code
        return "Done"
    return f"Unknown: {action}"

HANDLERS["my_module"] = handle_my_module
```

Enable in `nexa_config.json` and NEXA will route to it automatically.

---

## License
MIT -- free to use, modify, and distribute.
