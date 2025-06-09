#!/usr/bin/env python3

"""
Linux镜像速度测试工具
从官方镜像列表获取所有镜像，并进行速度测试
"""

import json
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

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from os_info import init_os_info, OSInfo
from system import confirm_action, setup_logging
from msg_handler import error, info, warning
from file_util import print_array

setup_logging()

files_map = {
    "debian": ["ls-lR.gz", "dists/bookworm/main/binary-amd64/Packages.gz"],
    "ubuntu": ["ls-lR.gz", "dists/jammy/main/binary-amd64/Packages.gz"],
    "centos": [
        "filelist.gz",
        "7.9.2009/os/x86_64/repodata/5319616dde574d636861a6e632939f617466a371e59b555cf816cf1f52f3e873-filelists.xml.gz",
    ],
    "rhel": ["repodata/repomd.xml", "RPM-GPG-KEY-redhat-release"],
    "arch": ["core/os/x86_64/core.db.tar.gz", "extra/os/x86_64/extra.db.tar.gz"],
    "opensuse": ["distribution/leap/15.5/repo/oss/ls-lR.gz", "distribution/leap/15.5/repo/oss/INDEX.gz"],
}


@dataclass
class MirrorResult:
    """镜像测试结果"""

    url: str
    url_upd: str
    url_sec: str
    country: str
    avg_speed: float  # KB/s
    response_time: float  # seconds
    success_rate: float  # 0-1
    error_msg: Optional[str] = None


