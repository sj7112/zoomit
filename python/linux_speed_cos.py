#!/usr/bin/env python3

"""
Centos镜像速度测试工具
从官方镜像列表获取所有镜像，并进行速度测试
"""

import glob
import os
import platform
import re
import sys


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from linux_speed import MirrorTester, _is_url_accessible
from file_util import file_backup_sj
from msg_handler import info, error


def get_centos_codename():
    # 检查 /etc/os-release 是否存在，提取 VERSION_ID
    if os.path.isfile("/etc/os-release"):
        with open("/etc/os-release") as f:
            os_release = f.read()

        version_id = None
        for line in os_release.splitlines():
            if line.startswith("VERSION_ID="):
                version_id = line.split("=")[1].strip('"')
                break

        if version_id:
            # 处理 CentOS 6/7 特殊情况
            if version_id in ["6", "7"]:
                # 获取 /etc/centos-release 中的版本号
                if os.path.isfile("/etc/centos-release"):
                    with open("/etc/centos-release") as f:
                        centos_release = f.read().strip()
                    return centos_release.split()[2]  # 获取类似 '7.9.2009' 的版本号
            else:
                return version_id
    return "unknown"


def auto_detect_gpg_key():
    """自动检测GPG密钥文件"""
    possible_keys = [
        "/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7",
        "/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-6",
        "/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-8",
        "/etc/pki/rpm-gpg/RPM-GPG-KEY-centosofficial",
    ]

    for key_path in possible_keys:
        if os.path.exists(key_path):
            return f"file://{key_path}"

    # 如果都不存在，使用通配符搜索
    centos_keys = glob.glob("/etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS*")
    if centos_keys:
        return f"file://{centos_keys[0]}"

    return "file:///etc/pki/rpm-gpg/RPM-GPG-KEY-CentOS-7"


class CentosMirrorTester(MirrorTester):
    def __init__(self, system_country):
        # 镜像列表：全球常用的 13 个镜像站点
        self.mirrors = [
            # 欧洲镜像
            {"country": "Germany", "url": "https://ftp.plusline.net/centos-vault/"},
            {"country": "Germany", "url": "https://mirror.rackspeed.de/centos/"},
            # 北美镜像
            {"country": "US", "url": "https://mirror.math.princeton.edu/pub/centos-vault/"},
            # 亚太镜像
            {"country": "China", "url": "https://mirrors.aliyun.com/centos-vault/"},
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/centos-vault/"},
            {"country": "China", "url": "https://mirrors.ustc.edu.cn/centos-vault/"},
            {"country": "China", "url": "https://mirrors.163.com/centos-vault/"},
            {"country": "China", "url": "https://mirrors.huaweicloud.com/centos-vault/"},
            {"country": "Japan", "url": "https://ftp.riken.jp/Linux/centos-vault/"},
            {"country": "Korea", "url": "https://mirror.kakao.com/centos/"},
            {"country": "Australia", "url": "https://mirror.aarnet.edu.au/pub/centos/"},
            # 南美和其他地区
            {"country": "Colombia", "url": "http://mirror.unimagdalena.edu.co/centos/"},
            {"country": "Brazil", "url": "http://ftp.unicamp.br/pub/centos/"},
        ]
        self.globals = {"country": "Global", "url": "https://vault.centos.org/"}
        super().__init__(system_country)
        self.os_info.codename = get_centos_codename()  # 确保获取版本代号，如7.9.2009
        # 测试代码！！！
        self.os_info.ostype = "centos"
        self.os_info.codename = "7.9.2009"  # 确保获取版本代号，如7.9.2009
        self.os_info.pretty_name = "CentOS Linux 7 (Core)"
        self.os_info.version_id = "7"

    # ==============================================================================
    # (1) 检查现有配置文件
    # ==============================================================================
    def check_file(self, file_path):
        """检查 CentOS-Base.repo 文件并提取 baseurl 列表"""
        urls = []
        current_section = None
        valid_sections = ["Base", "Updates", "Extras"]

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                # 匹配 name=
                if line.startswith("name="):
                    # 提取末尾关键字，如 Base、Updates 等
                    for section in valid_sections:
                        if line.endswith(section):
                            current_section = section
                            break
                    else:
                        current_section = None  # 不在我们关注的部分

                # 匹配 baseurl=
                elif line.startswith("baseurl=") and current_section:
                    url = line.partition("=")[2].strip()
                    if url.startswith(("http://", "https://")):
                        # 保留前缀包含 /centos/ 或 /centos-vault/
                        match = re.match(r"(https?://[^/]+/(centos|centos-vault)/)", url)
                        if match:
                            urls.append(match.group(1))  # 提取干净的 base URL
                    current_section = None  # 处理完一个 section，重置
        if urls:
            return file_path, urls
        return None, []

    def find_source(self):
        """找到默认yum配置文件，写入path和urls"""
        SOURCE_FILE = "/etc/yum.repos.d/CentOS-Base.repo"

        # 1. 检查配置
        self.path, self.urls = self.check_file(SOURCE_FILE)
        if self.path:
            return

        # 2. 若无配置
        self.path = None

    # ==============================================================================
    # (2) 查找最快 mirror
    # ==============================================================================
    def fetch_mirror_list(self, limit: int = None) -> None:
        """centos镜像列表通过手工维护来获取"""

        if limit:
            self.mirrors = self.mirrors[:limit]  # 限制镜像数量(方便测试)

        print("Centos镜像速度测试工具")
        print("=" * 50)

    # ==============================================================================
    # (3) 修改配置文件
    # ==============================================================================
    def update_path(self, mirror):
        url = mirror.url

        # 2. 生成镜像源内容
        lines = self.add_sources(url)

        # 3. 写入源文件
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            info(f"已更新 source list: {self.path}")
        except Exception as e:
            error(f"写入失败: {e}")

    def add_sources(self, url: str) -> list[str]:
        """
        为自定义镜像源（Base | Updates | Extras）生成多块 sources 块。
        每个 suite 一块，以空行分隔。
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
