#!/usr/bin/env python3

import os
from pathlib import Path
import sys


sys.path.append(str(Path(__file__).resolve().parent))  # add root sys.path

from python.linux_speed_arch import ArchMirrorTester
from python.linux_speed_cos import CentosMirrorTester
from python.linux_speed_deb import DebianMirrorTester
from python.linux_speed_suse import OpenSUSEMirrorTester
from python.linux_speed_ubt import UbuntuMirrorTester
from python.network_util import NetworkSetup
from python.cache.lang_cache import LangCache


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
