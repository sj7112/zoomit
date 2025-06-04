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

from system import setup_logging

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


class MirrorTester:
    def __init__(self, distro_ostype, system_country):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        self.distro_ostype = distro_ostype
        self.system_country = system_country
        self.mirrors = []
        self.default = []
        self.results = []

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

    def url_exists(mirrors: List[Dict], url: str) -> bool:
        """检查URL是否已存在（去重）"""
        parsed_new = urlparse(url)
        new_domain = parsed_new.netloc

        for mirror in mirrors:
            parsed_existing = urlparse(mirror["url"])
            if new_domain == parsed_existing.netloc:
                # 如果新URL是https，旧URL是http，则更新
                if url.startswith("https://") and mirror["url"].startswith("http://"):
                    mirror["url"] = url
                return True

        return False

    def test_mirror_speed(self, mirror: dict, limit_cap: float = None, test_count: int = 3) -> MirrorResult:
        """测试单个镜像的速度"""
        url = mirror["url"]
        country = mirror.get("country", "N/A")

        files_map = {
            "Debian": ["ls-lR.gz", "dists/bookworm/main/binary-amd64/Packages.gz"],
            "Ubuntu": ["ls-lR.gz", "dists/jammy/main/binary-amd64/Packages.gz"],
            "Centos": [
                "filelist.gz",
                "7.9.2009/os/x86_64/repodata/5319616dde574d636861a6e632939f617466a371e59b555cf816cf1f52f3e873-filelists.xml.gz",
            ],
            "RHEL": ["repodata/repomd.xml", "RPM-GPG-KEY-redhat-release"],
            "Arch": ["core/os/x86_64/core.db.tar.gz", "extra/os/x86_64/extra.db.tar.gz"],
            "OpenSUSE": ["repodata/repomd.xml", "content"],
        }
        # 测试文件列表（从小到大）
        test_files = files_map.get(self.distro_ostype)  # 通常几MB  # 几KB  # 很小

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
                    response = self.session.get(test_url, timeout=6, stream=True)  # 6秒超时

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
                            if limit_cap:
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
            try:
                result = self.test_mirror_speed(mirror, limit_cap)
                if not result:
                    return  # 异常退出
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

        # 补充测试全球镜像
        result = self.test_mirror_speed(self.globals)
        fastest_results.append(result) if result else None
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

    def print_results(self, results: List[MirrorResult], title: str):
        """打印测试结果"""
        print(f"\n{'='*80}")
        print(f"{title}")
        print(f"{'='*80}")
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

        with open("mirror_test_results.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        # 保存为sources.list格式
        with open("sources_top10.list", "w") as f:
            f.write("# 镜像源配置文件 - 按速度排序的前10个镜像\n")
            f.write(f"# 测试时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            for i, result in enumerate(top_10, 1):
                f.write(f"# 排名 {i} - {result.country} - 速度: {result.avg_speed:.1f} KB/s\n")
                f.write(f"deb {result.url} stable main contrib non-free\n")
                f.write(f"deb-src {result.url} stable main contrib non-free\n\n")

        print(f"\n结果已保存到:")
        print(f"- mirror_test_results.json (详细测试数据)")
        print(f"- sources_top10.list (sources.list格式)")
