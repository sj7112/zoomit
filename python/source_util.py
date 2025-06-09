#!/usr/bin/env python3

"""
global package management speed tester, automatically selects the fastest linux mirror
"""

import os
import sys


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from linux_speed_deb import update_source_deb
from linux_speed_ubt import update_source_ubt
from linux_speed_cos import update_source_cos
from linux_speed_arch import update_source_arch
from linux_speed_suse import update_source_suse


def update_source(distro_ostype: str, system_country: str) -> None:
    """主函数"""

    if distro_ostype == "debian":
        update_source_deb(system_country)

    elif distro_ostype == "ubuntu":
        update_source_ubt(system_country)

    elif distro_ostype == "centos":
        update_source_cos(system_country)

    elif distro_ostype == "arch":
        update_source_arch(system_country)

    elif distro_ostype == "opensuse":
        update_source_suse(system_country)


if __name__ == "__main__":
    update_source()
