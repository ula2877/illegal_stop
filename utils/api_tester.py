import requests
import psutil
import json
import os
import datetime
import socket
import platform
from utils.config_loader import load_config, BASE_DIR

LICENSE_URL = "https://auth.elmechtechnology.com/check_license.php"
UPLOAD_URL = "https://auth.elmechtechnology.com/upload_api.php"
OVERLOAD_URL = "https://auth.elmechtechnology.com/system_overload.php"

# def get_real_mac():
#     for iface, addrs in psutil.net_if_addrs().items():
#         for addr in addrs:
#             if addr.family.name == "AF_LINK":
#                 mac = addr.address
#                 if mac and mac != "00:00:00:00:00:00":
#                     return mac.upper()
#     return None

def get_mac_psutil():
    """Get MAC using psutil (works on Windows & Linux)"""
    for iface, addrs in psutil.net_if_addrs().items():

        # skip virtual interfaces
        if iface.lower().startswith(("lo", "docker", "veth", "br-", "vmnet", "vbox")):
            continue

        for addr in addrs:
            if addr.family in (psutil.AF_LINK, getattr(socket, "AF_PACKET", None)):
                mac = addr.address

                if mac and mac != "00:00:00:00:00:00":
                    return mac.upper()

    return None


def get_mac_linux_sys():
    """Fallback khusus Linux"""
    try:
        for iface in os.listdir("/sys/class/net/"):

            if iface.startswith(("lo", "docker", "veth", "br-")):
                continue

            path = f"/sys/class/net/{iface}/address"

            if os.path.exists(path):
                with open(path) as f:
                    mac = f.read().strip()

                    if mac != "00:00:00:00:00:00":
                        return mac.upper()
    except:
        pass

    return None


def get_real_mac():
    """Adaptive MAC getter (Windows + Linux)"""

    mac = get_mac_psutil()
    if mac:
        return mac

    if platform.system() == "Linux":
        mac = get_mac_linux_sys()
        if mac:
            return mac

    return None


def test_api_request(api_url: str, product_key: str, api_key: str = ""):
    logs = []

    def log(msg):
        logs.append(msg)

    # ========================
    # Validation
    # ========================
    if not api_url:
        log("ERROR: API URL kosong")
        return logs

    if not product_key:
        log("ERROR: Product key kosong")
        return logs

    mac = get_real_mac()
    if not mac:
        log("ERROR")
        # log("ERROR: Gagal mendapatkan MAC Address")
        return logs

    log(f"MAC Address: {mac}")

    # ========================
    # STEP 1 - License check
    # ========================
    # log("Checking license...")

    license_payload = {
        "mac_address": mac,
        "product_key": product_key
    }

    try:
        res = requests.post(LICENSE_URL, json=license_payload, timeout=10)
        data = res.json()

        if str(data.get("status", "")).lower() in ("ok", "valid", "success", "true", "1"):
            log("License valid")
        else:
            log("License invalid")
            return logs

    except Exception as e:
        log(f"ERROR: License check failed → {e}")
        return logs

    # ========================
    # STEP 2 - Main API
    # ========================
    log("Sending dummy detection event...")

    cfg = load_config()
    kode_jpl = cfg.get("kode_jpl", "UNKNOWN")

    data_payload = {
        "jpl": kode_jpl,
        "zone": "HIJAU",
        "vehicle": "R4"
    }

    headers = {}
    if api_key:
        headers["x-api-key"] = api_key

    image_path = os.path.join(BASE_DIR, "resources", "tester.jpg")

    if not os.path.exists(image_path):
        log(f"ERROR: File not found → {image_path}")
        return logs

    try:
        with open(image_path, "rb") as f:
            files = {
                "file": (os.path.basename(image_path), f, "image/jpeg")
            }

            resp = requests.post(
                api_url,
                headers=headers,
                data=data_payload,
                files=files,
                timeout=(15, 60)
            )

        log(f"API Status Code: {resp.status_code}")

        try:
            data = resp.json()
            log("API Response:")
            log(json.dumps(data, indent=2))
        except Exception:
            log("Raw Response:")
            log(resp.text)

    except requests.exceptions.Timeout:
        log("ERROR: API request timeout")
    except Exception as e:
        log(f"ERROR: API request failed → {e}")


    try:
        with open(image_path, "rb") as f:
            kode_jpl = cfg.get("kode_jpl", "UNKNOWN")
            lokasi = cfg.get("lokasi", "UNKNOWN")
            alamat = cfg.get("alamat", "UNKNOWN")

            sekarang = datetime.datetime.now()
            formatted_now = sekarang.strftime("%d-%m-%Y %H:%M:%S")

            payload = {
                "jenis_kendaraan": "TESTER",
                "kode_jpl": kode_jpl,
                "lokasi": lokasi,
                "alamat": alamat,
                "tanggal": formatted_now.split(" ")[0],
                "jam": formatted_now.split(" ")[1],
                "zona": "merah"
            }

            resp = requests.post(UPLOAD_URL, data=payload, files={"image": f}, timeout=10)
            log(f"API Status Code: {resp.status_code}")
    except Exception as e:
        log(f"ERROR: Upload failed: {e}")

    return logs
