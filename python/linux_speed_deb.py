#!/usr/bin/env python3

"""
Debian镜像速度测试工具
从官方镜像列表获取所有镜像，并进行速度测试
"""

import logging
import os
import re
import sys
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import statistics
from dataclasses import dataclass
from typing import List, Optional
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


class DebianMirrorTester(MirrorTester):
    def __init__(self, distro_ostype, system_country):
        super().__init__(distro_ostype, system_country)
        self.globals = {"country": "Global", "url": "https://deb.debian.org/debian"}

    def fetch_mirror_list(self) -> List[dict]:
        """从官方页面获取镜像列表"""
        print("正在获取Debian官方镜像列表...")

        try:
            response = self.session.get("https://www.debian.org/mirror/mirrors_full", timeout=10)
            response.raise_for_status()
            lines = response.text.splitlines()

            i = 0
            self.default = []
            self.mirrors = []

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
                        self.default = country_mirrors
                        self.mirrors = country_mirrors + self.mirrors
                    else:
                        self.mirrors.extend(country_mirrors)

                else:
                    i += 1

        except Exception as e:
            print(f"获取镜像列表失败: {e}")

        if not self.default:
            self.default = self._get_fallback_mirrors()  # 默认镜像列表
            if not self.mirrors:
                self.mirrors = self.default  # 使用后备镜像列表

    def _get_fallback_mirrors(self) -> List[dict]:
        """后备镜像列表：全球常用的 10 个 Debian 镜像站点"""
        return [
            # 欧洲镜像
            {"country": "Germany", "url": "http://ftp.de.debian.org/debian/"},
            {"country": "UK", "url": "http://mirrorservice.org/sites/ftp.debian.org/debian/"},
            {"country": "France", "url": "http://ftp.fr.debian.org/debian/"},
            {"country": "Netherlands", "url": "http://ftp.nl.debian.org/debian/"},
            # 美洲镜像
            {"country": "USA", "url": "http://ftp.us.debian.org/debian/"},
            {"country": "Brazil", "url": "http://ftp.br.debian.org/debian/"},
            # 亚太镜像
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/debian/"},
            {"country": "Japan", "url": "http://ftp.jp.debian.org/debian/"},
            {"country": "Singapore", "url": "http://mirror.nus.edu.sg/debian/"},
            {"country": "Australia", "url": "http://ftp.au.debian.org/debian/"},
        ]

    def run(self):
        """运行完整的测试流程"""
        print("Debian镜像速度测试工具")
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
        self.print_results(top_10, f"前{len(results)}个最快的Debian镜像+全球站 (共耗时{end_time - start_time:.2f}秒)")

        # 5. 保存结果
        self.save_results(top_10)

        print(f"\n测试完成! 共测试了 {len(results)} 个镜像")
        print(f"找到 {len([r for r in results if r.success_rate > 0])} 个可用镜像")


def update_source_deb(distro_ostype: str, system_country: str) -> None:
    """主函数"""
    tester = DebianMirrorTester(distro_ostype, system_country)
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
