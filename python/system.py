import glob
import logging
import os
from pathlib import Path
import subprocess
import re
import sys


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path


# 全局日志配置（放在文件开头）
LOG_FILE = "/var/log/sj_install.log"


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


def check_dns():
    """
    获取DNS服务器，不存在返回空串
    """
    try:
        # 获取DNS服务器(为空时，采取默认值)
        with open("/etc/resolv.conf", "r") as f:
            dns_servers = re.findall(r"nameserver (\d+\.\d+\.\d+\.\d+)", f.read())
            return " ".join(dns_servers)
    except Exception as e:
        logging.error(f"check_dns() failed: {e}")

    return ""


# 在程序启动时调用
setup_logging()
