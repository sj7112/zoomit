#!/usr/bin/env python3

"""
Centos镜像速度测试工具
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
from typing import Dict, List, Optional
import json

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from linux_speed import MirrorTester


class CentosMirrorTester(MirrorTester):
    def __init__(self, system_country):
        # 镜像列表：全球常用的 13 个镜像站点
        self.mirrors = [
            # 欧洲镜像
            {"country": "Germany", "url": "https://ftp.plusline.net/centos-vault/"},
            {"country": "Germany", "url": "https://mirror.rackspeed.de/centos/"},
            # 北美镜像
            {"country": "US", "url": "https://mirror.math.princeton.edu/pub/centos-vault/"},
            # 亚太镜像
            {"country": "China", "url": "https://mirrors.aliyun.com/centos-vault/"},
            {"country": "China", "url": "https://mirrors.tuna.tsinghua.edu.cn/centos-vault/"},
            {"country": "China", "url": "https://mirrors.ustc.edu.cn/centos-vault/"},
            {"country": "China", "url": "https://mirrors.163.com/centos-vault/"},
            {"country": "China", "url": "https://mirrors.huaweicloud.com/centos-vault/"},
            {"country": "Japan", "url": "https://ftp.riken.jp/Linux/centos-vault/"},
            {"country": "Korea", "url": "https://mirror.kakao.com/centos/"},
            {"country": "Australia", "url": "https://mirror.aarnet.edu.au/pub/centos/"},
            # 南美和其他地区
            {"country": "Colombia", "url": "http://mirror.unimagdalena.edu.co/centos/"},
            {"country": "Brazil", "url": "http://ftp.unicamp.br/pub/centos/"},
        ]
        self.globals = {"country": "Global", "url": "https://vault.centos.org/"}
        super().__init__(system_country)

    def fetch_mirror_list(self) -> None:
        print("Centos镜像速度测试工具")
        print("=" * 50)

    def run(self):
        """运行完整的测试流程"""
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
        self.print_results(top_10, f"前{len(results)}个最快的Centos镜像+全球站 (共耗时{end_time - start_time:.2f}秒)")

        # 5. 保存结果
        self.save_results(top_10)

        print(f"\n测试完成! 共测试了 {len(results)} 个镜像")
        print(f"找到 {len([r for r in results if r.success_rate > 0])} 个可用镜像")


def update_source_cos(system_country: str) -> None:
    """主函数"""
    tester = CentosMirrorTester(system_country)
    try:
        tester.run()
    except KeyboardInterrupt:
        print("\n\n用户中断了测试")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    update_source_cos()
