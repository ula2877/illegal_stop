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

echo "==> [1/7] Cek OS & package manager"
if ! command -v apt-get >/dev/null 2>&1; then
  echo "Script ini dibuat untuk distro berbasis Debian/Ubuntu (apt-get)."
  echo "Silakan install dependensi manual jika memakai distro lain."
fi

echo "==> [2/7] Install dependensi sistem (butuh sudo)"
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

echo "==> [3/7] Inisialisasi Git LFS"
git lfs install

echo "==> [4/7] Clone repository"
if [ -d "$APP_DIR/.git" ]; then
  echo "Folder $APP_DIR sudah ada, melakukan git pull..."
  git -C "$APP_DIR" pull
  git -C "$APP_DIR" lfs pull
else
  git clone "$REPO_URL" "$APP_DIR"
  git -C "$APP_DIR" lfs pull
fi

cd "$APP_DIR"

echo "==> [5/7] Buat virtual environment"
if [ ! -d "$VENV_DIR" ]; then
  $PYTHON_BIN -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

echo "==> [6/7] Upgrade pip dan install dependensi Python"
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt

APP_PATH="$(pwd)"
DESKTOP_FILE="$HOME/Desktop/illegal-stop-detection.desktop"
AUTOSTART_DIR="$HOME/.config/autostart"
AUTOSTART_FILE="$AUTOSTART_DIR/illegal-stop-detection.desktop"
ICON_PATH="$APP_PATH/resources/images/icon.png"
EXEC_CMD="/bin/bash -c 'cd \"$APP_PATH\" && source \"$APP_PATH/$VENV_DIR/bin/activate\" && python main.py'"

echo "==> [7/8] Buat shortcut desktop"
mkdir -p "$HOME/Desktop"
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
# Tandai trusted di GNOME (Ubuntu 22); abaikan jika gio tidak tersedia / gagal
gio set "$DESKTOP_FILE" metadata::trusted true 2>/dev/null || true

echo "==> [8/8] Buat autorun GNOME (Startup Applications)"
mkdir -p "$AUTOSTART_DIR"
cp "$DESKTOP_FILE" "$AUTOSTART_FILE"
chmod +x "$AUTOSTART_FILE"

echo ""
echo "Instalasi selesai."
echo "Lokasi aplikasi : $APP_PATH"
echo "Shortcut desktop: $DESKTOP_FILE"
echo "Autorun GNOME   : $AUTOSTART_FILE"
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
