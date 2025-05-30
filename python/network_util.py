#!/usr/bin/env python3

import glob
from pathlib import Path
import subprocess
import re
import os
import sys

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from file_util import read_env_file
from system import get_network_service, get_static_ip, run_cmd, check_dns

# 设置默认路径
PARENT_DIR = Path(__file__).parent.parent.resolve()
CONF_DIR = (PARENT_DIR / "config").resolve()


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


def check_ip(sudo_cmd):
    """
    检查服务器是否使用静态IP，并提供交互式选项：
    - 如果用户选择将网络改为静态IP，要求输入静态IP地址（最后一段 1-255，且不能与网关相同）
    参数：
        sudo_cmd (str): sudo 命令前缀（如 "sudo" 或 ""）
    返回值：
        env_network (dict): 包含网络配置信息的字典
    """
    ENV_SYSTEM = os.path.join(CONF_DIR, ".env")
    env_network = read_env_file(ENV_SYSTEM, "network")

    # 提取主要网络接口
    main_interface = run_cmd(sudo_cmd, "ip -o route get 1", r"dev (\S+)")
    env_network["MAIN_IFACE"] = main_interface

    # 提取当前IP地址
    curr_ip = run_cmd(sudo_cmd, f"ip -4 addr show {main_interface}", r"inet (\d+\.\d+\.\d+\.\d+)/")
    env_network["CURR_IP"] = curr_ip

    # 提取网关
    gateway = run_cmd(sudo_cmd, "ip route show default", r"default via (\d+\.\d+\.\d+\.\d+)")
    env_network["GATEWAY"] = gateway

    # 检查是否有DHCP客户端运行
    # pgrep -f "dhclient|dhcpcd|nm-dhcp|NetworkManager.*dhcp"
    dhcp_client = bool(run_cmd(sudo_cmd, ["pgrep", "-f", "dhclient|dhcpcd|nm-dhcp|NetworkManager.*dhcp"]))
    env_network["DHCP_CLIENT"] = dhcp_client

    # 调用 dmidecode 获取 system-manufacturer
    manufacturer = is_cloud_manufacturer(run_cmd(sudo_cmd, "dmidecode -s system-manufacturer"))
    if manufacturer:
        env_network["IS_CLOUD"] = manufacturer.strip()

    # 新安装系统，是这几种之一：systemd-networkd、NetworkManager、networking[ifupdown]、wicked、network[network-scripts]
    nm_type = get_network_service(sudo_cmd)
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

    return env_network


if __name__ == "__main__":
    # 测试入口
    status, env_network = check_ip("apt")
    print(f"返回状态码: {status}")
    print(f"返回的网络配置: {env_network}")
