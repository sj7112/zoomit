#!/usr/bin/env python3

"""Ubuntu Mirror Speed Tester"""

from pathlib import Path
import platform
import re
import sys
import requests
from typing import List


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))  # add root sys.path

from python.mirror.linux_speed import MirrorResult, MirrorTester, _is_url_accessible
from python.file_util import write_source_file
from python.msg_handler import info, error


class UbuntuMirrorTester(MirrorTester):
    def __init__(self):
        # Backup Mirror List: 10 Commonly Used Sites Worldwide
        self.mirrors = [
            # European
            {"country": "Germany", "url": "https://ftp.halifax.rwth-aachen.de/ubuntu/"},
            {"country": "UK", "url": "https://mirror.bytemark.co.uk/ubuntu/"},
            {"country": "France", "url": "http://ftp.rezopole.net/ubuntu/"},
            {"country": "Netherlands", "url": "https://mirror.nl.leaseweb.net/ubuntu/"},
            {"country": "Sweden", "url": "https://ftp.acc.umu.se/mirror/ubuntu/"},
            # North America
            {"country": "US", "url": "https://mirror.math.princeton.edu/pub/ubuntu/"},
            # Asia pacific
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/ubuntu/"},
            {"country": "Japan", "url": "https://ftp.jaist.ac.jp/pub/Linux/ubuntu/"},
            {"country": "Singapore", "url": "http://mirror.nus.edu.sg/ubuntu/"},
            {"country": "Australia", "url": "https://mirror.aarnet.edu.au/ubuntu/"},
        ]
        super().__init__()
        if self.is_debug:
            # 测试代码！！！
            self.os_info.ostype = "ubuntu"
            self.os_info.codename = "noble"
            self.os_info.pretty_name = "Ubuntu 24.04.2 LTS"
            self.os_info.version_id = "24.04"
            self.os_info.package_mgr = "apt"

    # ==============================================================================
    # (1) Check PM Path
    # ==============================================================================
    def check_file(self, file_path):
        """filepath and urls"""
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

        return (file_path, urls) if urls else (None, [])

    def check_file_new_format(self, file_path):
        """check new format (Deb822 .sources files)"""
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

    def find_mirror_source(self):
        """find config file, get path and urls"""

        SOURCE_FILE = "/etc/apt/sources.list"
        SOURCE_LIST_D_DIR = "/etc/apt/sources.list.d/"

        # 1. Deb822 new format: /etc/apt/sources.list.d/*.sources
        for full_path in Path(SOURCE_LIST_D_DIR).glob("*.sources"):
            self.path, self.urls = self.check_file_new_format(full_path)
            if self.path:
                return

        # 2. traditional format: /etc/apt/sources.list
        self.path, self.urls = self.check_file(SOURCE_FILE)
        if self.path:
            return

        # 3. old style: /etc/apt/sources.list.d/*.list
        for full_path in Path(SOURCE_LIST_D_DIR).glob("*.list"):
            self.path, self.urls = self.check_file(full_path)
            if self.path:
                return

        self.path = None

    # ==============================================================================
    # (2) Search Fast mirrors
    # ==============================================================================
    def fetch_mirror_list(self, limit: int = None) -> None:
        """Choose country mirror list"""

        try:
            response = requests.get("http://mirrors.ubuntu.com/", timeout=10)
            response.raise_for_status()

            # country code
            countries = re.findall(r'<a href="([A-Z]{2})\.txt', response.text)
            countries = sorted(set(countries))

            # read country
            while True:
                user_input = input(f"请选择国家/地区代码（回车使用默认值 '{self.system_country}'）：").strip().upper()
                country_code = user_input if user_input else self.system_country

                if country_code not in countries:
                    print(f"国家代码 {country_code} 不存在于列表中！请核对 http://mirrors.ubuntu.com/")
                    continue

                self.mirror_list = f"http://mirrors.ubuntu.com/{country_code}.txt"
                break

            super().fetch_mirror_list(limit)
            self.filter_mirrors_by_arch()

        except requests.RequestException as e:
            print(f"获取国家列表失败: {e}")

    def filter_mirrors_by_arch(self) -> list[str]:
        arch = platform.machine()

        if arch in ("x86_64", "amd64", "i386"):
            # main stream → /ubuntu/
            self.mirrors = [
                m for m in self.mirrors if "/ubuntu/" in m.get("url", "") and "/ubuntu-ports/" not in m.get("url", "")
            ]
        else:
            # others → /ubuntu-ports/
            self.mirrors = [m for m in self.mirrors if "/ubuntu-ports/" in m.get("url", "")]

    def parse_mirror_list(self, lines: List[str]) -> List[dict]:
        """Parse the HTML content"""

        for line in lines:
            line = line.strip()
            if line.startswith(("http://", "https://")):
                self.mirrors.append({"url": line})

    # ==============================================================================
    # (3) Update PM File
    # ==============================================================================
    def update_pm_file(self, mirror):
        def_url = "https://archive.ubuntu.com/ubuntu/"
        def_url_sec = "https://security.ubuntu.com/ubuntu/"

        # 1. check custom mirror
        self.check_mirror_components(mirror)
        url, url_sec = mirror.url, mirror.url_sec

        # 2. generate custom content
        lines = self.add_custom_sources(url, url_sec)

        # 3. generate default content
        lines.extend(self.add_default_sources(def_url, def_url_sec))

        # 4. update source file
        write_source_file(self.path, lines)

    def check_mirror_components(self, selected_mirror):
        """
        check noble, updates, security

        Args:
            selected_mirror: MirrorResult with "url"

        Returns:
            if "updates" exists, add to selected_mirror.url_upd
            if "security" exists, add to selected_mirror.url_sec
        """

        # Check noble-security
        base_url = selected_mirror.url.rstrip("/")
        if base_url.endswith("/ubuntu"):
            security_url = f"{base_url}/dists/noble-security/"
            if _is_url_accessible(security_url):
                selected_mirror.url_sec = security_url

    def add_custom_sources(self, url: str, url_sec: str) -> list[str]:
        """add sources block for custom mirrors"""

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

    def add_default_sources(self, def_url: str, def_url_sec: str) -> list[str]:
        """
        add sources block (archive | security) for custom mirrors
        one block for each suite, separated by empty lines.
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
