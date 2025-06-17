#!/usr/bin/env python3

"""Centos Mirror Speed Tester"""

import glob
import os
import platform
import re
import sys


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from linux_speed import MirrorTester, _is_url_accessible
from file_util import write_source_file
from msg_handler import info, error


def get_centos_codename():
    """package management - centos version codename"""
    if os.path.isfile("/etc/os-release"):
        with open("/etc/os-release") as f:
            os_release = f.read()

        version_id = None
        for line in os_release.splitlines():
            if line.startswith("VERSION_ID="):
                version_id = line.split("=")[1].strip('"')
                break

        if version_id:
            if version_id in ["6", "7"]:
                if os.path.isfile("/etc/centos-release"):
                    with open("/etc/centos-release") as f:
                        centos_release = f.read().strip()
                    return centos_release.split()[2]  # e.g. '7.9.2009'
            else:
                return version_id
    return "unknown"


def auto_detect_gpg_key():
    """GPG key file - auto detect path"""
    possible_keys = [
        "/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7",
        "/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-6",
        "/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-8",
        "/etc/pki/rpm-gpg/RPM-GPG-KEY-centosofficial",
    ]

    for key_path in possible_keys:
        if os.path.exists(key_path):
            return f"file://{key_path}"

    # if not exist, search by "*"
    centos_keys = glob.glob("/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS*")
    if centos_keys:
        return f"file://{centos_keys[0]}"

    return "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7"


class CentosMirrorTester(MirrorTester):
    def __init__(self, system_country):
        # Mirror List: 13 Commonly Used Sites Worldwide
        self.mirrors = [
            # European
            {"country": "Germany", "url": "https://ftp.plusline.net/centos-vault/"},
            {"country": "Germany", "url": "https://mirror.rackspeed.de/centos/"},
            # North America
            {"country": "US", "url": "https://mirror.math.princeton.edu/pub/centos-vault/"},
            # Asia pacific
            {"country": "China", "url": "https://mirrors.aliyun.com/centos-vault/"},
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/centos-vault/"},
            {"country": "China", "url": "https://mirrors.ustc.edu.cn/centos-vault/"},
            {"country": "China", "url": "https://mirrors.163.com/centos-vault/"},
            {"country": "China", "url": "https://mirrors.huaweicloud.com/centos-vault/"},
            {"country": "Japan", "url": "https://ftp.riken.jp/Linux/centos-vault/"},
            {"country": "Korea", "url": "https://mirror.kakao.com/centos/"},
            {"country": "Australia", "url": "https://mirror.aarnet.edu.au/pub/centos/"},
            # Others
            {"country": "Colombia", "url": "http://mirror.unimagdalena.edu.co/centos/"},
            {"country": "Brazil", "url": "http://ftp.unicamp.br/pub/centos/"},
        ]
        self.globals = {"country": "Global", "url": "https://vault.centos.org/"}
        super().__init__(system_country)
        self.os_info.codename = get_centos_codename()  # version code, such as 7.9.2009
        # # 测试代码！！！
        # self.os_info.ostype = "centos"
        # self.os_info.codename = "7.9.2009"  # 确保获取版本代号，如7.9.2009
        # self.os_info.pretty_name = "CentOS Linux 7 (Core)"
        # self.os_info.version_id = "7"

    # ==============================================================================
    # (1) Check PM Path
    # ==============================================================================
    def check_file(self, file_path):
        """filepath and urls"""
        urls = []
        current_section = None
        valid_sections = ["Base", "Updates", "Extras"]

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # match name=
                if line.startswith("name="):
                    for section in valid_sections:
                        if line.endswith(section):
                            current_section = section
                            break
                    else:
                        current_section = None  # not related

                # match baseurl=
                elif line.startswith("baseurl=") and current_section:
                    url = line.partition("=")[2].strip()
                    if url.startswith(("http://", "https://")):
                        # /centos/ or /centos-vault/
                        match = re.match(r"(https?://[^/]+/(centos|centos-vault)/)", url)
                        if match:
                            urls.append(match.group(1))  # base URL
                    current_section = None  # reset section
        if urls:
            return file_path, urls
        return None, []

    def find_source(self):
        """check CentOS-Base.repo, get path and urls"""

        SOURCE_FILE = "/etc/yum.repos.d/CentOS-Base.repo"

        self.path, self.urls = self.check_file(SOURCE_FILE)
        if self.path:
            return

        self.path = None

    # ==============================================================================
    # (2) Search Fast mirrors
    # ==============================================================================
    def fetch_mirror_list(self, limit: int = None) -> None:
        """centos mirror list is manually maintained"""

        if limit:
            self.mirrors = self.mirrors[:limit]  # mirrors limitation(for testing)

        print("Centos镜像速度测试工具")
        print("=" * 50)

    # ==============================================================================
    # (3) Update PM File
    # ==============================================================================
    def update_path(self, mirror):
        url = mirror.url

        # generate custom content
        lines = self.add_custom_sources(url)

        # update source file
        write_source_file(self.path, lines)

    def add_custom_sources(self, url: str) -> list[str]:
        """
        add sources block (Base | Updates | Extras) for custom mirrors
        one block for each suite, separated by empty lines.
        """
        codename = self.os_info.codename
        arch = platform.machine()
        lines = []
        suites = [
            ("Base", url, f"{codename}/os/"),
            ("Updates", url, f"{codename}/updates/"),
            ("Extras", url, f"{codename}/extras/"),
        ]

        for type, uri, suite in suites:
            lines.extend(
                [
                    f"[{type.lower()}]",
                    f"name=CentOS-{codename} - {type}",
                    f"baseurl={uri}{suite}{arch}/",
                    "gpgcheck=1",
                    f"gpgkey={auto_detect_gpg_key()}",
                    "",
                ]
            )
        return lines
