from datetime import datetime
import glob
import logging
import os
import shutil
import subprocess
import re
import sys

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from typing import Callable, Any, List
from msg_handler import _mf, error, exiterr, info, warning

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


def confirm_action(prompt: str, callback: Callable[..., Any] = None, *args: Any, **kwargs: Any) -> Any:
    """
    Confirmation function with callback support

    Args:
        prompt: Prompt message
        callback: Callback function. Returns 0 directly if None
        *args: Positional arguments for callback function
        **kwargs: Can contain cancellation messages and callback function keyword arguments

    Returns:
        0: User confirmed
        1: User cancelled
        2: User interrupt
        3: System Exception
    """

    try:
        # Priority: nomsg > msg > default value
        no_msg = kwargs.pop("nomsg", kwargs.pop("msg", _mf("操作已取消")))
        # Priority: errmsg > msg > default value
        err_msg = kwargs.pop("errmsg", kwargs.pop("msg", _mf("输入错误，请输入 Y 或 N")))

        # Get default and exit parameters
        default = kwargs.pop("default", "Y")  # default value = Y
        exit = kwargs.pop("exit", True)  # default = exit immediately

        # Set prompt suffix based on default value
        if default.upper() == "Y":
            prompt_suffix = "[Y/n]"
            default_choice = "y"
        else:
            prompt_suffix = "[y/N]"
            default_choice = "n"

        while True:
            response = input(f"{prompt} {prompt_suffix} ").strip().lower()
            if response == "":
                response = default_choice

            if response in ("y", "yes"):
                if callback:
                    return callback(*args)  # Execute callback function
                return 0
            elif response in ("n", "no"):
                print(no_msg)  # Output message for 'no' choice
                return 1
            else:
                print(err_msg)  # Output error message
                if not exit:
                    continue  # Continue loop without returning
                return 2

    except KeyboardInterrupt:
        print("\n")
        print(_mf("操作已取消"))
        return 2
    except Exception as e:
        print(_mf(r"输入处理出错: {}", e))
        return 3


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
    services = ["systemd-networkd", "NetworkManager", "networking", "wicked", "network"]
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


def install_packages():
    """安装所需软件包"""

    packages = [
        "typer",  # CLI 框架
        "ruamel.yaml",  # YAML 处理
        "requests",  # HTTP 库
        "iso3166",  # 查国家名称
        # "pydantic",   # 数据验证
        # "pathlib"     # 路径处理（Python 3.4+ 内置，但确保可用）
    ]

    info("安装所需 Python 包...")

    # 安装每个包
    for package in packages:
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", package],
                check=True,
                capture_output=True,
            )
            info(f"{package} 安装成功")
        except subprocess.CalledProcessError as e:
            warning(f"{package} 安装失败")
            print(f"错误详情: {e}")

    def install_base_pkg(self, lnx_cmd: str, package_name: Optional[str] = None) -> bool:
        """
        安装基础包

        Args:
            lnx_cmd: 要检查的命令名
            package_name: 包名（如果与命令名不同）

        Returns:
            bool: 安装是否成功
        """
        # 检查命令是否存在
        if shutil.which(lnx_cmd):
            self.info(f"'{lnx_cmd}' 已安装")
            return True

        # 如果没有指定包名，则使用命令名
        if package_name is None:
            package_name = lnx_cmd

        self.info(f"自动安装 '{lnx_cmd}' (包名: {package_name})...")

        # 检查包管理器是否可用
        if self.distro_pm == "unknown":
            self.exiterr("无法检测到支持的包管理器")

        # 更新包缓存（某些发行版需要）
        self._update_package_cache()

        # 获取安装命令
        cmd = self._get_install_command(package_name)

        # 执行安装命令
        success, output = self.cmd_exec(cmd)

        # 记录时间
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 再次检查是否安装成功
        if not success or not shutil.which(lnx_cmd):
            error_msg = f"{lnx_cmd} 安装失败，请手动安装，日志: {self.log_file} [{current_time}]"
            self.exiterr(error_msg)
            return False
        else:
            success_msg = f"{lnx_cmd} 安装成功，日志: {self.log_file} [{current_time}]"
            self.success(success_msg)
            return True

    def install_multiple_packages(self, packages: List[str]) -> bool:
        """
        批量安装多个包

        Args:
            packages: 包列表，可以是字符串或元组(命令名, 包名)

        Returns:
            bool: 所有包是否都安装成功
        """
        all_success = True

        for pkg in packages:
            if isinstance(pkg, tuple):
                cmd_name, pkg_name = pkg
                success = self.install_base_pkg(cmd_name, pkg_name)
            else:
                success = self.install_base_pkg(pkg)

            if not success:
                all_success = False

        return all_success


# 在程序启动时调用
setup_logging()
