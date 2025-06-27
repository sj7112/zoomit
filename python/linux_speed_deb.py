#!/usr/bin/env python3

"""Debian Mirror Speed Tester"""

from pathlib import Path
import re
import sys
from typing import List


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.linux_speed import MirrorResult, MirrorTester, _is_url_accessible
from python.file_util import write_source_file
from python.msg_handler import info, error


class DebianMirrorTester(MirrorTester):
    def __init__(self):
        # Backup Mirror List: 10 Commonly Used Sites Worldwide
        self.mirrors = [
            # European
            {"country": "Germany", "url": "http://ftp.de.debian.org/debian/"},
            {"country": "UK", "url": "http://mirrorservice.org/sites/ftp.debian.org/debian/"},
            {"country": "France", "url": "http://ftp.fr.debian.org/debian/"},
            {"country": "Netherlands", "url": "http://ftp.nl.debian.org/debian/"},
            # North America
            {"country": "US", "url": "http://ftp.us.debian.org/debian/"},
            # Asia pacific
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/debian/"},
            {"country": "Japan", "url": "http://ftp.jp.debian.org/debian/"},
            {"country": "Singapore", "url": "http://mirror.nus.edu.sg/debian/"},
            {"country": "Australia", "url": "http://ftp.au.debian.org/debian/"},
            # Others
            {"country": "Brazil", "url": "http://ftp.br.debian.org/debian/"},
        ]
        super().__init__()
        self.mirror_list = "https://www.debian.org/mirror/mirrors_full"
        if self.is_debug:
            # 测试代码！！！
            self.os_info.ostype = "debian"
            self.os_info.codename = "bookworm"
            self.os_info.pretty_name = "Debian GNU/Linux 12 (bookworm)"
            self.os_info.version_id = "12"
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

    def find_mirror_source(self):
        """find config file, get path and urls"""

        SOURCE_FILE = "/etc/apt/sources.list"
        SOURCE_LIST_D_DIR = "/etc/apt/sources.list.d/"

        # Step 1: check /etc/apt/sources.list
        self.path, self.urls = self.check_file(SOURCE_FILE)
        if self.path:
            return

        # Step 2: check files in /etc/apt/sources.list.d/
        for full_path in Path(SOURCE_LIST_D_DIR).glob("*.list"):
            self.path, self.urls = self.check_file(full_path)
            if self.path:
                return

        self.path = None

    # ==============================================================================
    # (2) Search Fast mirrors
    # ==============================================================================
    def parse_mirror_list(self, lines: List[str]) -> List[dict]:
        """Parse the HTML content"""

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # country name match
            name_match = re.search(r'<h3>\s*<a name="([A-Z]+)">([^<]+)</a>', line)
            if name_match:
                country_code = name_match.group(1)
                country_name = name_match.group(2)
                i += 1
                country_mirrors = []

                # mirrors of the country
                while i < len(lines):
                    site_line = lines[i].strip()

                    # next country
                    if re.search(r'<h3>\s*<a name="([A-Z]+)">([^<]+)</a>', site_line):
                        break

                    # match sites
                    site_match = re.search(r"<tt>([a-zA-Z0-9\.\-]+)</tt>", site_line)
                    if site_match:
                        # match href line
                        href_match = re.search(r'href="(http[^"]+/debian/)"', site_line)
                        if not href_match and i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            href_match = re.search(r'href="(http[^"]+/debian/)"', next_line)
                            if href_match:
                                i += 1  # proceed

                        if href_match:
                            country_mirrors.append(
                                {
                                    "country": country_name,
                                    "url": href_match.group(1),
                                }
                            )

                    i += 1  # go to next line

                # merge to self.mirrors
                if country_code == self.system_country:
                    self.mirrors = country_mirrors + self.mirrors
                else:
                    self.mirrors.extend(country_mirrors)

            else:
                i += 1

    # ==============================================================================
    # (3) Update PM File
    # ==============================================================================
    def update_pm_file(self, mirror):
        def_url = "http://deb.debian.org/debian"
        def_url_sec = "http://security.debian.org/debian-security"

        # 1. check custom mirror
        self.check_mirror_components(mirror)
        url, url_upd, url_sec = mirror.url, mirror.url_upd, mirror.url_sec

        # 2. generate custom content
        lines = self.add_custom_sources(url, url_upd, url_sec)

        # 3. generate default content
        lines.extend(self.add_custom_sources(def_url, def_url, def_url_sec))

        # 4. update source file
        write_source_file(self.path, lines)

    def check_mirror_components(self, selected_mirror: MirrorResult) -> int:
        """
        check bookworm, updates, security

        Args:
            selected_mirror: MirrorResult with "url"

        Returns:
            if "updates" exists, add to selected_mirror.url_upd
            if "security" exists, add to selected_mirror.url_sec
        """

        # Check bookworm-updates
        base_url = selected_mirror.url.rstrip("/")
        updates_url = f"{base_url}/dists/bookworm-updates/Release"
        if _is_url_accessible(updates_url):
            selected_mirror.url_upd = selected_mirror.url

        # Check bookworm-security
        if base_url.endswith("/debian"):
            #  /debian => /debian-security/
            security_url = base_url + "-security/"
            if _is_url_accessible(security_url):
                selected_mirror.url_sec = security_url

    def add_custom_sources(self, url, url_upd, url_sec):
        """add sources for custom mirrors"""

        codename = self.os_info.codename
        sources = [
            f"deb {url} {codename} main contrib non-free non-free-firmware",
        ]
        if url_upd:
            sources.append(f"deb {url_upd} {codename}-updates main contrib non-free non-free-firmware")
        if url_sec:
            sources.append(f"deb {url_sec} {codename}-security main contrib non-free non-free-firmware")
        sources.append("")
        return sources
