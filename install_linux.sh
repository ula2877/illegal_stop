#!/usr/bin/env bash
set -euo pipefail

# ==========================================
# Installer: ILLEGAL STOP DETECTION v.2.5
# Target: Linux (Debian/Ubuntu-based)
# ==========================================

REPO_URL="https://github.com/ula2877/illegal_stop.git"
APP_DIR="illegal_stop"
VENV_DIR=".venv"
PYTHON_BIN="python3"

echo "==> [1/9] Cek OS & package manager"
if ! command -v apt-get >/dev/null 2>&1; then
  echo "Script ini dibuat untuk distro berbasis Debian/Ubuntu (apt-get)."
  echo "Silakan install dependensi manual jika memakai distro lain."
fi

echo "==> [2/9] Install dependensi sistem (butuh sudo)"
sudo apt-get update
sudo apt-get install -y \
  git \
  git-lfs \
  ${PYTHON_BIN} \
  ${PYTHON_BIN}-venv \
  ${PYTHON_BIN}-pip \
  python3-dev \
  build-essential \
  pkg-config \
  libgl1 \
  libglib2.0-0 \
  libsm6 \
  libxext6 \
  libxrender1 \
  libxcb-xinerama0 \
  libxcb-cursor0 \
  ffmpeg \
  libgtk-3-0

echo "==> [3/9] Inisialisasi Git LFS"
git lfs install

echo "==> [4/9] Clone repository"
if [ -d "$APP_DIR/.git" ]; then
  echo "Folder $APP_DIR sudah ada, melakukan git pull..."
  git -C "$APP_DIR" pull
  git -C "$APP_DIR" lfs pull
else
  git clone "$REPO_URL" "$APP_DIR"
  git -C "$APP_DIR" lfs pull
fi

cd "$APP_DIR"

echo "==> [5/9] Buat virtual environment"
if [ ! -d "$VENV_DIR" ]; then
  $PYTHON_BIN -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "==> [6/9] Upgrade pip dan install dependensi Python"
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

APP_PATH="$(pwd)"
TARGET_USER="${SUDO_USER:-$USER}"
TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
DESKTOP_FILE="$TARGET_HOME/Desktop/illegal-stop-detection.desktop"
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/illegal-stop-detection.desktop"
ICON_PATH="$APP_PATH/resources/images/icon.png"
EXEC_CMD="/bin/bash -c 'cd \"$APP_PATH\" && source \"$APP_PATH/$VENV_DIR/bin/activate\" && python main.py'"

echo "==> [7/9] Buat shortcut desktop"
mkdir -p "$TARGET_HOME/Desktop"
cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Illegal Stop Detection
Comment=JPL Early Warning System - Illegal Stop Detection
Exec=$EXEC_CMD
Path=$APP_PATH
Icon=$ICON_PATH
Terminal=false
Categories=Utility;Application;
StartupNotify=true
EOF

chmod +x "$DESKTOP_FILE"
chown "$TARGET_USER":"$TARGET_USER" "$DESKTOP_FILE" 2>/dev/null || true
# Tandai trusted di GNOME (Ubuntu 22); abaikan jika gio tidak tersedia / gagal
sudo -u "$TARGET_USER" gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true

echo "==> [8/9] Buat autorun GNOME (Startup Applications)"
mkdir -p "$AUTOSTART_DIR"
cp "$DESKTOP_FILE" "$AUTOSTART_FILE"
chmod +x "$AUTOSTART_FILE"
chown "$TARGET_USER":"$TARGET_USER" "$AUTOSTART_DIR" "$AUTOSTART_FILE" 2>/dev/null || true

echo "==> [9/9] Konfigurasi auto-login dan nonaktifkan sleep/suspend (Ubuntu 22.04)"
# Auto-login GDM3
GDM_CUSTOM="/etc/gdm3/custom.conf"
if [ -f "$GDM_CUSTOM" ]; then
  sudo cp "$GDM_CUSTOM" "${GDM_CUSTOM}.bak.$(date +%s)" 2>/dev/null || true
  sudo python3 - <<PY
import configparser, os
path = r"$GDM_CUSTOM"
user = r"$TARGET_USER"
cfg = configparser.ConfigParser(strict=False)
cfg.optionxform = str
if os.path.exists(path):
    cfg.read(path)
if 'daemon' not in cfg:
    cfg['daemon'] = {}
cfg['daemon']['AutomaticLoginEnable'] = 'true'
cfg['daemon']['AutomaticLogin'] = user
with open(path, 'w') as f:
    cfg.write(f, space_around_delimiters=False)
print('GDM auto-login configured for', user)
PY
else
  echo "Peringatan: $GDM_CUSTOM tidak ditemukan, lewati konfigurasi auto-login."
fi

# Nonaktifkan sleep/suspend/hibernate di systemd
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target 2>/dev/null || true

# Nonaktifkan screen blank/idle/suspend di GNOME (best-effort, perlu session user)
run_as_user() {
  sudo -u "$TARGET_USER" env \
    DISPLAY="${DISPLAY:-:0}" \
    DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$(id -u "$TARGET_USER")/bus}" \
    "$@"
}

run_as_user gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null || echo "Catatan: gsettings idle-delay gagal (jalankan manual di sesi GNOME user)."
run_as_user gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-timeout 0 2>/dev/null || true
run_as_user gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-timeout 0 2>/dev/null || true
run_as_user gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-ac-type 'nothing' 2>/dev/null || true
run_as_user gsettings set org.gnome.settings-daemon.plugins.power sleep-inactive-battery-type 'nothing' 2>/dev/null || true
run_as_user gsettings set org.gnome.desktop.screensaver lock-enabled false 2>/dev/null || true
run_as_user gsettings set org.gnome.desktop.screensaver ubuntu-lock-on-suspend false 2>/dev/null || true

echo ""
echo "Instalasi selesai."
echo "Lokasi aplikasi : $APP_PATH"
echo "Shortcut desktop: $DESKTOP_FILE"
echo "Autorun GNOME   : $AUTOSTART_FILE"
echo "Auto-login GDM  : $TARGET_USER (via $GDM_CUSTOM)"
echo "Sleep/suspend   : dinonaktifkan (systemd mask + gsettings best-effort)"
echo ""
echo "Untuk menjalankan manual:"
echo "  cd \"$APP_PATH\""
echo "  source \"$VENV_DIR/bin/activate\""
echo "  python main.py"
echo ""
echo "Catatan:"
echo "- Pastikan kamera/sumber video di resources/config.yaml sesuai dengan mesin Linux."
echo "- File model/video besar diambil via Git LFS. Jika model belum lengkap, jalankan: git lfs pull"
echo "- Jika memakai GPU, sesuaikan package torch/ultralytics dan set device di config."
echo "- Autorun dibuat lewat ~/.config/autostart, sehingga juga muncul di 'Startup Applications' (gnome-session-properties)."
echo "- Reboot diperlukan agar auto-login GDM dan mask sleep/suspend berlaku penuh."
echo "- Jika gsettings gagal saat instalasi via SSH/non-GUI, jalankan perintah gsettings tersebut saat login ke sesi GNOME user."
