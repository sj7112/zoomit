#!/usr/bin/env python3

"""Arch Mirror Speed Tester"""

import os
from pathlib import Path
import re
import sys
from typing import Dict, List


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))  # add root sys.path

from python.mirror.linux_speed import MirrorResult, MirrorTester, get_country_name
from python.msg_handler import _mf
from python.file_util import write_source_file
from python.read_util import confirm_action


class ArchMirrorTester(MirrorTester):
    def __init__(self):
        # Backup Mirror List: 10 Commonly Used Sites Worldwide
        self.mirrors = [
            # European
            {"country": "Germany", "url": "https://ftp.fau.de/archlinux/"},
            {"country": "UK", "url": "https://www.mirrorservice.org/sites/ftp.archlinux.org/"},
            {"country": "France", "url": "https://mirrors.ircam.fr/pub/archlinux/"},
            # North America
            {"country": "USA", "url": "https://mirrors.mit.edu/archlinux/"},
            {"country": "Canada", "url": "https://mirror.csclub.uwaterloo.ca/archlinux/"},
            # Asia pacific
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/archlinux/"},
            {"country": "China", "url": "https://mirrors.aliyun.com/archlinux/"},
            {"country": "China", "url": "https://mirrors.163.com/archlinux/"},
            {"country": "Korea", "url": "https://mirror.kaist.ac.kr/archlinux/"},
            {"country": "Australia", "url": "https://mirror.aarnet.edu.au/pub/archlinux/"},
        ]
        super().__init__()
        self.mirror_list = "https://archlinux.org/mirrorlist/?country=all"
        if self.is_debug:
            # 测试代码！！！
            self.os_info.ostype = "arch"
            self.os_info.pretty_name = "Arch Linux"
            self.os_info.package_mgr = "pacman"

    # ==============================================================================
    # (1) Check PM Path
    # ==============================================================================
    def check_file(self, file_path):
        """filepath and urls"""
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("Server") and "=" in line:
                    # remove section: $repo/os/$arch
                    match = re.search(r"(https?://[^\s]+?/?)(?:\$repo/os/\$arch)?/?$", line)
                    if match:
                        url = match.group(1)
                        if url not in self.urls:
                            self.urls.append(url)

        if self.urls:
            self.path = file_path

    def find_mirror_source(self):
        """find config file, get path and urls"""

        SOURCE_FILE = "/etc/pacman.d/mirrorlist"

        self.check_file(SOURCE_FILE)
        if self.path:
            return

    # ==============================================================================
    # (2) Search Fast mirrors
    # ==============================================================================
    def parse_mirror_list(self, lines: List[str]) -> List[Dict]:
        """Parse the HTML content"""

        system_country_name = get_country_name(self.system_country)
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Match country name (## Country Name)
            country_match = re.match(r"^##\s+(.+)$", line)
            if country_match:
                country_name = country_match.group(1).strip()

                mirrors_country = []
                i += 1

                # Read all mirror URLs under the country
                while i < len(lines):
                    next_line = lines[i].strip()

                    # Exit current country processing if encountering the next country marker
                    if re.match(r"^##\s+", next_line):
                        i -= 1  # Step back one line for outer loop processing
                        break

                    # Match server URL (part before $repo/os/$arch)
                    server_match = re.match(r"^#Server\s*=\s*(.+)$", next_line)
                    if server_match:
                        url = server_match.group(1).strip()
                        url = re.sub(r"/\$repo.*$", "/", url)

                        # Check if URL is valid and not duplicated
                        if not self.url_exists(mirrors_country, url):
                            mirrors_country.append({"country": country_name, "url": url})

                    i += 1

                # Add country to mirrors
                if mirrors_country:
                    # Prefer system default country (add to the front)
                    if country_name and country_name.lower() in system_country_name.lower():
                        self.mirrors = mirrors_country + self.mirrors
                    else:
                        self.mirrors.extend(mirrors_country)

            i += 1

    # ==============================================================================
    # (3) Update PM File
    # ==============================================================================
    def choose_mirror(self) -> None:
        """Select the fastest mirror and update the package manager file"""

        top_10 = self.test_all_mirrors()

        confirm_action(_mf("Would you like to switch to the new mirror list?"), self.update_pm_file, top_10)

    def update_pm_file(self, top_10):
        # generate custom content
        lines = self.add_custom_sources(top_10)

        # update source file
        write_source_file(self.path, lines)

    def add_custom_sources(self, top_10: List[MirrorResult]) -> list[str]:
        """add to mirror list"""
        lines = []
        for mr in top_10:
            lines.append(f"Server = {mr.url}$repo/os/$arch")

        lines.append(f"Server = https://geo.mirror.pkgbuild.com/$repo/os/$arch")
        lines.append("")

        return lines
