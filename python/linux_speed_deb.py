#!/usr/bin/env python3

"""
Debian镜像速度测试工具
从官方镜像列表获取所有镜像，并进行速度测试
"""

import os
from pathlib import Path
import re
import sys
import requests
from typing import List


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from linux_speed import MirrorResult, MirrorTester
from file_util import file_backup_sj
from msg_handler import info, error


class DebianMirrorTester(MirrorTester):
    def __init__(self, system_country):
        # 后备镜像列表：全球常用的 10 个镜像站点（debian镜像更新慢，目前继续采用http）
        self.mirrors = [
            # 欧洲镜像
            {"country": "Germany", "url": "http://ftp.de.debian.org/debian/"},
            {"country": "UK", "url": "http://mirrorservice.org/sites/ftp.debian.org/debian/"},
            {"country": "France", "url": "http://ftp.fr.debian.org/debian/"},
            {"country": "Netherlands", "url": "http://ftp.nl.debian.org/debian/"},
            # 北美镜像
            {"country": "US", "url": "http://ftp.us.debian.org/debian/"},
            # 亚太镜像
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/debian/"},
            {"country": "Japan", "url": "http://ftp.jp.debian.org/debian/"},
            {"country": "Singapore", "url": "http://mirror.nus.edu.sg/debian/"},
            {"country": "Australia", "url": "http://ftp.au.debian.org/debian/"},
            # 南美和其他地区
            {"country": "Brazil", "url": "http://ftp.br.debian.org/debian/"},
        ]
        self.globals = {"country": "Global", "url": "http://deb.debian.org/debian"}
        super().__init__(system_country)
        self.mirror_list = "https://www.debian.org/mirror/mirrors_full"

    def match_patterns(self, line):
        """匹配的关键词（cdrom, deb, deb-src）"""
        if line.startswith("cdrom:"):
            return "cdrom:"
        match = re.match(r"^\s*(?:deb|deb-src)\s+(http[s]?://[^\s]+)", line)
        if match:
            return match.group(1)
        return None

    def check_file(self, file_path):
        """检测匹配到的文件名和urls"""
        urls = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#") or not line:
                    continue
                matched = self.match_patterns(line)
                if matched:
                    urls.append(matched)
        if urls:
            return file_path, urls
        return None, urls

    def find_apt_source(self):
        """找到默认apt配置文件，写入path和urls"""

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

    def parse_mirror_list(self, lines: List[str]) -> List[dict]:
        """解析镜像列表HTML内容"""

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 如果是国家开头行
            name_match = re.search(r'<h3>\s*<a name="([A-Z]+)">([^<]+)</a>', line)
            if name_match:
                country_code = name_match.group(1)
                country_name = name_match.group(2)
                i += 1
                country_mirrors = []

                # 内层循环处理该国家下的镜像
                while i < len(lines):
                    site_line = lines[i].strip()

                    # 如果遇到下一个国家段落，则跳出
                    if re.search(r'<h3>\s*<a name="([A-Z]+)">([^<]+)</a>', site_line):
                        break

                    # 匹配 site 域名
                    site_match = re.search(r"<tt>([a-zA-Z0-9\.\-]+)</tt>", site_line)
                    if site_match:
                        # 尝试在当前行或下一行匹配 href
                        href_match = re.search(r'href="(http[^"]+/debian/)"', site_line)
                        if not href_match and i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            href_match = re.search(r'href="(http[^"]+/debian/)"', next_line)
                            if href_match:
                                i += 1  # 消耗掉 href 行

                        if href_match:
                            country_mirrors.append(
                                {
                                    "country": country_name,
                                    "url": href_match.group(1),
                                }
                            )

                    i += 1  # 前进到下一行

                # 合并进 self.mirrors
                if country_code == self.system_country:
                    self.mirrors = country_mirrors + self.mirrors
                else:
                    self.mirrors.extend(country_mirrors)

            else:
                i += 1

    def check_mirror(self, selected_mirror: MirrorResult) -> int:
        """
        检查镜像站的 bookworm, updates, security 可用性

        Args:
            selected_mirror: MirrorResult 对象，包含 url 属性

        Returns:
            如果updates存在，改写 selected_mirror.url_upd
            如果security存在，改写 selected_mirror.url_sec
        """

        def _is_url_accessible(url: str) -> bool:
            """检查URL是否可访问"""
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            }
            try:
                response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
                return response.status_code == 200
            except:
                return False

        # 检查 bookworm-updates
        base_url = selected_mirror.url.rstrip("/")
        updates_url = f"{base_url}/dists/bookworm-updates/Release"
        if _is_url_accessible(updates_url):
            selected_mirror.url_upd = selected_mirror.url

        # 检查 bookworm-security
        if base_url.endswith("/debian"):
            # 将 /debian 替换为 /debian-security/
            security_url = base_url + "-security/"
            if _is_url_accessible(security_url):
                selected_mirror.url_sec = security_url
                return

    def update_path(self, mirror):
        source_file = self.path
        url, url_upd, url_sec = mirror.url, mirror.url_upd, mirror.url_sec
        def_url = "http://deb.debian.org/debian"
        def_url_sec = "http://security.debian.org/debian-security"

        # 1. 备份当前源文件
        file_backup_sj(source_file)

        # 2. 生成镜像源内容
        lines = []
        if not def_url == url:
            lines.extend(self.add_sources(url, url_upd, url_sec))

        # 3. 生成默认官方源内容
        lines.extend(self.add_sources(def_url, def_url, def_url_sec))

        # 4. 写入源文件
        try:
            with open(source_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            info(f"已更新 source list: {source_file}")
        except Exception as e:
            error(f"写入失败: {e}")

    def add_sources(self, url, url_upd, url_sec):
        # 2. 生成默认官方源内容
        codename = self.os_info.codename
        sources = [
            f"deb {url} {codename} main contrib non-free non-free-firmware",
        ]
        if url_upd:
            sources.append(f"deb {url_upd} {codename}-updates main contrib non-free non-free-firmware")
        if url_sec:
            sources.append(f"deb {url_sec} {codename}-security main contrib non-free non-free-firmware")
        return sources

    def run(self):
        """运行完整的测试流程"""
        # 1. 获取镜像列表
        self.find_apt_source()
        if not self.path:
            print("没有找到APT源配置文件")
            return

        # 2. 获取所有镜像
        self.fetch_mirror_list()

        # 3. 修改镜像
        self.update_mirror()


def update_source_deb(system_country: str) -> None:
    """主函数"""
    tester = DebianMirrorTester(system_country)
    try:
        tester.run()
    except KeyboardInterrupt:
        print("\n\n用户中断了测试")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    update_source_deb()
