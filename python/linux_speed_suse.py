#!/usr/bin/env python3

"""
OpenSUSE镜像速度测试工具
从官方镜像列表获取所有镜像，并进行速度测试
"""

import logging
import os
import re
import sys
import time
import threading
from iso3166 import countries
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import statistics
from dataclasses import dataclass
from typing import Dict, List, Optional
import json

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from system import setup_logging
from linux_speed import MirrorTester

setup_logging()


@dataclass
class MirrorResult:
    """镜像测试结果"""

    url: str
    country: str
    avg_speed: float  # KB/s
    response_time: float  # seconds
    success_rate: float  # 0-1
    error_msg: Optional[str] = None


class OpenSUSEMirrorTester(MirrorTester):
    def __init__(self, distro_ostype, system_country):
        super().__init__(distro_ostype, system_country)
        self.globals = {"country": "Global", "url": "http://download.opensuse.org/"}

    def fetch_mirror_list(self) -> str:
        """读取数据"""
        try:
            response = requests.get("https://mirrors.opensuse.org/", timeout=10)
            response.raise_for_status()
            self.parse_mirror_list(response.text)
        except requests.RequestException as e:
            print(f"获取镜像列表失败: {e}")
            return ""

    def parse_mirror_list(self, html_content: str):
        """解析镜像列表HTML内容"""

        lines = html_content.split("\n")
        i = 0

        while i < len(lines):
            line = lines[i].strip()
            if "<tr>" in line:
                i = self._process_tr_section(lines, i)
            else:
                i += 1

    def _process_tr_section(self, lines, start_index):
        """处理<tr>到</tr>之间的内容"""
        i = start_index

        # 1) 判断第一个td是否包含country信息
        country_code = None
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if "</tr>" in line:
                return i  # 返回下一个行的索引

            country_match = re.search(r'<div class="country">([^<]+)</div>', line)
            if country_match:
                country_code = country_match.group(1).strip()
                break

            # 2) 搜索包含distribution/leap/15.5/repo的链接
        url_found = False
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if "</tr>" in line:
                return i  # 返回下一个行的索引

            # 如果已经找到URL，继续处理下一行
            if url_found:
                continue

            if 'class="repoperfect"' in line and "href=" in line and '/distribution/leap/15\.5/repo"' in line:
                href_match = re.search(r'href="([^"]+)/leap/15\.5/repo"', line)
                if href_match:
                    url = href_match.group(1).strip()
                    url_found = True
                    if not self.url_exists(self.mirrors, url):
                        mirror_item = {"country": self.get_country_name(country_code), "url": url}
                        # 根据是否为本地国家来决定插入位置
                        if country_code.lower() == self.system_country.lower():
                            self.mirrors.insert(0, mirror_item)
                        else:
                            self.mirrors.append(mirror_item)
                        break

    def get_default_opensuse_mirrors() -> List[Dict]:
        """获取默认的openSUSE镜像列表（备用方案）"""
        default_mirrors = [
            {"country": "Global", "url": "https://download.opensuse.org/"},
            {"country": "Germany", "url": "https://ftp.gwdg.de/pub/linux/opensuse/"},
            {"country": "United States", "url": "https://mirrors.kernel.org/opensuse/"},
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/opensuse/"},
            {"country": "China", "url": "https://mirrors.aliyun.com/opensuse/"},
            {"country": "Japan", "url": "https://ftp.jaist.ac.jp/pub/Linux/openSUSE/"},
            {"country": "United Kingdom", "url": "https://www.mirrorservice.org/sites/download.opensuse.org/"},
            {"country": "France", "url": "https://ftp.free.fr/mirrors/ftp.opensuse.org/"},
            {"country": "Netherlands", "url": "https://ftp.nluug.nl/pub/os/Linux/distr/opensuse/"},
            {"country": "Australia", "url": "https://mirror.aarnet.edu.au/pub/opensuse/"},
        ]
        return default_mirrors

    def run(self):
        """运行完整的测试流程"""
        print("OpenSUSE镜像速度测试工具")
        print("=" * 50)

        # 1. 获取镜像列表
        self.fetch_mirror_list()

        # 2. 测试所有镜像
        start_time = time.time()
        results = self.test_all_mirrors()
        end_time = time.time()
        # 3. 筛选和排序
        top_10 = self.filter_and_rank_mirrors(results)
        if not top_10:
            print("没有找到可用的镜像")
            return

        # 4. 显示结果
        self.print_results(top_10, f"前{len(results)}个最快的OpenSUSE镜像+全球站 (共耗时{end_time - start_time:.2f}秒)")

        # 5. 保存结果
        self.save_results(top_10)

        print(f"\n测试完成! 共测试了 {len(results)} 个镜像")
        print(f"找到 {len([r for r in results if r.success_rate > 0])} 个可用镜像")


def update_source_suse(distro_ostype: str, system_country: str) -> None:
    """主函数"""
    tester = OpenSUSEMirrorTester(distro_ostype, system_country)
    try:
        tester.run()
    except KeyboardInterrupt:
        print("\n\n用户中断了测试")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    update_source_suse()
