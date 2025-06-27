#!/usr/bin/env python3

"""openSUSE Mirror Speed Tester"""

from pathlib import Path
import re
import sys
from typing import List


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.linux_speed import MirrorTester, get_country_name
from python.file_util import write_source_file


class OpenSUSEMirrorTester(MirrorTester):
    def __init__(self):
        # Backup Mirror List: 10 Commonly Used Sites Worldwide
        self.mirrors = [
            # European
            {"country": "Germany", "url": "https://ftp.fau.de/opensuse/"},
            {"country": "Germany", "url": "https://ftp.halifax.rwth-aachen.de/opensuse/"},
            {"country": "UK", "url": "https://www.mirrorservice.org/sites/download.opensuse.org/"},
            {"country": "Netherlands", "url": "https://ftp.nluug.nl/pub/os/Linux/distr/opensuse/"},
            {"country": "Italy", "url": "https://opensuse.mirror.garr.it/opensuse/"},
            {"country": "Sweden", "url": "https://ftp.lysator.liu.se/pub/opensuse/"},
            # North America
            {"country": "US", "url": "https://mirrors.kernel.org/opensuse/"},
            {"country": "US", "url": "https://mirror.math.princeton.edu/pub/opensuse/"},
            # Asia pacific
            {"country": "China", "url": "https://mirrors.aliyun.com/opensuse/"},
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/opensuse/"},
            {"country": "China", "url": "https://mirrors.ustc.edu.cn/opensuse/"},
            {"country": "China", "url": "https://mirrors.huaweicloud.com/opensuse/"},
            {"country": "China", "url": "https://mirror.sjtu.edu.cn/opensuse/"},
            {"country": "China", "url": "https://mirrors.bfsu.edu.cn/opensuse/"},
            {"country": "Japan", "url": "https://ftp.riken.jp/Linux/opensuse/"},
            {"country": "Japan", "url": "https://ftp.jaist.ac.jp/pub/Linux/openSUSE/"},
            {"country": "Korea", "url": "https://mirror.kakao.com/opensuse/"},
            {"country": "Singapore", "url": "https://download.nus.edu.sg/mirror/opensuse/"},
            {"country": "Australia", "url": "https://mirror.aarnet.edu.au/pub/opensuse/"},
            {"country": "Australia", "url": "https://ftp.iinet.net.au/pub/opensuse/"},
            {"country": "India", "url": "https://mirror.niser.ac.in/opensuse/"},
            # Others
            {"country": "Brazil", "url": "https://opensuse.c3sl.ufpr.br/"},
            {"country": "Brazil", "url": "https://mirror.ufscar.br/opensuse/"},
            {"country": "Argentina", "url": "https://mirror.fcaglp.unlp.edu.ar/opensuse/"},
            {"country": "South Africa", "url": "https://opensuse.mirror.ac.za/"},
            {"country": "Russia", "url": "https://mirror.yandex.ru/opensuse/"},
            {"country": "Turkey", "url": "https://ftp.linux.org.tr/opensuse/"},
        ]
        super().__init__()
        self.mirror_list = "https://mirrors.opensuse.org/"
        if self.is_debug:
            # 测试代码！！！
            self.os_info.ostype = "opensuse"
            self.os_info.codename = "15.6"
            self.os_info.pretty_name = "openSUSE Leap 15.6"
            self.os_info.version_id = "15.6"
            self.os_info.package_mgr = "zypper"

    # ==============================================================================
    # (1) Check PM Path
    # ==============================================================================
    def check_file(self, file_path):
        """filepath and urls"""
        baseurl = None
        urls = []

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("baseurl="):
                    baseurl = line[len("baseurl=") :]
                    break

            if baseurl:
                urls.append(re.split(r"/(distribution|update)/", baseurl)[0] + "/")

        return (file_path, urls) if urls else (None, [])

    def find_mirror_source(self):
        """check repo-oss.repo, get path and urls"""

        SOURCE_FILE = "/etc/zypp/repos.d/repo-oss.repo"

        self.path, self.urls = self.check_file(SOURCE_FILE)
        if self.path:
            return

        self.path = None

    # ==============================================================================
    # (2) Search Fast mirrors
    # ==============================================================================
    def parse_mirror_list(self, lines: List[str]):
        """Parse the HTML content"""

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if "<tr>" in line and not "</tr>" in line:  # <tr>/n.../n.../n</tr>
                i = self._process_tr_section(lines, i)
            else:
                i += 1

    def _process_tr_section(self, lines, start_index):
        """处理<tr>到</tr>之间的内容"""
        i = start_index + 1

        # 1) 判断第一个td是否包含country信息
        country_code = None
        while i < len(lines):
            line = lines[i].strip()
            i += 1  # 当前行处理完毕，指针跳到下一行
            if "</tr>" in line:
                return i  # 返回下一行索引

            country_match = re.search(r'<div class="country">([^<]+)</div>', line)
            if country_match:
                country_code = country_match.group(1).strip()
                break

        # 2) 搜索包含distribution/leap/15.6/repo的链接
        while i < len(lines):
            line = lines[i].strip()
            i += 1  # to next line
            if "</tr>" in line:
                return i  # return next line

            href_match = re.search(r'href="([^"]+)distribution/leap/15\.6/repo"', line)
            if href_match:
                url = href_match.group(1).strip()
                if url.endswith("/source/"):
                    url = url[:-7]  # 去掉source/后缀
                mirror_item = {
                    "country": get_country_name(country_code),
                    "url": url,
                }
                # 根据是否为本地国家来决定插入位置
                if country_code.lower() == self.system_country.lower():
                    self.mirrors.insert(0, mirror_item)
                else:
                    self.mirrors.append(mirror_item)
                return i  # return next line

    # ==============================================================================
    # (3) Update PM File
    # ==============================================================================
    def update_pm_file(self, mirror):
        url = mirror.url

        # generate custom content
        results = self.add_custom_sources(url)

        # update source file
        for path, lines in results:
            write_source_file(path, lines)

    def add_custom_sources(self, url: str) -> str:
        def_url = "https://download.opensuse.org/"

        repo_map = {
            "repo-oss": {"name": "main repository", "path": "distribution/leap/$releasever/repo/oss/"},
            "repo-non-oss": {
                "name": "main repository (non-OSS)",
                "path": "distribution/leap/$releasever/repo/non-oss/",
            },
            "repo-update": {"name": "main update repository", "path": "update/leap/$releasever/oss/"},
            "repo-update-non-oss": {"name": "update repository (non-OSS)", "path": "update/leap/$releasever/non-oss/"},
            "repo-backports-update": {
                "name": "Backports Update Repository",
                "path": "update/leap/$releasever/backports/",
            },
            "repo-sle-update": {"name": "SLE Update Repository", "path": "update/leap/$releasever/sle/"},
        }

        results = []
        for repo_type, info in repo_map.items():
            full_url = url + info["path"]
            gpgkey_url = full_url + "/repodata/repomd.xml.key"

            lines = [
                f"[{repo_type}]",
                f"name={info['name']}",
                "enabled=1",
                "autorefresh=1",
                f"baseurl={full_url}",
                "path=/",
                "type=rpm-md",
                "keeppackages=0",
                "gpgcheck=1",
                f"gpgkey={gpgkey_url}",
                "priority=90",
                "",
            ]
            # extend official value
            full_url = def_url + info["path"]
            gpgkey_url = full_url + "/repodata/repomd.xml.key"
            lines.extend(
                [
                    f"[{repo_type}-official]",
                    f"name={info['name']} - official",
                    "enabled=1",
                    "autorefresh=1",
                    f"baseurl={full_url}",
                    "path=/",
                    "type=rpm-md",
                    "keeppackages=0",
                    "gpgcheck=1",
                    f"gpgkey={gpgkey_url}",
                    "priority=99",
                    "",
                ]
            )
            repo_file = f"/etc/zypp/repos.d/{repo_type}.repo"
            results.append((repo_file, lines))

        return results
