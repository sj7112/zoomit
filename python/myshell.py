#!/usr/bin/env python3

import json
import os
import sys


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from network_util import check_ip
from source_util import update_source


def main():
    """服务器管理工具库 - 提供多种配置和管理功能(对接shell脚本)"""
    # print("LANG:", os.environ.get("LANG"))
    # print("LANGUAGE:", os.environ.get("LANGUAGE"))

    command = sys.argv[1]

    # 选择包管理器，并执行初始化
    if command == "sh_update_source":
        distro_ostype = sys.argv[2]
        update_source(distro_ostype)

    # 检查服务器是否使用静态IP并提供交互式选项
    elif command == "sh_check_ip":
        print(json.dumps(check_ip()))

    else:
        print(f"Error: Unknown command '{command}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
