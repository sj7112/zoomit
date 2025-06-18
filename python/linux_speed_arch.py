#!/usr/bin/env python3

"""Arch Mirror Speed Tester"""

import os
import re
import sys
from typing import Dict, List


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from linux_speed import MirrorResult, MirrorTester, get_country_name
from file_util import write_source_file
from system import confirm_action


class ArchMirrorTester(MirrorTester):
    def __init__(self, system_country):
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
        super().__init__(system_country)
        self.mirror_list = "https://archlinux.org/mirrorlist/?country=all"
        # # 测试代码！！！
        # self.os_info.ostype = "arch"
        # self.os_info.pretty_name = "Arch Linux"

    # ==============================================================================
    # (1) Check PM Path
    # ==============================================================================
    def check_file(self, file_path):
        """filepath and urls"""
        urls = []

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("Server") and "=" in line:
                    # remove section: $repo/os/$arch
                    match = re.search(r"(https?://[^\s]+?/?)(?:\$repo/os/\$arch)?/?$", line)
                    if match:
                        url = match.group(1)
                        if url not in urls:
                            urls.append(url)

        return (file_path, urls) if urls else (None, [])

    def find_source(self):
        """find config file, get path and urls"""

        SOURCE_FILE = "/etc/pacman.d/mirrorlist"

        self.path, self.urls = self.check_file(SOURCE_FILE)
        if self.path:
            return

        self.path = None

    # ==============================================================================
    # (2) Search Fast mirrors
    # ==============================================================================
    def parse_mirror_list(self, lines: List[str]) -> List[Dict]:
        """Parse the HTML content"""

        system_country_name = get_country_name(self.system_country)
        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 匹配国家名称 (## Country Name)
            country_match = re.match(r"^##\s+(.+)$", line)
            if country_match:
                country_name = country_match.group(1).strip()

                # 获取该国家的所有URL
                mirrors_country = []
                i += 1

                # 读取该国家下的所有镜像URL
                while i < len(lines):
                    next_line = lines[i].strip()

                    # 如果遇到下一个国家标记，退出当前国家处理
                    if re.match(r"^##\s+", next_line):
                        i -= 1  # 回退一行，让外层循环处理
                        break

                    # 匹配服务器URL
                    server_match = re.match(r"^#Server\s*=\s*(.+)$", next_line)
                    if server_match:
                        url = server_match.group(1).strip()
                        # 保留$repo/os/$arch前的部分
                        url = re.sub(r"/\$repo.*$", "/", url)

                        # 检查URL是否有效且不重复
                        if not self.url_exists(mirrors_country, url):
                            mirrors_country.append({"country": country_name, "url": url})

                    i += 1

                # 将mirrors_country添加到mirrors中
                if mirrors_country:
                    # 如果国家匹配输入参数，添加到前面；否则从尾部添加
                    if country_name and country_name.lower() in system_country_name.lower():
                        self.mirrors = mirrors_country + self.mirrors
                    else:
                        self.mirrors.extend(mirrors_country)

            i += 1

    # ==============================================================================
    # (3) Update PM File
    # ==============================================================================
    def choose_mirror(self) -> None:
        """选择最快镜像，并更新包管理器文件"""

        # 1 测试所有镜像
        top_10 = self.test_all_mirrors()

        # 2 无限循环直到用户选中合法镜像
        prompt = f"是否变更为新的镜像列表?"
        confirm_action(prompt, self.update_path, top_10)

    def update_path(self, top_10):
        # generate custom content (One mirror is enough for CentOS)
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
