#!/usr/bin/env python3

"""
global package management speed tester, automatically selects the fastest linux mirror
"""

from pathlib import Path
import sys


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.linux_speed_deb import DebianMirrorTester
from python.linux_speed_ubt import UbuntuMirrorTester
from python.linux_speed_cos import CentosMirrorTester
from python.linux_speed_suse import OpenSUSEMirrorTester
from python.linux_speed_arch import ArchMirrorTester


def update_source(distro_ostype: str) -> None:
    """主函数"""
    if distro_ostype == "debian":
        DebianMirrorTester().run()

    elif distro_ostype == "ubuntu":
        UbuntuMirrorTester().run()

    elif distro_ostype == "centos":
        CentosMirrorTester().run()

    elif distro_ostype == "opensuse":
        OpenSUSEMirrorTester().run()

    elif distro_ostype == "arch":
        ArchMirrorTester().run()
