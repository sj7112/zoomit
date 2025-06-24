#!/usr/bin/env python3

"""Linux Mirror Speed Tester (Base Class)"""

import logging
import os
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

from os_info import get_os_info
from system import confirm_action, setup_logging
from cmd_handler import cmd_ex_be, refresh_pm, upgrade_pm
from msg_handler import error, info, warning
from file_util import write_array

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


def _is_url_accessible(url: str) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    try:
        response = requests.head(url, headers=headers, timeout=5, allow_redirects=True)
        return response.status_code == 200
    except:
        return False


@dataclass
class MirrorResult:

    url: str
    url_upd: str  # debin | ubuntu
    url_sec: str  # debin | ubuntu
    country: str
    avg_speed: float  # KB/s
    response_time: float  # seconds
    success_rate: float  # 0-1
    error_msg: Optional[str] = None


def get_country_name(country_code):
    """
    Get the country name; if not found, return the country code.
    e.g. 'CN' -> 'China', 'USA' -> 'United States of America'
    """
    try:
        country = countries.get(country_code.upper())
        return country.name if country else country_code
    except KeyError:
        return country_code


class MirrorTester:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
            }
        )
        self.os_info = get_os_info()
        self.system_country = os.environ.get("LANGUAGE").split("_")[1].split(":")[0]
        self.mirror_list = ""
        self.netlocs = set()  # 用于去重的域名集合
        self.is_debug = os.environ.get("DEBUG") == "1"  # 测试标志

    def fetch_mirror_list(self, limit: int = None) -> None:
        print(f"{self.os_info.ostype}镜像速度测试工具")
        print("=" * 50)
        try:
            response = requests.get(self.mirror_list, timeout=10)
            response.raise_for_status()
            lines = response.text.split("\n")
            self.mirrors = []
            self.parse_mirror_list(lines)
            if limit:
                self.mirrors = self.mirrors[:limit]  # mirrors limitation(for testing)
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

        url = mirror.get("url")

        test_files = files_map.get(self.os_info.ostype)  # medium size files, usually 100k ~ 10m

        speeds = []
        max_speed = 0
        response_times = []
        success_count = 0
        error_msg = None

        for i in range(test_count):
            for test_file in test_files:
                try:
                    test_url = urljoin(url + "/", test_file)

                    if self.cancelled.is_set():
                        return None  # 强行中断，退出

                    start_time = time.time()
                    response = self.session.get(test_url, timeout=5, stream=True)  # 5秒超时

                    if self.cancelled.is_set():
                        return None  # 强行中断，退出

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
                url_upd=None,
                url_sec=None,
                country=mirror.get("country", "N/A"),
                avg_speed=statistics.mean(speeds),
                response_time=statistics.mean(response_times),
                success_rate=success_count / test_count,
                error_msg=error_msg if not speeds else None,
            )
        else:
            msg = f"speed: 0 KB/s; url: {url}" + (f"\n{error_msg}" if error_msg else "")
            logging.error(msg)
            return None  # 没有成功的测试

    def current_mirror(self):
        """Check if the currently selected mirror is valid"""
        curr_url = None
        if len(self.urls) > 0:
            for mirror in self.mirrors:
                if mirror["url"] == self.urls[0]:
                    curr_url = mirror["url"]
                    break
        return curr_url

    def test_all_mirrors(self, max_workers: int = 20, top_n: int = 10) -> List[MirrorResult]:
        """Test speed for all mirrors, only keep top_10"""

        print(f"开始测试 {len(self.mirrors)} 个镜像，筛选前 {top_n} 个最快镜像，请稍候...")

        start_time = time.time()

        lock = threading.Lock()
        fastest_results: List[MirrorResult] = []
        limit_cap = None
        completed = 0
        self.cancelled = threading.Event()

        def insert_sorted(results, new_result, top_n):
            """Manual insertion sort"""
            for i, result in enumerate(results):
                if new_result.avg_speed > result.avg_speed:
                    results.insert(i, new_result)
                    break
            else:
                results.append(new_result)  # If the new one is the slowest, add to the end

            if len(results) > top_n:  # The list length <= top_n
                results.pop(-1)  # Remove the slowest mirror

        def update_progress():
            """Update progress bar"""
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
                if result:
                    with lock:
                        insert_sorted(fastest_results, result, top_n)
                        if len(fastest_results) >= top_n:
                            limit_cap = fastest_results[-1].avg_speed  # update speed limit cap
            except Exception:
                pass
            finally:
                if not self.cancelled.is_set():
                    update_progress()

        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = [executor.submit(test_wrapper, mirror) for mirror in self.mirrors]
            for future in as_completed(futures):
                if not self.cancelled.is_set():
                    future.result(timeout=1)  # Set timeout to avoid long waits

        except KeyboardInterrupt:
            print("\n检测到 Ctrl+C，停止剩余任务...")
            # Immediately shut down the thread pool without waiting for unfinished tasks
            executor.shutdown(wait=False)
            self.cancelled.set()

        print()  # return line
        end_time = time.time()

        # 2 筛选和排序
        top_10 = self.filter_and_rank_mirrors(fastest_results)
        if not top_10:
            print("没有找到可用的镜像")
            return

        # 3 print the result
        tot_time = end_time - start_time
        self.print_results(top_10)
        print(f"\n找到前{len(top_10)}个最快的{self.os_info.ostype}镜像 (共耗时{tot_time:.2f}秒)")

        return top_10

    def filter_and_rank_mirrors(self, results: List[MirrorResult]) -> tuple:
        """Filter and rank mirrors"""
        # Remove mirrors that are completely inaccessible
        valid_results = [r for r in results if r.success_rate > 0 and r.avg_speed > 0]

        if not valid_results:
            print("警告: 没有找到可用的镜像!")
            return []

        # Sort by composite score (speed * success rate / response time)
        def calculate_score(result: MirrorResult) -> float:
            if result.response_time == 0 or result.response_time == float("inf"):
                return 0
            return (result.avg_speed * result.success_rate) / result.response_time

        # Calculate scores and sort
        for result in valid_results:
            result.score = calculate_score(result)

        # Select the top 10 sites
        return sorted(valid_results, key=lambda x: x.score, reverse=True)

    def choose_mirror(self) -> None:
        """Select the fastest mirror and update the package manager file"""

        top_10 = self.test_all_mirrors()
        tot_len = len(top_10)

        while True:
            print(f"\n请选择要使用的镜像 (1-{tot_len})，输入 0 表示不更改:")

            try:
                # Get user input
                choice = input(f"请输入选择 (0-{tot_len}): ").strip()

                # Special case: input is 0
                if choice == "0":
                    print("\n已取消配置，保持当前设置")
                    return 1

                # Convert input to an integer
                choice_num = int(choice)

                if 1 <= choice_num <= tot_len:
                    # Get the user-selected mirror
                    selected_mirror = top_10[choice_num - 1]

                    print(f"\n✨ 您选择了: {selected_mirror.url}")
                    print(f"   下载速度: {selected_mirror.avg_speed:.1f}s")

                    self.update_pm_file(selected_mirror)  # Update PM configuration file
                    return refresh_pm()  # refresh PM configuration
                else:
                    # Input number is out of range
                    error(f"Invalid input! Please enter a number between 0-{tot_len}")

            except ValueError:
                # Input is not a number
                error("Invalid input! Please enter a number")

            except KeyboardInterrupt:
                # User interrupted with Ctrl+C
                print("\n\nOperation canceled\n")
                return 2

    def print_results(self, results: List[MirrorResult]):
        print()
        print("-" * 80)
        print(f"{'排名':<3} {'速度(KB/s)':<9} {'响应时间(s)':<8} {'成功率':<4} {'国家/地区':<10} {'镜像URL'}")
        print("-" * 80)

        for i, result in enumerate(results, 1):
            print(
                f"{i:<4} {result.avg_speed:>8.1f} {result.response_time:>10.2f} "
                f"{result.success_rate:>10.1%} {result.country:^14} {result.url}"
            )

    def run(self):
        """主函数：运行完整的测试流程"""
        try:
            # 1. get source file with mirror list
            self.find_mirror_source()
            if not self.path:
                print(f"没有找到{self.os_info.package_mgr}源配置文件")
                return

            # 2. fetch all active mirrors
            self.fetch_mirror_list(12 if self.is_debug else None)

            # 3. update mirrors
            curr_url = self.current_mirror()
            prompt = f"{'已选镜像: ' + curr_url + ' ' if curr_url else ''}是否重新选择镜像?"
            confirm_action(prompt, self.choose_mirror)
        # except KeyboardInterrupt:
        #     print("\n\n用户中断了测试")
        except Exception as e:
            print(f"\n程序运行出错: {e}")
            import traceback

            traceback.print_exc()

        finally:
            prompt = "是否立刻升级软件包?"
            confirm_action(prompt, upgrade_pm)  # upgrade PM configuration
