#!/usr/bin/env python3

import glob
from pathlib import Path
import subprocess
import re
import os
import sys

# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from file_util import read_env_file

# 设置默认路径
PARENT_DIR = Path(__file__).parent.parent.resolve()
CONF_DIR = (PARENT_DIR / "config").resolve()

FILE_PATH_INFRA = "/opt/docker/infra"
FILE_PATH_APP = "/opt/docker/apps"


def is_cloud_manufacturer(manufacturer):
    # 常见云厂商关键词列表（可扩展）
    cloud_keywords = [
        "Amazon",
        "Google",
        "Microsoft Azure",
        "Alibaba Cloud",
        "Tencent Cloud",
        "Huawei",
        "Oracle Cloud",
        "IBM Cloud",
        "DigitalOcean",
        "Linode",
    ]
    if manufacturer:
        for keyword in cloud_keywords:
            if keyword.lower() in manufacturer.lower():
                return manufacturer
    return None


if __name__ == "__main__":
    # 测试入口
    print(f"返回状态码: {status}")
    print(f"返回的网络配置: {env_network}")
