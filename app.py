import os
import subprocess
import threading
import time
import json
import requests
import tempfile
import re
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# ── Config ─────────────────────────────────────────────────
PHONE_IP   = "192.168.100.7"
PHONE_PORT = "5555"
ADB_PATH   = os.path.join(os.path.dirname(__file__), "adb", "adb.exe")

# Fallback to system ADB if local not found
if not os.path.exists(ADB_PATH):
    ADB_PATH = "adb"

MMRL_REPO_URLS = [
    "https://raw.githubusercontent.com/Googlers-Repo/magisk-modules-repo/main/json/modules.json",
    "https://raw.githubusercontent.com/Magisk-Modules-Alt-Repo/json/main/modules.json",
]

app       = Flask(__name__)
app.config["SECRET_KEY"] = "magisk-manager-secret"
app.config['JSON_SORT_KEYS'] = False
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading", logger=False, engineio_logger=False)

# ── ADB Helper ─────────────────────────────────────────────
def get_device_serial():
    """Return best available device serial (TCP preferred, fallback USB)."""
    _, out, _ = adb_global("devices")
    tcp_target = f"{PHONE_IP}:{PHONE_PORT}"
    usb_serial = None
    
    for line in out.splitlines():
        if "\tdevice" not in line:
            continue
        serial = line.split("\t")[0].strip()
        if serial == tcp_target:
            return tcp_target       # TCP match, use immediately
        if usb_serial is None:
            usb_serial = serial     # remember first USB device
    
    return usb_serial               # None if nothing found

def adb(*args, timeout=30):
    """Run ADB command against the best available device."""
    serial = get_device_serial()
    if not serial:
        return -1, "", "No device connected"
    
    cmd = [ADB_PATH, "-s", serial] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out"
    except FileNotFoundError:
        return -1, "", f"ADB not found at: {ADB_PATH}"
    except Exception as e:
        return -1, "", str(e)

def adb_global(*args, timeout=30):
    """Run a global ADB command (no device selector)."""
    cmd = [ADB_PATH] + list(args)
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return -1, "", str(e)

# ── Routes ─────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/connect", methods=["POST"])
def connect_phone():
    """Connect to phone via ADB"""
    # Check what's already connected
    _, out, _ = adb_global("devices")
    print(f"[DEBUG] devices output:\n{out}")

    tcp_target  = f"{PHONE_IP}:{PHONE_PORT}"
    has_tcp     = tcp_target in out and "\tdevice" in out
    has_any     = any("\tdevice" in l for l in out.splitlines())

    print(f"[DEBUG] has_tcp={has_tcp}  has_any={has_any}")

    if not has_tcp:
        if not has_any:
            # Nothing connected at all — restart server and try TCP
            adb_global("kill-server")
            time.sleep(0.5)
            adb_global("start-server")
            time.sleep(0.5)

        # Attempt TCP connect (harmless if USB already present)
        _, cout, cerr = adb_global("connect", tcp_target)
        print(f"[DEBUG] connect output: '{cout}' err: '{cerr}'")

        # Re-check
        _, out2, _ = adb_global("devices")
        has_tcp  = tcp_target in out2 and "\tdevice" in out2
        has_any  = any("\tdevice" in l for l in out2.splitlines())

        if not has_any:
            return jsonify({
                "success": False,
                "message": f"Could not connect: {cout or cerr}",
            }), 503

    # At this point at least one device is available
    try:
        info   = get_phone_info()
        magisk = get_magisk_version()
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to get device info: {str(e)}",
        }), 500

    return jsonify({
        "success": True,
        "message": "Connected",
        "info":    info,
        "magisk":  magisk,
    })

