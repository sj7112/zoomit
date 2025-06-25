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
    env_nw = {}

    def save_env_nw(self, backup=True):
        """
        retrieve network parameters, save to .env file
        """
        self.CONF_DIR.mkdir(parents=True, exist_ok=True)
        evn_file = os.path.join(self.CONF_DIR, ".env")

        # backup original config file
        backup_file = f"{evn_file}.bak"
        if backup and not os.path.exists(backup_file):
            shutil.copy2(evn_file, backup_file)

        # write to config file
        with open(evn_file, "w", encoding="utf-8") as f:
            f.write("#=network\n\n")
            # 写入网络参数
            for key, value in self.env_nw.items():
                f.write(f"{key}={value}\n")

    # ==============================================================================
    # (1) Check Network Environment
    # ==============================================================================
    def check_env_nw(self):
        """
        检查服务器是否使用静态IP，并提供交互式选项：
            - 如果用户选择将网络改为静态IP，要求输入静态IP地址（最后一段 1-255，且不能与网关相同）
            - env_nw (dict): 包含网络配置信息的字典
        """
        ENV_NW = os.path.join(self.CONF_DIR, ".env")
        self.env_nw = read_env_file(ENV_NW, "network")

        # 提取主要网络接口
        main_interface = cmd_ex_pat("ip -o route get 1", r"dev (\S+)")
        self.env_nw["MAIN_IFACE"] = main_interface

        # 提取当前IP地址
        curr_ip = cmd_ex_pat(f"ip -4 addr show {main_interface}", r"inet (\d+\.\d+\.\d+\.\d+)/")
        self.env_nw["CURR_IP"] = curr_ip

        # 提取网关
        gateway = cmd_ex_pat("ip route show default", r"default via (\d+\.\d+\.\d+\.\d+)")
        self.env_nw["GATEWAY"] = gateway

        # 检查是否有DHCP客户端运行
        # pgrep -f "dhclient|dhcpcd|nm-dhcp|NetworkManager.*dhcp"
        dhcp_client = bool(cmd_ex_str(["pgrep", "-f", "dhclient|dhcpcd|nm-dhcp|NetworkManager.*dhcp"]))
        self.env_nw["DHCP_CLIENT"] = dhcp_client

        # 调用 dmidecode 获取 system-manufacturer
        manufacturer = is_cloud_manufacturer(cmd_ex_str("dmidecode -s system-manufacturer"))
        if manufacturer:
            self.env_nw["IS_CLOUD"] = manufacturer.strip()

        # 新安装系统，是这几种之一：systemd-networkd、NetworkManager、networking[ifupdown]、wicked、network[network-scripts]
        nm_type = get_network_service()
        self.env_nw["CURR_NM"] = nm_type
        if not dhcp_client:
            self.env_nw["STATIC_IP"] = get_static_ip(nm_type)
            if self.env_nw["STATIC_IP"]:
                if curr_ip == self.env_nw["STATIC_IP"]:
                    self.env_nw["HAS_STATIC"] = "active"  # 已生效
                else:
                    self.env_nw["HAS_STATIC"] = "pending"  # 待生效

        # 获取DNS服务器(为空时，采取默认值)
        if dns_servers := check_dns():
            self.env_nw["DNS_SERVERS"] = dns_servers

    # ==============================================================================
    # (2) Update IP
    # ==============================================================================
    def setup_octet(self):
        """
        Interactive setup for static IP
        """
        env_nw = self.env_nw
        # 提示用户输入静态IP地址的最后一段
        curr_ip = env_nw.get("CURR_IP", "")
        gateway = env_nw.get("GATEWAY", "")
        curr_last_octet = curr_ip.split(".")[-1] if curr_ip else "1"

        ip_parts = curr_ip.split(".") if curr_ip else []
        if len(ip_parts) < 3:
            print("当前 IP 地址无效")
            return 3

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
                return 2

    # ==============================================================================
    # 主程序
    # ==============================================================================
    def fix_ip(self):
        """
        是否需要固定IP
        返回值：
            0: 需要改固定IP
            1: 不需要改固定IP
            2: 用户终止操作
            3: 异常终止
        """
        # 初始化全局变量
        self.check_env_nw()

        # 云服务器无需设置固定IP
        env_nw = self.env_nw
        if env_nw.get("IS_CLOUD"):
            info(f"{env_nw['IS_CLOUD']} 云服务器无需设置固定IP")
            return 1

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
