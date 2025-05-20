import platform


def detect_os_arch():
    # Normalize OS name
    os_map = {
        "linux": "linux",
        "darwin": "darwin",
        "windows": "windows",  # Add if you want to support Windows
    }
    system = platform.system().lower()
    os_name = os_map.get(system)
    if os_name is None:
        raise RuntimeError(f"Unsupported OS: {system}")

    # Normalize architecture
    arch_map = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    machine = platform.machine().lower()
    arch = arch_map.get(machine)
    if arch is None:
        raise RuntimeError(f"Unsupported architecture: {machine}")

    return os_name, arch
