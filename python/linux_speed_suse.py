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

from linux_speed import MirrorTester


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
        # 后备镜像列表：全球常用的 10 个镜像站点

        self.mirrors = [
            # 北美镜像
            {"country": "US", "url": "https://mirrors.kernel.org/opensuse/"},
            {"country": "US", "url": "https://mirror.math.princeton.edu/pub/opensuse/"},
            # 欧洲镜像
            {"country": "Germany", "url": "https://ftp.fau.de/opensuse/"},
            {"country": "Germany", "url": "https://ftp.halifax.rwth-aachen.de/opensuse/"},
            {"country": "UK", "url": "https://www.mirrorservice.org/sites/download.opensuse.org/"},
            {"country": "Netherlands", "url": "https://ftp.nluug.nl/pub/os/Linux/distr/opensuse/"},
            {"country": "Italy", "url": "https://opensuse.mirror.garr.it/opensuse/"},
            {"country": "Sweden", "url": "https://ftp.lysator.liu.se/pub/opensuse/"},
            # 亚太镜像
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
            # 南美和其他地区
            {"country": "Brazil", "url": "https://opensuse.c3sl.ufpr.br/"},
            {"country": "Brazil", "url": "https://mirror.ufscar.br/opensuse/"},
            {"country": "Argentina", "url": "https://mirror.fcaglp.unlp.edu.ar/opensuse/"},
            {"country": "South Africa", "url": "https://opensuse.mirror.ac.za/"},
            {"country": "Russia", "url": "https://mirror.yandex.ru/opensuse/"},
            {"country": "Turkey", "url": "https://ftp.linux.org.tr/opensuse/"},
        ]

        self.globals = {"country": "Global", "url": "https://download.opensuse.org/"}
        super().__init__(distro_ostype, system_country)
        self.mirror_list = "https://mirrors.opensuse.org/"

    def parse_mirror_list(self, lines: List[str]):
        """解析镜像列表HTML内容"""

        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if "<tr>" in line and not "</tr>" in line:  # 只处理<tr>开始的多行文本
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

        # 2) 搜索包含distribution/leap/15.5/repo的链接
        while i < len(lines):
            line = lines[i].strip()
            i += 1  # 当前行处理完毕，指针跳到下一行
            if "</tr>" in line:
                return i  # 返回下一行索引

            href_match = re.search(r'href="([^"]+)distribution/leap/15\.5/repo"', line)
            if href_match:
                mirror_item = {
                    "country": self.get_country_name(country_code),
                    "url": href_match.group(1).strip(),
                }
                # 根据是否为本地国家来决定插入位置
                if country_code.lower() == self.system_country.lower():
                    self.mirrors.insert(0, mirror_item)
                else:
                    self.mirrors.append(mirror_item)
                return i  # 返回下一行索引

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
