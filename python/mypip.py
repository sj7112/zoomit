#!/usr/bin/env python3

"""
global pip speed tester, automatically selects the fastest pip mirror
"""

import os
import time
import subprocess
import sys
import concurrent.futures
from urllib.parse import urlparse

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


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

    """显示测试结果"""
    # 按速度排序
    successful_results = [r for r in results if r["status"] == "success"]
    failed_results = [r for r in results if r["status"] != "success"]

    successful_results.sort(key=lambda x: x["time"])

    if successful_results:
        # 计算每列的最大宽度
        name_width = max(len(r["name"]) for r in successful_results) + 4
        url_width = max(len(r["url"]) for r in successful_results) + 4

        # 打印表头
        print(f"{'序号':<4} {'镜像名':<{name_width}} {'URL地址':<{url_width - 4}} 耗时")
        print("-" * (4 + name_width + url_width + 12))

        # 打印数据行
        for i, result in enumerate(successful_results, 1):
            time_str = f"{result['time']:.2f}s"
            print(f"{i:<4} {result['name']:<{name_width}} {result['url']:<{url_width}} {time_str:>8}")

        fastest = successful_results[0]
        print(f"\n🚀 最快镜像: {fastest['name']}")
        print(f"   URL地址: {fastest['url']}")
        print(f"   响应时间: {fastest['time']:.2f}s")

        return successful_results

    if failed_results:
        print(f"\n❌ 失败的镜像 ({len(failed_results)}个):")

        # 计算失败结果的列宽
        name_width = max(len(r["name"]) for r in failed_results) + 4
        url_width = max(len(r["url"]) for r in failed_results) + 4

        # 打印失败结果的表头
        print(f"{'镜像名':<{name_width}} {'URL地址':<{url_width}} {'状态':>8}")
        print("-" * (name_width + url_width + 8))

        for result in failed_results:
            status_msg = {"timeout": "超时", "failed": "失败", "error": "错误"}.get(result["status"], result["status"])
            print(f"{result['name']:<{name_width}} {result['url']:<{url_width}} {status_msg:>8}")

    return None


def choose_pip_mirror():
    """
    从镜像列表中选择一个镜像
    参数:
        mirror_list: 可用镜像列表，每个元素包含 name, url, time 等信息
    返回:
        选中的镜像字典，如果用户选择不更改则返回 None
    """
    try:
        mirror_list = test_pip_mirrors()
        if not mirror_list:
            print("\n⚠️  没有找到可用的镜像，请检查网络连接")
            return 3, None

        while True:  # 无限循环直到用户输入正确
            try:
                # 获取用户输入并去除首尾空格
                choice = input(
                    f"\n请选择要使用的镜像，输入 0 表示不更改 (0-{len(mirror_list)}): ".format(len(mirror_list))
                ).strip()

                # 处理输入为 0 的情况（不更改配置）
                if choice == "0":
                    print("\n已取消配置，保持当前设置")
                    return 1, None

                # 将输入转换为整数
                choice_num = int(choice)

                # 检查输入是否在有效范围内
                if 1 <= choice_num <= len(mirror_list):
                    # 获取用户选择的镜像（注意索引从0开始，所以要减1）
                    selected_mirror = mirror_list[choice_num - 1]
                    return 0, selected_mirror["url"]
                else:
                    print(f"[ERROR] 输入错误！请输入 0-{len(mirror_list)} 之间的数字")

            except ValueError:
                print(f"[ERROR] 输入错误！请输入 0-{len(mirror_list)} 之间的数字")

    except KeyboardInterrupt:
        # 用户按 Ctrl+C 中断
        print("\n\n已取消操作")
        return 2, None


def main():
    """主函数"""

    # Test mirror speed and select a mirror
    status, url = choose_pip_mirror()
    if url:
        with open("/tmp/mypip_result.log", "w") as f:
            f.write(url)

    sys.exit(status)


if __name__ == "__main__":
    main()
