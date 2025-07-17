import glob
import logging
import os
from pathlib import Path
import random
import subprocess
import re
import sys
import threading
import time
from typing import List
import unicodedata


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path


# 全局日志配置（放在文件开头）
LOG_FILE = "/var/log/sj_install.log"
TMP_FILE_PREFIX = "sj_temp_"
TIMEOUT_FILE = os.environ.get("TIMEOUT_FILE")
PARAM_FILE = os.environ.get("PARAM_FILE")


def setup_logging():
    """初始化日志配置"""
    logger = logging.getLogger()
    if logger.hasHandlers():
        # 清除现有处理器
        logger.handlers.clear()

    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.ERROR,
            format="%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s",
            filemode="a",
        )
    except Exception:
        logging.basicConfig(level=logging.ERROR)


def generate_temp_file() -> str:
    """
    Generate a unique temporary file path.
    Prefer /dev/shm if it exists and is writable, otherwise fallback to /tmp.
    Create an empty file to reserve the filename.
    Returns the full file path as a string.
    """
    # Choose temp directory: /dev/shm preferred if available and writable
    if os.path.isdir("/dev/shm") and os.access("/dev/shm", os.W_OK):
        tmpdir = "/dev/shm"
    else:
        tmpdir = "/tmp"

    # Generate unique filename with prefix, timestamp, and random number
    filename = f"{TMP_FILE_PREFIX}{int(time.time())}{random.randint(0, 32767)}"
    tmpfile = os.path.join(tmpdir, filename)
    return tmpfile


def write_temp_file(path, lines, mode="w"):
    """Write content to file.

    Args:
        path (str): File path.
        lines (list or dict): Lines to write.
        mode (str): 'w' for overwrite (default), 'a' for append.
    """

    if lines:
        with open(path, mode, encoding="utf-8") as f:
            if isinstance(lines, dict):
                for key, value in lines.items():
                    f.write(f"{key}={value}\n")
            elif isinstance(lines, list):
                for line in lines:
                    f.write(f"{line}\n")
            else:
                f.write(f"{line}\n")


# ==============================================================================
#    网络管理器	             常见服务名
#    NetworkManager	    NetworkManager.service
#    systemd-networkd	systemd-networkd.service
#    ifupdown	        networking.service（Debian/Ubuntu）
#    wicked	            wickedd.service, wicked.service（openSUSE）
#    network-scripts	    network.service（RHEL/CentOS 7）
#
#    其他网络服务	         常见服务名
#    dhclient            dhclient.service（Debian/Ubuntu）
#    dhcpcd              dhcpcd.service（Arch Linux、部分 Debian 派生版）
# ==============================================================================
def check_network_service(service_name):
    """
    检查指定的服务是否处于活动状态，例如 "systemd-networkd"、"NetworkManager"、"networking"

    返回值:
        bool: 如果服务处于活动状态，返回服务名称；或者返回None
    """
    cmd = ["systemctl", "is-active", "--quiet", service_name]

    try:
        # 使用 systemctl 检查服务状态
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            return service_name
    except Exception as e:
        logging.error(f"check_network_service， {service_name}) failed: {e}")

    return None


def get_network_service():
    """
    获取当前活动的网络服务

    返回值:
        str: 当前活动的网络服务名称
    """
    # 定义可能的网络服务名称
    services = ["NetworkManager", "networking", "wicked", "network", "systemd-networkd"]
    for service in services:
        if check_network_service(service):
            return service

    return None


def get_static_ip(nm_type):
    """
    检查是否配置了静态 IP，并返回 IP 地址；否则返回 None。

    参数:
        nm_type (str): 当前网络管理器的名称

    返回:
        str | None: 静态 IP 地址，或 None（未配置静态 IP）
    """

    try:
        if nm_type == "systemd-networkd":  # 服务器版
            for path in glob.glob("/etc/systemd/network/*.network"):
                with open(path) as f:
                    content = f.read()
                    # 如果启用了 DHCP，就不是静态 IP
                    if "DHCP=yes" in content:
                        continue
                        # 否则尝试找静态 IP 地址
                    match = re.search(r"Address=(\d+\.\d+\.\d+\.\d+)", content)
                    if match:
                        return match.group(1)

        elif nm_type == "NetworkManager":  # 桌面版
            for path in glob.glob("/etc/NetworkManager/system-connections/*"):
                if not os.path.isfile(path):
                    continue
                with open(path) as f:
                    content = f.read()
                if "ipv4" in content:
                    method = content["ipv4"].get("method", "")
                    address1 = content["ipv4"].get("address1", "")
                    if method == "manual" and address1:
                        ip = address1.split("/")[0]
                        return ip

        elif nm_type == "networking":  # Debian 系
            files = ["/etc/network/interfaces"] + glob.glob("/etc/network/interfaces.d/*")
            for path in files:
                if not os.path.isfile(path):
                    continue
                with open(path) as f:
                    content = f.read()
                    blocks = re.split(r"\n\s*\n", content)
                    for block in blocks:
                        if re.search(r"iface\s+\S+\s+inet\s+static", block):
                            match = re.search(r"address\s+(\d+\.\d+\.\d+\.\d+)", block)
                            if match:
                                return match.group(1)

        elif nm_type == "wicked":  # openSUSE
            for path in glob.glob("/etc/sysconfig/network/ifcfg-*"):
                with open(path) as f:
                    content = f.read()
                    if "BOOTPROTO='static'" in content or "BOOTPROTO=static" in content:
                        match = re.search(r"IPADDR='?(\d+\.\d+\.\d+\.\d+)'?", content)
                        if match:
                            return match.group(1)

        elif nm_type == "network":  # CentOS/RHEL legacy ifcfg
            for path in glob.glob("/etc/sysconfig/network-scripts/ifcfg-*"):
                with open(path) as f:
                    content = f.read()
                    if "BOOTPROTO=static" in content:
                        match = re.search(r"IPADDR=(\d+\.\d+\.\d+\.\d+)", content)
                        if match:
                            return match.group(1)

    except Exception as e:
        logging.error(f"get_static_ip({nm_type}) failed: {e}")

    return None