def get_phone_info():
    _, model,   _ = adb("shell", "getprop", "ro.product.model")
    _, android, _ = adb("shell", "getprop", "ro.build.version.release")
    _, bat_raw, _ = adb("shell", "dumpsys", "battery")
    _, storage_raw, _ = adb("shell", "df", "/data")

    print(f"[DEBUG] model='{model}' android='{android}'")
    print(f"[DEBUG] bat_raw='{bat_raw[:200]}'")
    print(f"[DEBUG] storage_raw='{storage_raw[:200]}'")

    # Parse battery
    battery = "-"
    for line in bat_raw.splitlines():
        if "level:" in line:
            battery = line.split(":")[-1].strip() + "%"
            break

    # Parse storage
    storage = "-"
    for line in storage_raw.splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[0].startswith("/dev"):
            try:
                used  = int(parts[2]) // 1024
                total = int(parts[1]) // 1024
                storage = f"{used}MB / {total}MB"
            except Exception:
                pass
            break


    result = {
        "model":   model.strip() or "Unknown",
        "android": android.strip() or "?",
        "battery": battery,
        "storage": storage,
    }
    print(f"[DEBUG] get_phone_info result: {result}")
    return result


def get_magisk_version():
    """Get installed Magisk version"""
    _, out, _ = adb("shell", "su", "-c", "magisk -v")
    if out:
        return out.strip()
    
    _, out, _ = adb("shell", "magisk", "-v")
    return out.strip() if out else "Unknown"

@app.route("/api/modules/search")
def search_modules():
    """Search modules from repositories"""
    query = request.args.get("q", "").strip().lower()
    modules = fetch_modules_from_repos()

    if query:
        modules = [
            m for m in modules
            if query in m.get("name", "").lower()
            or query in m.get("description", "").lower()
            or query in m.get("author", "").lower()
            or query in m.get("id", "").lower()
        ]

    return jsonify({
        "success": True,
        "total":   len(modules),
        "modules": modules[:80],   # cap at 80 results
    })

def fetch_modules_from_repos():
    """Fetch and normalise modules from all known repos."""
    all_modules = []
    seen_ids    = set()

    for url in MMRL_REPO_URLS:
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            data = resp.json()

            # Different repos use different schemas
            raw = []
            if isinstance(data, list):
                raw = data
            elif "modules" in data:
                raw = data["modules"]
            elif "data" in data:
                raw = data["data"]

            for m in raw:
                mid = m.get("id") or m.get("name", "")
                if mid in seen_ids:
                    continue
                seen_ids.add(mid)

                # Normalise download URL
                dl = (
                    m.get("download")
                    or m.get("zipUrl")
                    or (m.get("release", {}).get("zipUrl", "")
                        if isinstance(m.get("release"), dict) else "")
                )

                all_modules.append({
                    "id":          mid,
                    "name":        m.get("name") or mid,
                    "version":     m.get("version") or m.get("versionName") or "?",
                    "versionCode": m.get("versionCode") or "",
                    "author":      m.get("author") or m.get("authorName") or "Unknown",
                    "description": m.get("description") or "",
                    "download":    dl,
                })

        except Exception as e:
            print(f"[WARN] Failed to fetch {url}: {e}")
            continue

    return all_modules

@app.route("/api/modules/installed")
def get_installed_modules():
    script = (
        "find /data/adb/modules -maxdepth 1 -mindepth 1 -type d | while read d; do "
        "id=$(basename \"$d\"); "
        "prop=\"$d/module.prop\"; "
        "name=$(grep -m1 '^name=' \"$prop\" 2>/dev/null | cut -d= -f2-); "
        "ver=$(grep -m1 '^version=' \"$prop\" 2>/dev/null | cut -d= -f2-); "
        "desc=$(grep -m1 '^description=' \"$prop\" 2>/dev/null | cut -d= -f2-); "
        "disabled=$(test -f \"$d/disable\" && echo 1 || echo 0); "
        "remove=$(test -f \"$d/remove\" && echo 1 || echo 0); "
        "printf '%s|%s|%s|%s|%s|%s\\n' \"$id\" \"$name\" \"$ver\" \"$disabled\" \"$remove\" \"$desc\"; "
        "done"
    )

    # Debug: check what files exist
    _, ls_out, _ = adb("shell", "su", "-c", "ls /data/adb/modules/*/")
    print(f"[DEBUG] module files:\n{ls_out[:500]}")

    code, out, err = adb("shell", "su", "-c", script)
    print(f"[DEBUG] installed modules code={code}\nout={out[:300]}\nerr={err[:200]}")

    if code != 0:
        return jsonify({"success": False, "error": err or "Failed", "modules": []}), 500

    modules = []
    for line in out.splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 5)
        if len(parts) < 5:
            continue
        mid, name, version, disabled, remove = parts[:5]
        desc = parts[5] if len(parts) > 5 else ""
        modules.append({
            "id":             mid.strip(),
            "name":           name.strip() or mid.strip(),
            "version":        version.strip() or "?",
            "enabled":        disabled.strip() == "0",
            "pending_remove": remove.strip() == "1",
            "description":    desc.strip(),
        })

    return jsonify({"success": True, "modules": modules})