class MirrorTester:
    def __init__(self, system_country):

        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        self.os_info = init_os_info()
        self.system_country = system_country
        self.mirror_list = ""
        self.results = []
        self.mirrors.append(self.globals)  # 添加全球镜像站点
        self.netlocs = set()  # 用于去重的域名集合

    def get_country_name(self, country_code):
        """
        根据国家代码获取国家名称，找不到则返回原国家代码
        例如：'CN' -> 'China', 'USA' -> 'United States of America'
        """
        try:
            country = countries.get(country_code.upper())
            return country.name if country else country_code
        except KeyError:
            return country_code

    def fetch_mirror_list(self, limit: int = None) -> None:
        """读取数据"""
        print(f"{self.os_info.ostype}镜像速度测试工具")
        print("=" * 50)
        try:
            response = requests.get(self.mirror_list, timeout=10)
            response.raise_for_status()
            lines = response.text.split("\n")
            self.mirrors = []
            self.parse_mirror_list(lines)
            if limit:
                self.mirrors = self.mirrors[:limit]  # 限制镜像数量(用于测试)
            self.mirrors.append(self.globals)  # 添加全球镜像站点
        except requests.RequestException as e:
            print(f"获取镜像列表失败: {e}")

    def url_exists(self, mirrors: List[Dict], url: str) -> bool:
        """
        检查URL是否已存在（去重）
        如果是https协议，且已存在相同域名的http镜像，则予以替换
        """
        parsed_new = urlparse(url)
        new_scheme = parsed_new.scheme
        new_domain = parsed_new.netloc
        if not new_domain in self.netlocs:
            self.netlocs.add(new_domain)  # 添加到集合中，避免重复
        elif new_scheme != "https":
            return True
        else:  # 如果是https协议，且已存在相同域名的http镜像，予以替换
            for mirror in mirrors:
                parsed_existing = urlparse(mirror["url"])
                if new_domain == parsed_existing.netloc:
                    mirror["url"] = url  # 新URL是https，旧URL是http，则更新URL
                    return True

        return False

    def test_mirror_speed(self, mirror: dict, limit_cap: float = None, test_count: int = 3) -> MirrorResult:
        """测试单个镜像的速度"""
        url = mirror["url"]
        country = mirror.get("country", "N/A")
        is_global = mirror.get("country") == "Global"

        # 测试文件列表（从小到大）
        test_files = files_map.get(self.os_info.ostype)  # 通常几MB  # 几KB  # 很小

        speeds = []
        max_speed = 0
        response_times = []
        success_count = 0
        error_msg = None

        for i in range(test_count):
            for test_file in test_files:
                try:
                    test_url = urljoin(url + "/", test_file)

                    start_time = time.time()
                    response = self.session.get(test_url, timeout=5, stream=True)  # 6秒超时

                    if response.status_code == 200:
                        # 下载部分数据来测试速度
                        downloaded = 0
                        chunk_start = time.time()

                        for chunk in response.iter_content(chunk_size=8192):
                            downloaded += len(chunk)
                            if downloaded > 100 * 1024:  # 下载100KB后停止
                                break

                        end_time = time.time()
                        elapsed = end_time - chunk_start

                        if elapsed > 0 and downloaded > 0:
                            speed = downloaded / elapsed / 1024  # KB/s

                            # 检查是否超过速率限制 (设置阈值为 < limit_cap的1/3)
                            if limit_cap and not is_global:
                                max_speed = max(max_speed, speed)
                                if max_speed < limit_cap / test_count:
                                    return None  # 超过限制，退出

                            speeds.append(speed)
                            response_times.append(end_time - start_time)
                            success_count += 1
                            break  # 成功就跳出文件循环

                    response.close()

                except Exception as e:
                    error_msg = str(e)
                    continue

            # 在测试之间添加小延迟
            if i < test_count - 1:
                time.sleep(0.5)

        # 计算平均值
        if speeds:
            return MirrorResult(
                url=url,
                url_upd=None,
                url_sec=None,
                country=country,
                avg_speed=statistics.mean(speeds),
                response_time=statistics.mean(response_times),
                success_rate=success_count / test_count,
                error_msg=error_msg if not speeds else None,
            )
        else:
            msg = f"speed: 0 KB/s; url: {url}" + (f"\n{error_msg}" if error_msg else "")
            logging.error(msg)
            return None  # 没有成功的测试

    # 测试所有镜像，仅保留前10个最快的镜像
    def test_all_mirrors(self, max_workers: int = 20, top_n: int = 10) -> List[MirrorResult]:
        """并发测试所有镜像，仅保留前 top_n 个最快镜像，进度单行输出"""

        print(f"开始测试 {len(self.mirrors)} 个镜像，筛选前 {top_n} 个最快镜像，请稍候...")

        lock = threading.Lock()
        fastest_results: List[MirrorResult] = []
        global_result: MirrorResult = None
        limit_cap = None
        completed = 0

        def insert_sorted(results, new_result, top_n):
            """手动插入排序"""
            for i, result in enumerate(results):
                if new_result.avg_speed > result.avg_speed:
                    results.insert(i, new_result)
                    break
            else:
                results.append(new_result)  # 如果新结果是最慢的，添加到末尾

            if len(results) > top_n:  # 保持列表长度不超过 top_n
                results.pop(-1)  # 删除最慢的镜像

        def update_progress():
            nonlocal completed
            completed += 1
            print(
                f"\r进度: {completed}/{len(self.mirrors)} ({completed / len(self.mirrors) * 100:.1f}%)",
                end="",
                flush=True,
            )

        def test_wrapper(mirror):
            nonlocal limit_cap
            nonlocal global_result
            try:
                result = self.test_mirror_speed(mirror, limit_cap)
                if result:
                    if mirror.get("country") == "Global":
                        global_result = result
                    else:
                        with lock:
                            insert_sorted(fastest_results, result, top_n)
                            if len(fastest_results) >= top_n:
                                limit_cap = fastest_results[-1].avg_speed  # 更新速率限制
            except Exception:
                pass  # 静默跳过失败项
            finally:
                update_progress()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(test_wrapper, mirror) for mirror in self.mirrors]
            for future in as_completed(futures):
                future.result()

        # 补充全球镜像Global mirror
        insert_sorted(fastest_results, global_result, top_n + 1)
        print()  # 结束后换行
        return fastest_results

    def filter_and_rank_mirrors(self, results: List[MirrorResult]) -> tuple:
        """筛选和排序镜像"""
        # 过滤掉完全无法访问的镜像
        valid_results = [r for r in results if r.success_rate > 0 and r.avg_speed > 0]

        if not valid_results:
            print("警告: 没有找到可用的镜像!")
            return []

        # 按照综合分数排序（速度 * 成功率 / 响应时间）
        def calculate_score(result: MirrorResult) -> float:
            if result.response_time == 0 or result.response_time == float("inf"):
                return 0
            return (result.avg_speed * result.success_rate) / result.response_time

        # 计算分数并排序
        for result in valid_results:
            result.score = calculate_score(result)

        sorted_results = sorted(valid_results, key=lambda x: x.score, reverse=True)

        # 选择前10个 + global站点
        return sorted_results

    def update_mirror(self) -> bool:
        """是否需要重新选择镜像"""
        curr_url = None
        if len(self.urls) > 0:
            for mirror in self.mirrors:
                if mirror["url"] == self.urls[0]:
                    curr_url = mirror["url"]
                    break

        prompt = f"{'已选镜像: ' + curr_url + ' ' if curr_url else ''}是否重新选择镜像?"
        confirm_action(prompt, self.choose_mirror)

    def choose_mirror(self) -> None:
        """选择最快镜像，并更新包管理器文件"""
        # 1 测试所有镜像
        start_time = time.time()
        results = self.test_all_mirrors()
        end_time = time.time()

        # 2 筛选和排序
        top_10 = self.filter_and_rank_mirrors(results)
        if not top_10:
            print("没有找到可用的镜像")
            return

        # 3 显示结果
        tot_len = len(top_10)
        tot_time = end_time - start_time
        self.print_results(top_10)
        print(f"\n找到前{tot_len-1}个最快的{self.os_info.ostype}镜像 + 全球站 (共耗时{tot_time:.2f}秒)")

        # 3 无限循环直到用户选中合法镜像
        while True:
            print(f"\n请选择要使用的镜像 (1-{tot_len})，输入 0 表示不更改:")

            try:
                # 获取用户输入并去除首尾空格
                choice = input(f"请输入选择 (0-{tot_len}): ").strip()

                # 处理输入为 0 的情况（不更改配置）
                if choice == "0":
                    print("\n已取消配置，保持当前设置")
                    return

                # 将输入转换为整数
                choice_num = int(choice)

                # 检查输入是否在有效范围内
                if 1 <= choice_num <= tot_len:
                    # 获取用户选择的镜像（注意索引从0开始，所以要减1）
                    selected_mirror = top_10[choice_num - 1]

                    # 显示用户选择的镜像信息
                    print(f"\n✨ 您选择了: {selected_mirror.url}")
                    print(f"   下载速度: {selected_mirror.avg_speed:.1f}s")
                    self.check_mirror(selected_mirror)
                    self.update_path(selected_mirror)
                    return
                else:
                    # 输入的数字超出范围
                    error(f"输入错误！请输入 0-{tot_len} 之间的数字")

            except ValueError:
                # 输入的不是数字
                error("输入错误！请输入数字")

            except KeyboardInterrupt:
                # 用户按 Ctrl+C 中断
                print("\n\n已取消操作")
                return

        # 4 保存结果
        self.save_results(top_10)

    def print_results(self, results: List[MirrorResult]):
        """打印测试结果"""
        print()
        print("-" * 80)
        print(f"{'排名':<3} {'速度(KB/s)':<9} {'响应时间(s)':<8} {'成功率':<4} {'国家/地区':<10} {'镜像URL'}")
        print("-" * 80)

        for i, result in enumerate(results, 1):
            print(
                f"{i:<4} {result.avg_speed:>8.1f} {result.response_time:>10.2f} "
                f"{result.success_rate:>10.1%} {result.country:^14} {result.url}"
            )

    def save_results(self, top_10: List[MirrorResult]):
        """保存结果到文件"""

        # 保存为JSON格式
        def result_to_dict(result: MirrorResult) -> dict:
            return {
                "url": result.url,
                "country": result.country,
                "avg_speed_kbps": round(result.avg_speed, 2),
                "response_time_sec": round(result.response_time, 3),
                "success_rate": round(result.success_rate, 3),
                "score": round(getattr(result, "score", 0), 3),
            }

        data = {
            "test_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "top_10_mirrors": [result_to_dict(r) for r in top_10],
        }

        with open("tests/mirror_test_results.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 保存为sources.list格式
        with open("tests/sources_top10.list", "w") as f:
            f.write("# 镜像源配置文件 - 按速度排序的前10个镜像\n")
            f.write(f"# 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            for i, result in enumerate(top_10, 1):
                f.write(f"# 排名 {i} - {result.country} - 速度: {result.avg_speed:.1f} KB/s\n")
                f.write(f"deb {result.url} stable main contrib non-free\n")
                f.write(f"deb-src {result.url} stable main contrib non-free\n\n")

        print(f"\n结果已保存到:")
        print(f"- mirror_test_results.json (详细测试数据)")
        print(f"- sources_top10.list (sources.list格式)")
