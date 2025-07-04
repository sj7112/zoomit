#!/usr/bin/env python3

import os
from pathlib import Path
import sys


sys.path.append(str(Path(__file__).resolve().parent))  # add root sys.path

from python.config_sshd import SshSetup
from python.mirror.linux_speed_arch import ArchMirrorTester
from python.mirror.linux_speed_cos import CentosMirrorTester
from python.mirror.linux_speed_deb import DebianMirrorTester
from python.mirror.linux_speed_suse import OpenSUSEMirrorTester
from python.mirror.linux_speed_ubt import UbuntuMirrorTester
from python.network_util import NetworkSetup
from python.cache.lang_cache import LangCache


def main():
    """Provides various python functions (integrated with shell scripts)"""
    # print("LANG:", os.environ.get("LANG"))
    # print("LANGUAGE:", os.environ.get("LANGUAGE"))

    command = sys.argv[1]
    match command:
        case "sh_update_source":
            # Select mirror for package manager and perform initialization
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

        # Check if the server is using a static IP (user interactive)
        case "sh_configure_sshd":
            exit_code = SshSetup().configure_sshd()
            sys.exit(exit_code)

        # Check if the server is using a static IP (user interactive)
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
