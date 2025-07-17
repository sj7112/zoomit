#!/usr/bin/env python3

from pathlib import Path
import os
import shutil
import sys
from typing import List


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.file_util import read_env_file
from python.cmd_handler import cmd_ex_str, cmd_ex_pat
from python.system import get_network_service, get_param_fixip, get_static_ip, check_dns
from python.read_util import confirm_action
from python.msg_handler import _mf, exiterr, info, string
from python.debug_tool import print_array

# Set the default path
PARENT_DIR = Path(__file__).resolve().parent.parent
CONF_DIR = (PARENT_DIR / "config/network").resolve()

DEF_DNS8 = "8.8.8.8"
DEF_DNS1 = "1.1.1.1"


def is_cloud_manufacturer(manufacturer):
    # Common Cloud Provider Keywords List (Extensible)
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


def nmcli_dns_check(dns_str: str) -> List[str]:
    """
    Parse DNS entries from `nmcli` command output
    """
    lines = dns_str.splitlines()
    dns_list = []
    for line in lines:
        if "IP4.DNS" in line.upper():
            # Typical format: IP4.DNS[1]: 8.8.8.8
            # Extract the IP address after the colon and strip whitespace
            dns_ip = line.split(":", 1)[1].strip()
            dns_list.append(dns_ip)

    return dns_list


