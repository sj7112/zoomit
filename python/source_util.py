#!/usr/bin/env python3

"""
global package management speed tester, automatically selects the fastest linux mirror
"""

import os
import sys


# default python sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from linux_speed_deb import DebianMirrorTester
from linux_speed_ubt import UbuntuMirrorTester
from linux_speed_cos import CentosMirrorTester
from linux_speed_suse import OpenSUSEMirrorTester
from linux_speed_arch import update_source_arch


def update_source(distro_ostype: str, system_country: str) -> None:
    """主函数"""
    if distro_ostype == "debian":
        DebianMirrorTester(system_country).run()

    elif distro_ostype == "ubuntu":
        UbuntuMirrorTester(system_country).run()

    elif distro_ostype == "centos":
        CentosMirrorTester(system_country).run()

    elif distro_ostype == "opensuse":
        OpenSUSEMirrorTester(system_country).run()

    elif distro_ostype == "arch":
        update_source_arch(system_country)
