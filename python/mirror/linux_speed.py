#!/usr/bin/env python3

"""Linux Mirror Speed Tester (Base Class)"""

import logging
import os
from pathlib import Path
import sys
import time
import threading
from iso3166 import countries
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))  # add root sys.path

from python.cache.os_info import OSInfoCache
from python.system import setup_logging
from python.read_util import confirm_action
from python.cmd_handler import pm_refresh, pm_upgrade
from python.msg_handler import _mf, error, info, string, warning
from python.file_util import write_array

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
        self.os_info = OSInfoCache.get_instance().get()
        self.system_country = os.environ.get("LANGUAGE").split("_")[1].split(":")[0]
        self.path = None  # package management configuation file
        self.urls = []  # urls in the core configuration file
        self.curr_mirror = None
        self.mirror_list = ""
        self.netlocs = set()  # Unique domain names set (domain support both https and http, use https)
        self.is_debug = os.environ.get("DEBUG") == "0"  # debug flag

    def fetch_mirror_list(self, limit: int = None) -> None:
        string(r"{} Mirror Speed Testing Tool", self.os_info.ostype)
        print("=" * 80)
        try:
            response = requests.get(self.mirror_list, timeout=10)
            response.raise_for_status()
            lines = response.text.split("\n")
            self.mirrors = []
            self.parse_mirror_list(lines)
            if limit:
                self.mirrors = self.mirrors[:limit]  # mirrors limitation(for testing)
        except requests.RequestException as e:
            string(r"Failed to fetch the mirror list: {}", e)

    def url_exists(self, mirrors: List[Dict], url: str) -> bool:
        """
        Check if the URL already exists (deduplication).
        If the protocol is HTTPS and an HTTP mirror with the same domain already exists, replace it.
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

    def test_all_mirrors(self, max_workers: int = 20, top_n: int = 10) -> List[MirrorResult]:
        """Test speed for all mirrors, only keep top_10"""

        string(
            r"Starting to test {} mirrors, filtering the top {} fastest mirrors, please wait...",
            len(self.mirrors),
            top_n,
        )

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

        progress = _mf("Progress")

        def update_progress():
            """Update progress bar"""
            nonlocal completed
            completed += 1
            print(
                f"\r{progress}: {completed}/{len(self.mirrors)} ({completed / len(self.mirrors) * 100:.1f}%)",
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
            print()
            string("Ctrl+C detected, stopping remaining tasks...")
            # Immediately shut down the thread pool without waiting for unfinished tasks
            executor.shutdown(wait=False)
            self.cancelled.set()

        print()  # return line

        # 1 filter：Remove mirrors that are completely inaccessible
        results = [r for r in fastest_results if r.success_rate > 0 and r.avg_speed > 0]
        if not results:
            return None

        # 2 sort the results
        top_10 = self.filter_and_rank_mirrors(results)

        # 3 print the result
        self.print_results(top_10)
        end_time = time.time()
        tot_time = f"{end_time - start_time:.2f}"
        print()
        string(r"Found top {} fastest {} mirrors (total time: {} seconds)", len(top_10), self.os_info.ostype, tot_time)

        return top_10

    def filter_and_rank_mirrors(self, results: List[MirrorResult]) -> tuple:
        """Filter and rank mirrors"""

        # Sort by composite score (speed * success rate / response time)
        def calculate_score(result: MirrorResult) -> float:
            if result.response_time == 0 or result.response_time == float("inf"):
                return 0
            return (result.avg_speed * result.success_rate) / result.response_time

        # Calculate scores and sort
        for result in results:
            result.score = calculate_score(result)

        # Select the top 10 sites
        return sorted(results, key=lambda x: x.score, reverse=True)

    def choose_mirror(self) -> None:
        """Select the fastest mirror and update the package manager file"""
        # fetch all active mirrors
        self.fetch_mirror_list(12 if self.is_debug else None)

        top_10 = self.test_all_mirrors()
        if not top_10:
            string("No available mirrors found")
            return 3

        def do_choose_mirror(choice: int) -> int:
            # Special case: input is 0
            if choice == 0:
                print()
                string("Configuration cancelled, keeping current settings")
                return 1

            # Get the user-selected mirror
            selected_mirror = top_10[choice - 1]
            print()
            print(f"✨ {_mf('You selected')}: {selected_mirror.url}")
            print(f"   {_mf('Download speed')}: {selected_mirror.avg_speed:.1f}s")

            self.update_pm_file(selected_mirror)  # Update PM configuration file
            return pm_refresh()  # refresh PM configuration

        def valid_choose_mirror(choice: int, error_msg: str) -> int:
            if 0 <= choice <= tot_len:
                return 0  # valid input

            print(error_msg)
            return 2  # invalid, continue

        tot_len = len(top_10)
        string(r"Please select a mirror to use (1-{}), enter 0 to keep current settings", tot_len)
        prompt = _mf(r"Please enter your choice (0-{}): ", tot_len)
        error_msg = _mf(r"Invalid input! Please enter a number between 0-{}", tot_len)
        confirm_action(
            prompt,
            do_choose_mirror,
            option="number",
            no_value=0,
            to_value=1,
            err_handle=valid_choose_mirror,
            error_msg=error_msg,
        )

    def print_results(self, results: List[MirrorResult]):
        print()
        print("-" * 80)
        print(
            f"{_mf('Rank'):<4} {_mf('Speed(KB/s)'):<8} {_mf('Resp Time(s)'):<6} {_mf('Succ Rate'):<6} {_mf('Country/Region'):<16} {_mf('Mirror URL')}"
        )
        print("-" * 80)

        for i, result in enumerate(results, 1):
            print(
                f"{i:<4}{result.avg_speed:>9.1f}{result.response_time:>11.2f}{result.success_rate:>11.1%}{result.country:^18}{result.url}"
            )

    def run(self):
        """Main function: Run the complete testing process"""
        try:
            # 1. get source file with mirror list
            self.find_mirror_source()
            if not self.path:
                string(r"Could not find the {} source configuration file", self.os_info.package_mgr)
                return

            default = True
            prompt = _mf("Would you like to reselect a mirror?")
            if self.curr_mirror:
                string(r"Current {} mirror: {}", self.os_info.package_mgr, self.curr_mirror)
                default = False

            # 2. update mirrors
            ret_code = confirm_action(prompt, self.choose_mirror, no_value=default)
            default = ret_code == 0
        except Exception as e:
            print()
            string(r"An error occurred during program execution: {}", e)
            import traceback

            traceback.print_exc()

        finally:
            # 3. upgrade PM configuration
            print()
            prompt = _mf("Would you like to upgrade the packages immediately?")
            confirm_action(prompt, pm_upgrade, no_value=default)