class NetworkSetup:
    """
    Network Setup class
    """

    def __init__(self, type="infrastructure"):
        self.type = type
        self.env = read_env_file(os.path.join(CONF_DIR, ".env"), type)

    # ==============================================================================
    # (0) Function Tools
    # ==============================================================================
    def save_env(self, backup=True):
        """
        retrieve network parameters, save to .env file
        """
        CONF_DIR.mkdir(parents=True, exist_ok=True)
        env_file = os.path.join(CONF_DIR, ".env")

        # backup original config file
        backup_file = f"{env_file}.bak"
        if backup and not os.path.exists(backup_file):
            shutil.copy2(env_file, backup_file)

        # write to config file
        with open(env_file, "w", encoding="utf-8") as f:
            f.write("#=network\n\n")
            # Write network parameters
            for key, value in self.env.items():
                f.write(f"{key}={value}\n")

    def find_ip4_dns(self):
        """
        Find all IPv4 DNS server
        """
        nm_type = self.env.get("CURR_NM")
        main_interface = self.env.get("MAIN_IFACE")
        if nm_type == "NetworkManager":
            dns_servers = nmcli_dns_check(cmd_ex_str(f"nmcli device show {main_interface}"))

        # elif nm_type == "systemd-networkd":
        #     # systemd-networkd 使用 resolv.conf
        #     resolv_path = "/run/systemd/resolve/resolv.conf"
        #     if os.path.exists(resolv_path):
        #         with open(resolv_path, "r") as f:
        #             dns_servers = re.findall(r"nameserver (\d+\.\d+\.\d+\.\d+)", f.read())
        #             return " ".join(dns_servers)

        # elif nm_type in ["networking", "wicked", "network"]:
        #     # 其他网络服务通常也使用 /etc/resolv.conf
        #     return check_dns_from_resolv()

        # if no DNS found, use the default DNS servers
        else:
            dns_servers = check_dns()

        # add default DNS for international websites 8.8.8.8 | 1.1.1.1
        if DEF_DNS8 not in dns_servers:
            dns_servers.append(DEF_DNS8)
        if DEF_DNS1 not in dns_servers:
            dns_servers.append(DEF_DNS1)

        return " ".join(dns_servers)

    # ==============================================================================
    # (1) Check Network Environment
    # ==============================================================================
    def check_env(self):
        """
        Check whether the server is using a static IP
        """
        # Extract the primary network interface
        main_interface = cmd_ex_pat("ip -o route get 1", r"dev (\S+)")
        self.env["MAIN_IFACE"] = main_interface

        # current IP Address
        curr_ip = cmd_ex_pat(f"ip -4 addr show {main_interface}", r"inet (\d+\.\d+\.\d+\.\d+)/")
        self.env["CURR_IP"] = curr_ip

        gateway = cmd_ex_pat("ip route show default", r"default via (\d+\.\d+\.\d+\.\d+)")
        self.env["GATEWAY"] = gateway

        # Check if a DHCP client is running
        # pgrep -f "dhclient|dhcpcd|nm-dhcp|NetworkManager.*dhcp"
        # dhcp_client = bool(cmd_ex_str(["pgrep", "-f", "dhclient|dhcpcd|nm-dhcp|NetworkManager.*dhcp"]))
        dhcp_client = "proto dhcp" in (cmd_ex_str(["ip", "route", "show", "default"]))
        self.env["DHCP_CLIENT"] = dhcp_client

        # call dmidecode for system-manufacturer
        manufacturer = is_cloud_manufacturer(cmd_ex_str("dmidecode -s system-manufacturer"))
        if manufacturer:
            self.env["IS_CLOUD"] = manufacturer.strip()

        # New installation must have：
        # NetworkManager、networking[ifupdown]、wicked、network[network-scripts]、systemd-networkd
        nm_type = get_network_service()
        self.env["CURR_NM"] = nm_type
        if not dhcp_client:
            self.env["STATIC_IP"] = get_static_ip(nm_type)
            if self.env["STATIC_IP"]:
                if curr_ip == self.env["STATIC_IP"]:
                    self.env["HAS_STATIC"] = "active"  # IP is fixed already
                else:
                    self.env["HAS_STATIC"] = "pending"  # IP is not fixed

        # Retrieve DNS server (use default if empty)
        if dns_servers := self.find_ip4_dns():
            self.env["DNS_SERVERS"] = dns_servers

    # ==============================================================================
    # (2) Update IP
    # ==============================================================================
    def setup_octet(self):
        """
        Interactive setup for static IP
        """
        env = self.env
        # Prompt the user to enter the last octet of the static IP address
        curr_ip = env.get("CURR_IP", "")
        gateway = env.get("GATEWAY", "")
        curr_last_octet = curr_ip.split(".")[-1] if curr_ip else "1"

        ip_parts = curr_ip.split(".") if curr_ip else []
        if len(ip_parts) < 3:
            string("The current IP address is invalid")
            return 3

        def valid_setup_octet(new_last_octet: int, error_msg: str) -> int:
            if not (1 <= new_last_octet <= 255):
                string("The input must be between 1 and 255")
                return 2  # continue

            if gateway and new_last_octet == int(gateway.split(".")[-1]):
                string("The static IP address cannot be the same as the gateway")
                return 2  # continue

            return 0  # valid input

        prompt = _mf(r"Please enter the last octet of the static IP address (1–255) [default: {}]: ", curr_last_octet)
        ret_code, new_last_octet = confirm_action(
            prompt,
            option="number",
            no_value=curr_last_octet,
            to_value=get_param_fixip(),
            err_handle=valid_setup_octet,
        )

        if ret_code == 0:
            # Build a new static IP address
            env["STATIC_IP"] = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.{new_last_octet}"
            env["HAS_STATIC"] = "pending"  # IP is not fixed

        return ret_code

    # ==============================================================================
    # Main Program
    # ==============================================================================
    def configure_nw(self):
        """
        need a static IP?
        Return values:
            0: Static IP modification is required
            1: Static IP modification is not required
            2: Operation cancelled by user
            3: Abnormal termination
        """
        # Initialize global variables
        self.check_env()

        # Cloud servers do not require a static IP
        env = self.env
        if env.get("IS_CLOUD"):
            info(r"{} Cloud servers do not require a static IP", env["IS_CLOUD"])
            return 1

        # Prompt the user to see if they want to modify the IP configuration
        default = True
        if env.get("DHCP_CLIENT") == False:
            if env.get("STATIC_IP"):
                string(f"{_mf('Server is configured with a static IP')}: {env['STATIC_IP']}")
                default = False
            else:
                string(f"{_mf('Server may be configured with a static IP')}: {env['CURR_IP']}")
        else:
            if env.get("CURR_IP"):
                string(f"{_mf('Server is configured with a dynamic IP')}: {env['CURR_IP']}")
            else:
                string("Server may be configured with a dynamic IP")

        prompt = _mf("Would you like to adjust it?")
        no_msg = _mf("Do not modify the network configuration")
        retVal = confirm_action(prompt, self.setup_octet, no_msg=no_msg, no_value=default)

        self.save_env()
        return retVal