@app.route("/api/modules/toggle", methods=["POST"])
def toggle_module():
    """Enable or disable a module"""
    data   = request.get_json() or {}
    mid    = data.get("id", "").strip()
    enable = data.get("enable", True)

    if not mid:
        return jsonify({
            "success": False,
            "error": "No module ID provided"
        }), 400

    module_path  = f"/data/adb/modules/{mid}"
    disable_flag = f"{module_path}/disable"

    if enable:
        cmd = f"rm -f {disable_flag}"
        msg = f"Module '{mid}' enabled (takes effect after reboot)"
    else:
        cmd = f"touch {disable_flag}"
        msg = f"Module '{mid}' disabled (takes effect after reboot)"

    code, out, err = adb("shell", "su", "-c", cmd)
    if code != 0:
        return jsonify({
            "success": False,
            "error": err or "Failed to toggle module"
        }), 500

    return jsonify({
        "success": True,
        "message": msg
    })

@app.route("/api/modules/remove", methods=["POST"])
def remove_module():
    """Mark a module for removal"""
    data = request.get_json() or {}
    mid  = data.get("id", "").strip()

    if not mid:
        return jsonify({
            "success": False,
            "error": "No module ID provided"
        }), 400

    remove_flag = f"/data/adb/modules/{mid}/remove"
    code, _, err = adb("shell", "su", "-c", f"touch {remove_flag}")

    if code != 0:
        return jsonify({
            "success": False,
            "error": err or "Failed to mark module for removal"
        }), 500

    return jsonify({
        "success": True,
        "message": f"Module '{mid}' marked for removal on next reboot",
    })

@app.route("/api/reboot", methods=["POST"])
def reboot_phone():
    """Reboot the device"""
    code, _, err = adb("reboot")
    if code != 0:
        return jsonify({
            "success": False,
            "error": err or "Reboot failed"
        }), 500
    
    return jsonify({
        "success": True,
        "message": "Device rebooting..."
    })

@app.route("/api/modules/upload", methods=["POST"])
def upload_module():
    """Upload and install a module from file"""
    if "file" not in request.files:
        return jsonify({
            "success": False,
            "error": "No file provided"
        }), 400

    f = request.files["file"]
    if not f.filename.endswith(".zip"):
        return jsonify({
            "success": False,
            "error": "File must be a .zip"
        }), 400

    safe_name = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", f.filename)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip", prefix="upload_") as tmp:
        tmp_path = tmp.name
        f.save(tmp_path)

    module_id = safe_name.replace(".zip", "")
    
    thread = threading.Thread(
        target=install_module_task,
        args=(None, safe_name, module_id, tmp_path),
        daemon=True,
    )
    thread.start()

    return jsonify({
        "success": True,
        "message": "Upload started"
    })

# ── Socket.IO Install ───────────────────────────────────────
@socketio.on("install_module")
def handle_install(data):
    """Handle module installation via Socket.IO"""
    url  = data.get("url", "")
    name = data.get("name", "module")
    mid  = data.get("id", "module")

    if not url:
        emit("install_done", {
            "success": False,
            "message": "No download URL provided"
        })
        return

    thread = threading.Thread(
        target=install_module_task,
        args=(url, name, mid),
        daemon=True,
    )
    thread.start()

@socketio.on("connect")
def handle_connect():
    """Handle Socket.IO connection"""
    print(f"[DEBUG] Client connected: {request.sid}")
    emit("response", {"data": "Connected to server"})

@socketio.on("disconnect")
def handle_disconnect():
    """Handle Socket.IO disconnection"""
    print(f"[DEBUG] Client disconnected: {request.sid}")

def emit_log(message, level="info"):
    """Emit log message to connected clients"""
    try:
        socketio.emit("install_log", {
            "message": message,
            "level": level
        })
    except Exception as e:
        print(f"[ERROR] Failed to emit log: {e}")

