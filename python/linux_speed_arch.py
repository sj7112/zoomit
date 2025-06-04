#!/usr/bin/env python3

"""
Arch镜像速度测试工具
从官方镜像列表获取所有镜像，并进行速度测试
"""

import os
import re
import sys
import time
import requests
from urllib.parse import urlparse
from dataclasses import dataclass
from typing import Dict, List, Optional
from iso3166 import countries

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from file_util import print_array
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


class ArchMirrorTester(MirrorTester):
    def __init__(self, distro_ostype, system_country):
        super().__init__(distro_ostype, system_country)
        self.globals = {"country": "Global", "url": "https://geo.mirror.pkgbuild.com/"}

    def fetch_mirror_list(self) -> str:
        """读取数据"""
        try:
            response = self.session.get("https://archlinux.org/mirrorlist/?country=all", timeout=10)
            response.raise_for_status()
            self.parse_mirror_list(response.text)
        except requests.RequestException as e:
            print(f"获取镜像列表失败: {e}")
            return ""

    def parse_mirror_list(self, content: str) -> List[Dict]:
        """解析镜像列表内容"""
        lines = content.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # 匹配国家名称 (## Country Name)
            country_match = re.match(r"^##\s+(.+)$", line)
            if country_match:
                current_country = country_match.group(1).strip()

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
                        if self.is_valid_url(url) and not self.url_exists(mirrors_country, url):
                            mirrors_country.append({"country": current_country, "url": url})

                    i += 1

                # 将mirrors_country添加到mirrors中
                if mirrors_country:
                    country_name = self.get_country_name(self.system_country)
                    # 如果国家匹配输入参数，添加到前面；否则从尾部添加
                    if country_name and country_name.lower() in current_country.lower():
                        self.mirrors = mirrors_country + self.mirrors
                    else:
                        self.mirrors.extend(mirrors_country)

            i += 1

    def is_valid_url(self, url: str) -> bool:
        """检查URL是否有效"""
        try:
            result = urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False

    def run(self):
        """运行完整的测试流程"""
        print("Arch镜像速度测试工具")
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
        self.print_results(top_10, f"前{len(results)}个最快的Arch镜像+全球站 (共耗时{end_time - start_time:.2f}秒)")

        # 5. 保存结果
        self.save_results(top_10)

        print(f"\n测试完成! 共测试了 {len(results)} 个镜像")
        print(f"找到 {len([r for r in results if r.success_rate > 0])} 个可用镜像")


def update_source_arch(distro_ostype: str, system_country: str) -> None:
    """主函数"""
    tester = ArchMirrorTester(distro_ostype, system_country)
    try:
        tester.run()
    except KeyboardInterrupt:
        print("\n\n用户中断了测试")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    update_source_arch()
