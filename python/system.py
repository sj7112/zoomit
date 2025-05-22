import glob
import logging
import os
import subprocess
import re
from typing import Callable, Any
from msg_handler import error

# 全局日志配置（放在文件开头）
LOG_FILE = "/var/log/sj_pkg_error.log"


def setup_logging():
    """初始化日志配置"""
    try:
        os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
        logging.basicConfig(
            filename=LOG_FILE,
            level=logging.ERROR,
            format="%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s",
            filemode="a",
        )
    except Exception:
        # 如果无法写入日志文件，则输出到控制台
        logging.basicConfig(level=logging.ERROR)


def confirm_action(prompt: str, callback: Callable[..., Any] = None, *args: Any, **kwargs: Any) -> int:
    """
    确认操作函数（带回调）

    参数:
        prompt: 提示消息
        callback: 回调函数。为 None 直接返回 0
        *args: 回调函数的位置参数
        **kwargs: 可包含取消提示信息 msg=xxx，以及回调函数的关键字参数

    返回:
        0: 用户确认执行
        1: 用户取消操作
        2: 输入错误
    """
    cancel_msg = kwargs.pop("msg", "操作已取消")

    response = input(f"{prompt} [Y/n] ").strip().lower()
    if response in ("", "y", "yes"):
        if callback:
            callback(*args)  # 执行回调函数
        return 0
    elif response in ("n", "no"):
        error(cancel_msg)
        return 1
    else:
        error(cancel_msg)
        return 2


def run_cmd(sudo_cmd, cmd, pattern=""):
    """
    执行系统命令并返回结果，支持正则匹配提取。

    参数:
        cmd (str 或 list): 要执行的命令，可以是字符串（如 "ls -l"）或列表（如 ["ls", "-l"]）。
        pattern (str): 可选，正则表达式模式，用于从命令输出中提取特定内容。

    返回:
        str:
            - 如果提供了 pattern，则返回匹配的第一个分组内容；
            - 如果未提供 pattern，则返回完整的命令输出；
            - 如果命令执行失败或未匹配到 pattern，则返回空字符串 ""。

    示例:
        # 获取当前用户
        user = run_cmd(sudo_cmd, "whoami")

        # 提取 IP 地址
        ip = run_cmd(sudo_cmd, "ip -o route get 1", r"src (\d+\.\d+\.\d+\.\d+)")
    """
    # 如果 cmd 是字符串，则用 split() 转换为列表
    if isinstance(cmd, str):
        cmd = cmd.split()

    # 如果需要 sudo，则在命令前添加 sudo
    if sudo_cmd:
        cmd.insert(0, sudo_cmd)

    # 执行命令并捕获输出
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if result.returncode != 0:
        return ""  # 命令失败，返回空字符串
    # 如果提供了正则模式，尝试匹配
    if pattern:
        match = re.search(pattern, result.stdout)
        if match:
            return match.group(1)  # 返回匹配的第一个分组
        else:
            return ""  # 未匹配到内容，返回空字符串
    else:
        return result.stdout  # 未提供正则模式，返回完整输出


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
def check_network_service(sudo_cmd, service_name):
    """
    检查指定的服务是否处于活动状态，例如 "systemd-networkd"、"NetworkManager"、"networking"

    返回值:
        bool: 如果服务处于活动状态，返回服务名称；或者返回None
    """
    cmd = ["systemctl", "is-active", "--quiet", service_name]

    # 如果需要 sudo，则在命令前添加 sudo
    if sudo_cmd:
        cmd.insert(0, sudo_cmd)

    try:
        # 使用 systemctl 检查服务状态
        result = subprocess.run(cmd, check=False)
        if result.returncode == 0:
            return service_name
    except Exception as e:
        logging.error(f"check_network_service({sudo_cmd}， {service_name}) failed: {e}")

    return None


def get_network_service(sudo_cmd):
    """
    获取当前活动的网络服务

    返回值:
        str: 当前活动的网络服务名称
    """
    # 定义可能的网络服务名称
    services = ["systemd-networkd", "NetworkManager", "networking", "wicked", "network"]
    for service in services:
        if check_network_service(sudo_cmd, service):
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
                    if "DHCP=no" in content:
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
