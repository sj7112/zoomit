#!/usr/bin/env python3

"""
Ubuntu镜像速度测试工具
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


class UbuntuMirrorTester(MirrorTester):
    def __init__(self, distro_ostype, system_country):
        super().__init__(distro_ostype, system_country)
        self.globals = {"country": "Global", "url": "https://archive.ubuntu.com/ubuntu/"}

    def get_countries_list(self) -> List[str]:
        """获取所有国家/地区的镜像列表"""
        try:
            response = requests.get("http://mirrors.ubuntu.com/", timeout=10)
            response.raise_for_status()

            # 提取国家代码
            countries = re.findall(r'<a href="([A-Z]{2})\.txt', response.text)
            return sorted(set(countries))
        except requests.RequestException as e:
            print(f"获取国家列表失败: {e}")
            return []

    def get_mirrors_by_country(self, country_code: str) -> List[str]:
        """根据国家代码获取镜像列表"""
        try:
            url = f"http://mirrors.ubuntu.com/{country_code}.txt"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            # 提取HTTP镜像地址
            for line in response.text.splitlines():
                line = line.strip()
                if line.startswith(("http://", "https://")):
                    self.mirrors.append({"url": line})

            print(f"找到 {len(self.mirrors)} 个镜像")

        except requests.RequestException as e:
            print(f"获取 {country_code} 镜像列表失败: {e}")

        if not self.mirrors:
            self.mirrors = self._get_fallback_mirrors()  # 默认镜像列表

    def _get_fallback_mirrors(self) -> List[dict]:
        """后备镜像列表：全球常用的 10 个 Ubuntu 镜像站点"""
        return [
            # 欧洲镜像
            {"country": "Germany", "url": "http://ftp.halifax.rwth-aachen.de/ubuntu/"},
            {"country": "UK", "url": "http://mirror.bytemark.co.uk/ubuntu/"},
            {"country": "France", "url": "http://ftp.rezopole.net/ubuntu/"},
            {"country": "Netherlands", "url": "http://mirror.nl.leaseweb.net/ubuntu/"},
            {"country": "Sweden", "url": "http://ftp.acc.umu.se/mirror/ubuntu.com/ubuntu/"},
            # 美洲镜像
            {"country": "USA", "url": "http://mirror.math.princeton.edu/pub/ubuntu/"},
            # 亚太镜像
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/ubuntu/"},
            {"country": "Japan", "url": "http://ftp.jaist.ac.jp/pub/Linux/ubuntu/"},
            {"country": "Singapore", "url": "http://mirror.nus.edu.sg/ubuntu/"},
            {"country": "Australia", "url": "http://mirror.aarnet.edu.au/Ubuntu/"},
        ]

    def fetch_mirror_list(self) -> None:
        """主函数：计算最快的镜像并保存到文件"""
        # 获取所有国家列表
        countries = self.get_countries_list()
        if not countries:
            return

        # 交互式选择国家
        while True:
            user_input = input(f"请选择国家/地区代码（回车使用默认值 '{self.system_country}'）：").strip().upper()
            country_code = user_input if user_input else self.system_country

            if country_code not in countries:
                print(f"国家代码 {country_code} 不存在于列表中！请核对 http://mirrors.ubuntu.com/")
                continue

            self.get_mirrors_by_country(country_code)
            break

    def run(self):
        """运行完整的测试流程"""
        print("Ubuntu镜像速度测试工具")
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
        self.print_results(top_10, f"前{len(results)}个最快的Ubuntu镜像+全球站 (共耗时{end_time - start_time:.2f}秒)")

        # 5. 保存结果
        self.save_results(top_10)

        print(f"\n测试完成! 共测试了 {len(results)} 个镜像")
        print(f"找到 {len([r for r in results if r.success_rate > 0])} 个可用镜像")


def update_source_ubt(distro_ostype: str, system_country: str) -> None:
    """主函数"""
    tester = UbuntuMirrorTester(distro_ostype, system_country)
    try:
        tester.run()
    except KeyboardInterrupt:
        print("\n\n用户中断了测试")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    update_source_ubt()