def emit_progress(percent, status=""):
    """Emit progress update to connected clients"""
    try:
        socketio.emit("install_progress", {
            "percent": int(percent),
            "status": status
        })
    except Exception as e:
        print(f"[ERROR] Failed to emit progress: {e}")

def install_module_task(url, name, mid, local_path=None):
    """Install module from URL or local file"""
    tmp_path  = local_path
    push_path = f"/sdcard/Download/{mid}.zip"

    try:
        if local_path:
            # Using uploaded file
            try:
                size_kb = os.path.getsize(local_path) // 1024
                emit_log(f"📁 Using uploaded file: {name} ({size_kb} KB)", "info")
                emit_progress(35, "File ready")
            except OSError:
                raise RuntimeError("Cannot access uploaded file")
        else:
            # ── Step 1: Download ──────────────────────────────
            if not url:
                raise RuntimeError("No URL provided for download")
            
            emit_log(f"⬇️  Downloading {name}...", "info")
            emit_progress(5, "Downloading...")

            try:
                resp = requests.get(url, stream=True, timeout=60)
                resp.raise_for_status()
            except requests.RequestException as e:
                raise RuntimeError(f"Download failed: {str(e)}")

            total   = int(resp.headers.get("content-length", 0))
            fetched = 0

            with tempfile.NamedTemporaryFile(
                delete=False, suffix=".zip", prefix="magisk_"
            ) as f:
                tmp_path = f.name
                try:
                    for chunk in resp.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            fetched += len(chunk)
                            if total > 0:
                                dl_pct = int((fetched / total) * 30) + 5
                                emit_progress(dl_pct, f"Downloading... {fetched//1024}KB")
                except Exception as e:
                    os.remove(tmp_path)
                    raise RuntimeError(f"Download interrupted: {str(e)}")

            try:
                size_kb = os.path.getsize(tmp_path) // 1024
                emit_log(f"✅ Downloaded {size_kb} KB", "success")
                emit_progress(35, "Download complete")
            except OSError:
                raise RuntimeError("Cannot verify downloaded file")

        # ── Step 2: Push to phone ─────────────────────────
        emit_log(f"📤 Pushing ZIP to phone...", "info")
        emit_progress(40, "Pushing to phone...")

        code, out, err = adb("push", tmp_path, push_path)
        if code != 0:
            raise RuntimeError(f"Push failed: {err or out}")

        emit_log(f"✅ ZIP pushed to phone", "success")
        emit_progress(60, "Pushed to phone")

        # ── Step 3: Install via Magisk CLI ────────────────
        emit_log(f"🔧 Installing via Magisk...", "info")
        emit_progress(70, "Installing...")

        install_cmd = f"magisk --install-module '{push_path}'"
        code, out, err = adb("shell", "su", "-c", install_cmd)

        output = (out + "\n" + err).lower()
        for line in (out + "\n" + err).splitlines():
            line = line.strip()
            if line:
                level = "error" if any(
                    w in line.lower() for w in ["error", "fail", "fatal"]
                ) else "info"
                emit_log(f"   {line}", level)

        if code != 0 and "error" in output:
            raise RuntimeError(f"Magisk install error: {err or out}")

        emit_progress(90, "Finalising...")
        adb("shell", "rm", "-f", push_path)
        emit_progress(95, "Cleaning up...")

        emit_log(f"✅ Module queued for installation!", "success")
        emit_log(f"📱 Reboot your phone to activate.", "info")
        emit_progress(100, "Complete!")

        socketio.emit("install_done", {
            "success": True,
            "message": f"{name} installed! Reboot to activate.",
        })

    except Exception as e:
        error_msg = str(e)
        emit_log(f"❌ Error: {error_msg}", "error")
        emit_progress(0, "Failed")
        socketio.emit("install_done", {
            "success": False,
            "message": error_msg,
        })
        print(f"[ERROR] Install failed: {error_msg}")

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception as e:
                print(f"[WARN] Could not clean up temp file: {e}")

# ── Main ────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  🚀 Magisk Module Manager")
    print("  🌐 http://localhost:5000")
    print("=" * 60)
    print()
    socketio.run(app, host="0.0.0.0", port=5000, debug=False, allow_unsafe_werkzeug=True)
