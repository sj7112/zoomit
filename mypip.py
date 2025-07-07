#!/usr/bin/env python3

"""
global pip speed tester, automatically selects the fastest pip mirror
"""

import time
import subprocess
import sys
import concurrent.futures


# Global pip mirrors
GLOBAL_MIRRORS = {
    # official
    "PyPI (Official)": "https://pypi.org/simple/",
    # Asia
    "tsinghua (China)": "https://pypi.tuna.tsinghua.edu.cn/simple/",
    "aliyun (China)": "https://mirrors.aliyun.com/pypi/simple/",
    "ustc (China)": "https://pypi.mirrors.ustc.edu.cn/simple/",
    "huaweicloud (China)": "https://mirrors.huaweicloud.com/repository/pypi/simple/",
    "douban (China)": "https://pypi.douban.com/simple/",
    "tencent (China)": "https://mirrors.cloud.tencent.com/pypi/simple/",
    "KAIST (Korea)": "https://mirror.kakao.com/pypi/simple/",
    "JAIST (Japan)": "https://ftp.jaist.ac.jp/pub/pypi/simple/",
    # Europe
    "GARR (Italy)": "https://pypi.mirror.garr.it/simple/",
    "University of Crete (Greece)": "https://pypi.cc.uoc.gr/simple/",
    # North America
    "CMU (US)": "https://pypi.cmu.edu/simple/",
    # Australia
    "AARNET (Australia)": "https://pypi.aarnet.edu.au/simple/",
}


def msg_parse_tmpl(template, *args):
    for i, var in enumerate(args):
        template = template.replace("{}", str(var), 1)  # replace the frist {}
        template = template.replace(f"{{{i}}}", str(var))  # replace all {i}

    return template


def test_mirror_speed(mirror_name, mirror_url, timeout=10):
    """speed test for a single mirror"""

    start_time = time.time()
    try:
        # use --dry-run to test the speed
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--dry-run",
                "--quiet",
                "--no-deps",
                "--index-url",
                mirror_url,
                "requests",  # using a common package to test speed
            ],
            capture_output=True,
            timeout=timeout,
            text=True,
        )

        end_time = time.time()

        if result.returncode == 0:
            response_time = end_time - start_time
            return {"name": mirror_name, "url": mirror_url, "time": response_time, "status": "success"}
        else:
            return {
                "name": mirror_name,
                "url": mirror_url,
                "time": float("inf"),
                "status": "failed",
                "error": result.stderr,
            }

    except subprocess.TimeoutExpired:
        return {"name": mirror_name, "url": mirror_url, "time": float("inf"), "status": "timeout"}
    except Exception as e:
        return {"name": mirror_name, "url": mirror_url, "time": float("inf"), "status": "error", "error": str(e)}


def test_pip_mirrors(max_workers=5):
    """test speed for all mirrors concurrently"""
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_mirror = {
            executor.submit(test_mirror_speed, name, url): (name, url) for name, url in GLOBAL_MIRRORS.items()
        }

        for future in concurrent.futures.as_completed(future_to_mirror):
            result = future.result()
            results.append(result)

    # show result: Sort by speed
    successful_results = [r for r in results if r["status"] == "success"]
    failed_results = [r for r in results if r["status"] != "success"]

    successful_results.sort(key=lambda x: x["time"])
    return successful_results, failed_results


def main():
    """Test all mirrors and return the result"""
    mirror_list, failed_list = test_pip_mirrors()
    if mirror_list:
        with open("/tmp/mypip_mirror_list.log", "w", encoding="utf-8") as fh:
            for value in mirror_list:
                line = f"{value['status']}|{value['name']}|{value['url']}|{value['time']}"
                fh.write(f"{line}\n")
            for value in failed_list:
                line = f"{value['status']}|{value['name']}|{value['url']}"
                fh.write(f"{line}\n")
        sys.exit(0)

    sys.exit(1)


if __name__ == "__main__":
    main()
