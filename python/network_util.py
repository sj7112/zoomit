#!/usr/bin/env python3

from pathlib import Path
import os
import shutil
import sys
import time


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from file_util import read_env_file
from cmd_handler import cmd_ex_str, cmd_ex_pat
from system import confirm_action, get_network_service, get_static_ip, check_dns
from msg_handler import _mf, exiterr, info, string
from debug_tool import print_array


def is_cloud_manufacturer(manufacturer):
    # 常见云厂商关键词列表（可扩展）
    cloud_keywords = [
        "Amazon",
        "Google",
        "Microsoft Azure",
        "Alibaba Cloud",
        "Tencent Cloud",
        "Huawei",
        "Oracle Cloud",
        "IBM Cloud",
        "DigitalOcean",
        "Linode",
    ]
    if manufacturer:
        for keyword in cloud_keywords:
            if keyword.lower() in manufacturer.lower():
                return manufacturer
    return None


class NetworkSetup:
    """
    Network Setup class
    """

    # 设置默认路径
    PARENT_DIR = Path(__file__).parent.parent.resolve()
    CONF_DIR = (PARENT_DIR / "config/network").resolve()
    env_network = {}

    def save_env_nw(self, backup=True):
        """
        retrieve .env_network parameters, save to .env file
        """
        evn_file = os.path.join(self.CONF_DIR, ".env")
        if backup:
            shutil.copy2(evn_file, f"{evn_file}.bak")

        with open(evn_file, "w", encoding="utf-8") as f:
            f.write("#=network\n\n")
            # 写入网络参数
            for key, value in self.env_network.items():
                f.write(f"{key}={value}\n")

    def count_down(self):
        """倒计时提醒"""
        env_nw = self.env_network
        # 设置环境变量
        duration = 5
        iface = env_nw["MAIN_IFACE"]
        ip_addr = env_nw["STATIC_IP"]

        # ANSI 颜色
        BG_BLUE = "\033[44m"
        NC = "\033[0m"  # 重置颜色

        info(f"{duration}秒后修改网络配置：{ip_addr} (接口 {iface})，请准备好重连。按 Ctrl+C 取消")

        for i in range(duration, 0, -1):
            print(f"{BG_BLUE}  {i} 秒 {NC}", end="\r", flush=True)
            time.sleep(0.5)

        print(f"{BG_BLUE}  0 秒 {NC}")

    # ==============================================================================
    # (1) Check Network Environment
    # ==============================================================================
    def check_ip(self):
        """
        检查服务器是否使用静态IP，并提供交互式选项：
        - 如果用户选择将网络改为静态IP，要求输入静态IP地址（最后一段 1-255，且不能与网关相同）

        返回值：
            env_network (dict): 包含网络配置信息的字典
        """
        ENV_SYSTEM = os.path.join(self.CONF_DIR, ".env")
        env_network = read_env_file(ENV_SYSTEM, "network")

        # 提取主要网络接口
        main_interface = cmd_ex_pat("ip -o route get 1", r"dev (\S+)")
        env_network["MAIN_IFACE"] = main_interface

        # 提取当前IP地址
        curr_ip = cmd_ex_pat(f"ip -4 addr show {main_interface}", r"inet (\d+\.\d+\.\d+\.\d+)/")
        env_network["CURR_IP"] = curr_ip

        # 提取网关
        gateway = cmd_ex_pat("ip route show default", r"default via (\d+\.\d+\.\d+\.\d+)")
        env_network["GATEWAY"] = gateway

        # 检查是否有DHCP客户端运行
        # pgrep -f "dhclient|dhcpcd|nm-dhcp|NetworkManager.*dhcp"
        dhcp_client = bool(cmd_ex_str(["pgrep", "-f", "dhclient|dhcpcd|nm-dhcp|NetworkManager.*dhcp"]))
        env_network["DHCP_CLIENT"] = dhcp_client

        # 调用 dmidecode 获取 system-manufacturer
        manufacturer = is_cloud_manufacturer(cmd_ex_str("dmidecode -s system-manufacturer"))
        if manufacturer:
            env_network["IS_CLOUD"] = manufacturer.strip()

        # 新安装系统，是这几种之一：systemd-networkd、NetworkManager、networking[ifupdown]、wicked、network[network-scripts]
        nm_type = get_network_service()
        env_network["CURR_NM"] = nm_type
        if not dhcp_client:
            env_network["STATIC_IP"] = get_static_ip(nm_type)
            if env_network["STATIC_IP"]:
                if curr_ip == env_network["STATIC_IP"]:
                    env_network["HAS_STATIC"] = "active"  # 已生效
                else:
                    env_network["HAS_STATIC"] = "pending"  # 待生效

        # 获取DNS服务器(为空时，采取默认值)
        if dns_servers := check_dns():
            env_network["DNS_SERVERS"] = dns_servers

        self.env_network = env_network
        print_array(env_network)
        return env_network

    # ==============================================================================
    # (2) Update IP
    # ==============================================================================
    def setup_octet(self):
        """
        Interactive setup for static IP
        """
        env_nw = self.env_network
        # 提示用户输入静态IP地址的最后一段
        curr_ip = env_nw.get("CURR_IP", "")
        gateway = env_nw.get("GATEWAY", "")
        curr_last_octet = curr_ip.split(".")[-1] if curr_ip else "1"

        ip_parts = curr_ip.split(".") if curr_ip else []
        if len(ip_parts) < 3:
            print("当前 IP 地址无效")
            return 1

        while True:
            try:
                prompt = _mf(r"请输入静态IP地址的最后一段 (1-255) [默认: {}]: ", curr_last_octet)
                new_last_octet = input(prompt).strip() or curr_last_octet  # 默认=当前值

                if not new_last_octet.isdigit():
                    print(_mf("请输入数字"))
                    continue

                octet_num = int(new_last_octet)
                if not (1 <= octet_num <= 255):
                    print(_mf("输入必须在 1~255 之间"))
                    continue

                if gateway and new_last_octet == gateway.split(".")[-1]:
                    print(_mf("输入的静态IP地址不能与网关相同，请重新输入"))
                    continue

                # 构造新的静态IP地址
                env_nw["STATIC_IP"] = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.{new_last_octet}"
                env_nw["HAS_STATIC"] = "pending"  # 待生效
                return 0

            except KeyboardInterrupt:
                print(_mf("\n操作已取消"))
                return 1

    def fix_ip(self):
        """
        是否需要固定IP
        返回值：
            bool: True表示需要设置静态IP，False表示不需要
        """
        # 初始化全局变量
        self.check_ip()
        env_nw = self.env_network

        # 云服务器无需设置固定IP
        if env_nw.get("IS_CLOUD"):
            info(f"{env_nw['IS_CLOUD']} 云服务器无需设置固定IP")
            return False

        # 根据不同情况设置提示信息
        if env_nw.get("STATIC_IP"):
            prompt = _mf("检测到服务器已配置静态IP，是否调整IP？")
        elif env_nw.get("DHCP_CLIENT") == True:
            prompt = _mf("检测到服务器使用动态IP，是否改为静态IP？")
        else:
            prompt = _mf("检测到服务器可能使用静态IP，是否调整IP？")

        # 提示用户是否要改IP配置
        no_msg = _mf("用户选择不修改网络配置")
        retVal = confirm_action(prompt, self.setup_octet, nomsg=no_msg)

        self.save_env_nw()
        return retVal

    # ==============================================================================
    # (3) Configure Network System
    # ==============================================================================

    def config_nmcli(self):
        """配置静态IP（NetworkManager）"""
        env_nw = self.env_network

        # 检查 nmcli 是否存在
        if not shutil.which("nmcli"):
            exiterr("nmcli 未安装或不可用，请先安装 NetworkManager 命令行工具")

        # 设置环境变量
        iface = env_nw["MAIN_IFACE"]  # 网络接口名
        con_name = f"static-{iface}"  # 连接名称，NetworkManager 中标识配置的名字
        ip_addr = env_nw["STATIC_IP"]  # IP 地址（不含掩码）
        prefix = env_nw.get("PREFIX", "24")  # 子网掩码长度，默认24
        gateway = env_nw["GATEWAY"]  # 网关
        dns = env_nw["DNS_SERVERS"]  # DNS 服务器，多个用空格隔开

        # 1. 检查连接是否存在
        # nmcli connection show "$CON_NAME" &>/dev/null
        result = cmd_ex_str(["nmcli", "connection", "show", con_name])
        if not result:
            # 连接不存在，创建新连接
            cmd_ex_str(f'nmcli connection add type ethernet ifname "{iface}" con-name "{con_name}"')

        # 2. 修改连接为静态 IP
        cmd_ex_str(
            f"""nmcli connection modify "{con_name}"
            ipv4.addresses "{ip_addr}/{prefix}"
            ipv4.gateway "{gateway}"
            ipv4.dns "{dns}"
            ipv4.method manual
            connection.autoconnect yes"""
        )

        # 3. 激活连接
        self.count_down()  # 倒计时提醒
        result = cmd_ex_str(f'nmcli connection up "{con_name}"')
        if not result:
            exiterr("连接激活失败，请检查网络并尝试重新连接")

    # ifupdown_to_systemd_networkd() {
    #     # 安装systemd-networkd
    #     install_base_pkg "systemd" # 安装systemd-networkd

    #     setup_systemd_networkd # 生成配置文件
    #     setup_switch_network   # 创建切换脚本

    #     count_down # 倒计时提醒
    #     $SUDO_CMD setsid /tmp/switch_network.sh </dev/null &

    # }
    # ==============================================================================
    # 主程序
    # ==============================================================================
    def configure_ip(self):
        result = self.fix_ip()  # 设置环境配置文件
        env_nw = self.env_network

        exiterr(f"return value={result}")

        curr_nm = env_nw.get("CURR_NM")
        match curr_nm:
            case "NetworkManager":
                info("NetworkManager 正在运行")
                self.config_nmcli()
            case "networking":
                info("ifupdown 正在运行")
                self.ifupdown_to_systemd_networkd()
            case "wicked":
                info("wicked 正在运行")
                # 可加 self.wicked_to_systemd_networkd()
            case "network":
                info("network-scripts 正在运行")
                # 可加 self.network_to_systemd_networkd()
            case "systemd-networkd":
                info("systemd-networkd 正在运行")
                self.config_default()
            case _:
                exiterr("未知网络管理器，无法配置静态IP")