def check_dns() -> List[str]:
    """
    Retrieve DNS server IP addresses from /etc/resolv.conf
    """
    try:
        # Read /etc/resolv.conf and extract IPv4 DNS addresses
        with open("/etc/resolv.conf", "r") as f:
            return re.findall(r"nameserver (\d+\.\d+\.\d+\.\d+)", f.read())
    except Exception as e:
        logging.error(f"check_dns() failed: {e}")
        return []


# ==============================================================================
# functions to support read_util.py
# ==============================================================================
def init_time_out(value: int = 0) -> str:
    """
    init timeout value and set the evironment variable
    This function is used for testing purposes.
    """
    tempfile = generate_temp_file()
    with open(tempfile, "w") as tmp:
        tmp.write(f"current={value}\n")
        tmp.write("backup=999999\n")
    os.environ["TIMEOUT_FILE"] = tempfile
    global TIMEOUT_FILE
    TIMEOUT_FILE = tempfile  # Update global variable
    return tempfile


def get_time_out():
    """
    get timeout value from file
    """
    if not TIMEOUT_FILE:
        return 999999  # never timeout
    try:
        with open(TIMEOUT_FILE, "r") as f:
            for line in f:
                if line.startswith("current="):
                    return int(line.strip().split("=", 1)[1])
    except Exception:
        pass
    return 999999  # never timeout


def toggle_time_out():
    """
    switch timeout value
    """
    if not TIMEOUT_FILE:
        return  # exception handler
    curr, back = "999999", "60"
    try:
        with open(TIMEOUT_FILE, "r") as f:
            for line in f:
                if line.startswith("current="):
                    curr = line.strip().split("=", 1)[1]
                elif line.startswith("backup="):
                    back = line.strip().split("=", 1)[1]
    except Exception:
        pass
    with open(TIMEOUT_FILE, "w") as f:
        f.write(f"current={back}\nbackup={curr}\n")

    def do_erase():
        time.sleep(0.3)
        length = 3 + len(back)
        sequence = "\b" * length + " " * length + "\b" * length
        print(sequence, end="", flush=True)

    # print ^X and clean after 0.3s
    print(f"^X={back}", end="", flush=True)
    threading.Thread(target=do_erase, daemon=True).start()
    return int(back)


def clear_input():
    """
    Function to clear the input buffer (incl. Enter, spaces, etc.)
    """
    sys.stdout.write("\r\033[K")
    sys.stdout.flush()


def safe_backspace(prompt: str, response: str) -> str:
    if not response:
        return response
    # remove last character (handling multibyte is tricky in terminal)
    sys.stdout.write("\b \b")
    sys.stdout.flush()
    return response[:-1]


def get_display_width(char):
    """
    Calculate the display width of a character in the terminal
    """
    if char == "\t":
        return 4  # Tabs typically occupy 4 spaces

    # Control characters are usually not displayed
    if unicodedata.category(char).startswith("C"):
        return 0

    # East Asian character width determination
    east_asian_width = unicodedata.east_asian_width(char)
    if east_asian_width in ("F", "W"):  # Fullwidth, Wide
        return 2
    elif east_asian_width in ("H", "Na", "N"):  # Halfwidth, Narrow, Neutral
        return 1
    elif east_asian_width == "A":  # Ambiguous - It is 1 in most terminals
        return 1
    else:
        return 1


def safe_backspace(response: str) -> str:
    if not response:
        return response

    # check if multibyte character
    last_char = response[-1]
    new_response = response[:-1]
    display_width = get_display_width(last_char)
    for _ in range(display_width):
        sys.stdout.write("\b \b")  # ASCII: Use backspace-space-backspace sequence

    sys.stdout.flush()
    return new_response


def print_prompt_for_raw_mode(prompt):
    """
    将提示符格式化为适合 raw 模式的格式
    在 raw 模式下，需要使用 \r\n 来正确换行
    """
    prompt = prompt.replace("\n", "\r\n")
    print(f"{prompt} ", end="", flush=True)


# ==============================================================================
# functions to support auto run parameter
# ==============================================================================
def get_param_fixip():
    """
    get parameter value from file
    """
    if not PARAM_FILE:
        return 0  # no value
    try:
        with open(PARAM_FILE, "r") as f:
            for line in f:
                if line.startswith("ip_last_octet="):
                    return int(line.strip().split("=", 1)[1])
    except Exception:
        pass
    return 0  # no value


# 在程序启动时调用
setup_logging()
