import platform
import sys
import os
import re
import requests

from python.cache.os_info import OSInfoCache
from python.cmd_handler import cmd_ex_pat, cmd_ex_str
from python.msg_handler import _mf, info, string, warning
from python.read_util import confirm_action
from python.system import generate_temp_file, write_temp_file


MIN_VERSION = "20.10.0"  # need to support docker compose version 3.9

env = os.environ.copy()
env["LANG"] = "C"


urls_map = {
    "global": "https://download.docker.com/linux",
    "aliyun": "https://mirrors.aliyun.com/docker-ce/linux/{ostype}",
}

paths_map = {
    "debian": "dists/{codename}/pool/stable/{arch}/",
    "ubuntu": "dists/{codename}/pool/stable/{arch}/",
    "centos": "{version}/{arch}/stable/Packages/",
    "rhel": "{version}/{arch}/stable/Packages/",
    "opensuse": None,  # openSUSE Linux usually uses zypper repo, no official path
    "arch": None,  # Arch Linux usually uses pacman repo, no official path
}


class DockerSetup:
    def __init__(self, min_ver=MIN_VERSION):
        self.min_ver = min_ver
        self.conf_file = os.environ.get("DOCKER_SETUP_FILE") or generate_temp_file()  # generate file only for test
        self.lines = {}
        self.os_info = OSInfoCache.get_instance().get()

    def get_official_version_url(self, location):
        """Choose the path rule"""
        ostype = self.os_info.ostype
        pm = self.os_info.package_mgr
        codename = self.os_info.codename
        arch = platform.machine().lower()
        if arch == "i386":
            print("Docker cannot run on i386 platform!", file=sys.stderr)
            sys.exit(1)
        if pm == "apt":
            if arch == "x86_64":
                arch = "amd64"
            elif arch == "aarch64":
                arch = "arm64"
        elif pm == "yum" or pm == "dnf":
            if arch == "amd64":
                arch = "x86_64"
            elif arch == "arm64":
                arch = "aarch64"
        elif arch in ["arm64", "aarch64"]:
            arch = "arm64"

        path_template = paths_map.get(ostype)

        if not path_template:
            return None, None

        # For distros without codename, you may need to define `version` instead
        url_path = path_template.format(
            ostype=ostype, codename=codename, version=codename, arch=arch  # Reuse codename as version if needed
        )

        base_url = urls_map.get(location).format(ostype=ostype)
        return base_url, f"{base_url}/{url_path}"

    def get_docker_version(self):
        try:
            result = cmd_ex_str("docker version --format {{.Server.Version}}", noex=True)
            match = re.search(r"\d+\.\d+\.\d+", result)
            if match:
                return match.group(0)
        except Exception:
            pass
        return None

    def get_available_version(self):
        env = {"LANG": "C", "PATH": os.environ.get("PATH", "/usr/bin:/bin")}
        if self.os_info.package_mgr == "apt":
            for pkg in ["docker-ce", "docker.io"]:  # apt-cache policy docker-ce | docker.io
                output = cmd_ex_pat(["apt-cache", "policy", pkg], r"Candidate:\s*(\d+\.\d+\.\d+)", env=env, noex=True)
                if output:
                    return output

        elif self.os_info.package_mgr == "dnf":
            return cmd_ex_pat(["dnf", "info", "docker-ce"], r"(?m)^Version\s*:\s*(\d+\.\d+\.\d+)", env=env, noex=True)

        elif self.os_info.package_mgr == "yum":
            return cmd_ex_pat(["yum", "info", "docker-ce"], r"(?m)^Version\s*:\s*(\d+\.\d+\.\d+)", env=env, noex=True)

        elif self.os_info.package_mgr == "pacman":
            return cmd_ex_pat(["pacman", "-Si", "docker"], r"(?m)^Version\s*:\s*(\d+\.\d+\.\d+)", env=env, noex=True)

        elif self.os_info.package_mgr == "zypper":
            return cmd_ex_pat(["zypper", "info", "docker"], r"(?m)^Version\s*:\s*(\d+\.\d+\.\d+)", env=env, noex=True)

        return None

    def get_official_version(self, location):
        """
        Return latest available Docker CE version and the corresponding apt repo URL
        """
        base_url, full_url = self.get_official_version_url(location)
        if full_url:
            try:
                response = requests.get(full_url, timeout=10)
                if response.status_code == 200:
                    matches = re.findall(r"docker-ce_(\d+\.\d+\.\d+)[\w~+:. -]*\.(?:deb|rpm)", response.text)
                    latest_version = sorted(matches, key=lambda v: list(map(int, v.split("."))), reverse=True)[0]
                    return latest_version, base_url
            except Exception:
                pass
            string(r"Error fetching official version from {}", full_url)
            print()
        return None, None

    def compare_versions(self, v1, v2):
        def normalize(v):
            return [int(x) for x in v.split(".") if x.isdigit()]

        return normalize(v1) >= normalize(v2)

    def install_check(self) -> bool:
        min_ver = self.min_ver
        rc = 0

        ver = self.get_docker_version()
        if ver:
            prompt = _mf("Do you want to re-install Docker?")
            if self.compare_versions(ver, min_ver):
                string(r"Docker version {} is installed and running", ver)
                rc = confirm_action(prompt, no_value=False)
                if rc == 0:
                    print()  # print blank line
            else:
                warning(r"Docker requires version {}+, now it's {}", ver)
                rc = confirm_action(prompt, no_value=True)
                if rc == 1:
                    sys.exit(1)  # stop running
        return rc == 0

    def install_choose(self) -> bool:
        min_ver = self.min_ver
        v1_inst_str = _mf(r"Install system-provided Docker")
        v2_inst_str = _mf(r"Install official-provided Docker")
        lines = self.lines

        pm = self.os_info.package_mgr
        v1 = self.get_available_version()
        if v1:
            if self.compare_versions(v1, min_ver):
                lines["available"] = {"version": v1}
            else:
                info(r"Requires Docker version {}+, {} only supports {}", min_ver, pm, v1)

        version = _mf("Version")
        v2, url = self.get_official_version("global")
        if v2:
            if self.compare_versions(v2, min_ver):
                lines["official"] = {"version": v2, "url": url}

        v2, url = self.get_official_version("aliyun")
        if v2:
            if self.compare_versions(v2, min_ver):
                lines["official_cn"] = {"version": v2, "url": url}

        if not lines:
            sys.exit(1)  # stop running

        line_size = len(lines)
        if line_size > 1:
            index = 1
            for key, value in lines.items():
                key_desc = ""
                match key:
                    case "available":
                        key_desc = v1_inst_str
                    case "official":
                        key_desc = v2_inst_str
                    case "official_cn":
                        key_desc = v2_inst_str + f" (aliyun)"
                print(f" {index})  {version}={value['version']:<11}{key_desc}")
                index += 1
            print()  # print blank line

            prompt = _mf(r"Please select a version to install (1-{}). Enter 0 to skip:", line_size)
            rc, result = confirm_action(prompt, option="number", no_value=0, to_value=line_size)
            if result == 0:
                warning("Skip Docker installation")
                return False  # keep current setup
            else:
                line = list(lines.values())[result - 1]
                write_temp_file(self.conf_file, line)  # add version and base_url in temp file
        else:
            line = list(lines.items())[0]
            key, value = line
            match key:
                case "available":
                    key_desc = v1_inst_str
                case "official":
                    key_desc = v2_inst_str
                case "official_cn":
                    key_desc = v2_inst_str + f" (aliyun)"
            prompt = f"{version}={value['version']:<10}{key_desc}:"
            rc = confirm_action(prompt, no_value=True, no_msg=f"{_mf('Skip Docker installation')}")
            if rc == 1:
                return False  # keep current setup
            else:
                write_temp_file(self.conf_file, value)  # store version and base_url in temp file

        return True

    def check_docker(self):
        if self.install_check() and self.install_choose():
            return 0  # install/re-install docker
        else:
            return 1  # keep current setup


# Example usage:
if __name__ == "__main__":
    docker = DockerSetup()
    docker.check_docker()
    print(f"Docker version saved in: {docker.conf_file}")
