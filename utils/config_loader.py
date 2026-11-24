import os
import time
import yaml

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_config_cache = None
_config_cache_time = 0
_config_ttl = 2.0 


def load_config(path="resources/config.yaml"):
    global _config_cache, _config_cache_time

    now = time.time()
    if _config_cache is not None and (now - _config_cache_time) < _config_ttl:
        return _config_cache

    config_path = os.path.join(BASE_DIR, path)

    with open(config_path, "r") as f:
        config = yaml.safe_load(f) or {}

    try:
        cameras = config.get("cameras", {})
        if cameras:
            for cam_name, cam_cfg in cameras.items():
                if not isinstance(cam_cfg, dict):
                    continue
                source = cam_cfg.get("source_path")

                if isinstance(source, str):
                    if not source.startswith(("rtsp://", "http://", "https://")):
                        if not os.path.isabs(source):
                            cam_cfg["source_path"] = os.path.join(BASE_DIR, source)
    except Exception as e:
        print(f"[Config] Warning: failed to normalize camera paths: {e}")

    _config_cache = config
    _config_cache_time = now
    return config


def reload_config(path="resources/config.yaml"):
    global _config_cache, _config_cache_time
    _config_cache = None
    _config_cache_time = 0
    return load_config(path)
