#!/usr/bin/env python3

import json
import os
import sys


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from linux_speed_arch import ArchMirrorTester
from linux_speed_cos import CentosMirrorTester
from linux_speed_deb import DebianMirrorTester
from linux_speed_suse import OpenSUSEMirrorTester
from linux_speed_ubt import UbuntuMirrorTester
from network_util import NetworkSetup
from lang_cache import LangCache


def main():
    """服务器管理工具库 - 提供多种配置和管理功能(对接shell脚本)"""
    # print("LANG:", os.environ.get("LANG"))
    # print("LANGUAGE:", os.environ.get("LANGUAGE"))

    command = sys.argv[1]
    match command:
        case "sh_update_source":
            # 选择包管理器，并执行初始化
            distro_ostype = sys.argv[2]
            match distro_ostype:
                case "debian":
                    DebianMirrorTester().run()
                case "ubuntu":
                    UbuntuMirrorTester().run()
                case "centos":
                    CentosMirrorTester().run()
                case "opensuse":
                    OpenSUSEMirrorTester().run()
                case "arch":
                    ArchMirrorTester().run()
                case _:
                    sys.exit(f"Error: Unknown distro '{distro_ostype}'")

        # 检查服务器是否使用静态IP并提供交互式选项
        case "sh_fix_ip":
            exit_code = NetworkSetup().fix_ip()
            sys.exit(exit_code)

        # clear cache (diskcache for language messages)
        case "sh_clear_cache":
            LangCache.get_instance().clear_cache()

        case _:
            sys.exit(f"Error: Unknown command '{command}'")


if __name__ == "__main__":
    main()
