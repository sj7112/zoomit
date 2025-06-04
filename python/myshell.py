#!/usr/bin/env python3

import json
import os
import sys


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from network_util import check_ip
from network_speed import install_pip
from source_util import update_source


def main():
    """服务器管理工具库 - 提供多种配置和管理功能(对接shell脚本)"""
    command = sys.argv[1]

    # 检查服务器是否使用静态IP并提供交互式选项
    if command == "sh_check_ip":
        sudo_cmd = sys.argv[2]
        print(json.dumps(check_ip(sudo_cmd)))

    # 选择python镜像
    elif command == "sh_install_pip":
        install_pip()

    # 选择包管理器
    elif command == "sh_update_source":
        distro_ostype = sys.argv[2]
        system_country = sys.argv[3]
        update_source(distro_ostype, system_country)

    else:
        print(f"Error: Unknown command '{command}'")
        sys.exit(1)


if __name__ == "__main__":
    main()
