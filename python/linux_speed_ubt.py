#!/usr/bin/env python3

"""
Ubuntu镜像速度测试工具
从官方镜像列表获取所有镜像，并进行速度测试
"""

import os
from pathlib import Path
import platform
import re
import sys
import requests
from typing import List


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from linux_speed import MirrorResult, MirrorTester, _is_url_accessible
from file_util import file_backup_sj
from msg_handler import info, error


class UbuntuMirrorTester(MirrorTester):
    def __init__(self, system_country):
        # 后备镜像列表：全球常用的 10 个镜像站点
        self.mirrors = [
            # 欧洲镜像
            {"country": "Germany", "url": "https://ftp.halifax.rwth-aachen.de/ubuntu/"},
            {"country": "UK", "url": "https://mirror.bytemark.co.uk/ubuntu/"},
            {"country": "France", "url": "http://ftp.rezopole.net/ubuntu/"},
            {"country": "Netherlands", "url": "https://mirror.nl.leaseweb.net/ubuntu/"},
            {"country": "Sweden", "url": "https://ftp.acc.umu.se/mirror/ubuntu/"},
            # 美洲镜像
            {"country": "US", "url": "https://mirror.math.princeton.edu/pub/ubuntu/"},
            # 亚太镜像
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/ubuntu/"},
            {"country": "Japan", "url": "https://ftp.jaist.ac.jp/pub/Linux/ubuntu/"},
            {"country": "Singapore", "url": "http://mirror.nus.edu.sg/ubuntu/"},
            {"country": "Australia", "url": "https://mirror.aarnet.edu.au/ubuntu/"},
        ]
        self.globals = {"country": "Global", "url": "https://archive.ubuntu.com/ubuntu/"}
        super().__init__(system_country)
        # 测试代码！！！
        self.os_info.ostype = "ubuntu"
        self.os_info.codename = "noble"
        self.os_info.pretty_name = "Ubuntu 24.04.2 LTS"
        self.os_info.version_id = "24.04"

    # ==============================================================================
    # (1) 检查现有配置文件
    # ==============================================================================
    def check_file(self, file_path):
        """检测匹配到的文件名和urls"""
        urls = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                elif line.startswith("cdrom:"):
                    urls.append("cdrom:")
                    break
                else:
                    match = re.match(r"^\s*(?:deb|deb-src)\s+(http[s]?://[^\s]+)", line)
                    if match:
                        urls.append(match.group(1))
        if urls:
            return file_path, urls
        return None, []

    def check_file_new_format(self, file_path):
        """检查新格式（Deb822 .sources 文件）"""
        urls = []
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            uri_matches = re.findall(r"^\s*URIs:\s+(.+)$", content, re.MULTILINE)
            for uri_line in uri_matches:
                uris = uri_line.strip().split()
                for uri in uris:
                    if uri.startswith(("http://", "https://")):
                        urls.append(uri)
        if urls:
            return file_path, urls
        return None, urls

    def find_source(self):
        """
        查找APT源配置（支持Deb822新格式与传统格式）
        返回：sources = [(path1, [urls1]), (path2, [urls2]), ...]
        """
        SOURCE_FILE = "/etc/apt/sources.list"
        SOURCE_LIST_D_DIR = "/etc/apt/sources.list.d/"

        # 1. 新格式：/etc/apt/sources.list.d/*.sources
        for full_path in Path(SOURCE_LIST_D_DIR).glob("*.sources"):
            self.path, self.urls = self.check_file_new_format(full_path)
            if self.path:
                return

        # 2. 旧格式：主文件 /etc/apt/sources.list
        self.path, self.urls = self.check_file(SOURCE_FILE)
        if self.path:
            return

        # 3. 旧格式：/etc/apt/sources.list.d/*.list
        for full_path in Path(SOURCE_LIST_D_DIR).glob("*.list"):
            self.path, self.urls = self.check_file(full_path)
            if self.path:
                return

        # 4. 若无配置
        self.path = None

    # ==============================================================================
    # (2) 查找最快 mirror
    # ==============================================================================
    def fetch_mirror_list(self, limit: int = None) -> None:
        """主函数：计算最快的镜像并保存到文件"""
        # 获取所有国家列表
        try:
            response = requests.get("http://mirrors.ubuntu.com/", timeout=10)
            response.raise_for_status()

            # 提取国家代码
            countries = re.findall(r'<a href="([A-Z]{2})\.txt', response.text)
            countries = sorted(set(countries))

            # 交互式选择国家
            while True:
                user_input = input(f"请选择国家/地区代码（回车使用默认值 '{self.system_country}'）：").strip().upper()
                country_code = user_input if user_input else self.system_country

                if country_code not in countries:
                    print(f"国家代码 {country_code} 不存在于列表中！请核对 http://mirrors.ubuntu.com/")
                    continue

                self.mirror_list = f"http://mirrors.ubuntu.com/{country_code}.txt"
                break

            super().fetch_mirror_list(limit)  # 调用公共方法获取镜像列表
            self.filter_mirrors_by_arch()  # 根据系统架构筛选镜像

        except requests.RequestException as e:
            print(f"获取国家列表失败: {e}")

    def filter_mirrors_by_arch(self) -> list[str]:
        arch = platform.machine()

        if arch in ("x86_64", "amd64", "i386"):
            # 主流架构 → 只保留包含 /ubuntu/ 且不包含 /ubuntu-ports/
            self.mirrors = [
                m for m in self.mirrors if "/ubuntu/" in m.get("url", "") and "/ubuntu-ports/" not in m.get("url", "")
            ]
        else:
            # 移植架构 → 只保留 /ubuntu-ports/
            self.mirrors = [m for m in self.mirrors if "/ubuntu-ports/" in m.get("url", "")]

    def parse_mirror_list(self, lines: List[str]) -> List[dict]:
        """解析镜像列表HTML内容"""

        # 提取HTTP镜像地址
        for line in lines:
            line = line.strip()
            if line.startswith(("http://", "https://")):
                self.mirrors.append({"url": line})

    # ==============================================================================
    # (3) 修改配置文件
    # ==============================================================================
    def update_path(self, mirror):
        def_url = "http://archive.ubuntu.com/ubuntu/"
        def_url_sec = "http://security.ubuntu.com/ubuntu/"

        self.check_mirror(mirror)  # 判断镜像是否包含security
        url, url_sec = mirror.url, mirror.url_sec

        # 2. 生成镜像源内容
        lines = []
        if not def_url == url:
            lines.extend(self.add_sources(url, url_sec))

        # 3. 生成默认官方源内容
        lines.extend(self.add_source_def(def_url, def_url_sec))

        # 4. 写入源文件
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            info(f"已更新 source list: {self.path}")
        except Exception as e:
            error(f"写入失败: {e}")

    def check_mirror(self, selected_mirror):
        """
        检查镜像站的 noble, updates, security 可用性

        Args:
            selected_mirror: MirrorResult 对象，包含 url 属性

        Returns:
            如果updates存在，改写 selected_mirror.url_upd
            如果security存在，改写 selected_mirror.url_sec
        """

        # 检查 noble-security
        base_url = selected_mirror.url.rstrip("/")
        if base_url.endswith("/ubuntu"):
            security_url = f"{base_url}/dists/noble-security/"
            if _is_url_accessible(security_url):
                selected_mirror.url_sec = security_url

    def add_sources(self, url: str, url_sec: str) -> list[str]:
        """
        为自定义镜像源（如 tuna）生成 sources 块。
        """
        codename = self.os_info.codename
        suite = f"{codename} {codename}-updates {codename}-backports" + (f" {codename}-security" if url_sec else "")
        return [
            "Types: deb",
            f"URIs: {url}",
            f"Suites: {suite}",
            "Components: main restricted universe multiverse",
            "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg",
            "",
        ]

    def add_source_def(self, def_url: str, def_url_sec: str) -> list[str]:
        """
        为默认官方镜像源（archive/security）生成多块 sources 块。
        每个 suite 一块，以空行分隔。
        """
        codename = self.os_info.codename
        lines = []
        suites = [
            (def_url, f"{codename} {codename}-updates {codename}-backports"),
            (def_url_sec, f"{codename}-security"),
        ]

        for uri, suite in suites:
            lines.extend(
                [
                    "Types: deb",
                    f"URIs: {uri.rstrip('/')}/",
                    f"Suites: {suite}",
                    "Components: main restricted universe multiverse",
                    "Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg",
                    "",
                ]
            )
        return lines
