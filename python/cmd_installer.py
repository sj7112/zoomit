#!/usr/bin/env python3

import subprocess
import sys
import shutil
import platform


from datetime import datetime
from typing import List, Optional, Tuple

from os_info import get_os_info
from cmd_handler import cmd_exec, cmd_ex_str, cmd_ex_pat


# Global configuration
LOG_FILE = "/var/log/sj_install.log"


class LinuxInstaller:
    """Linux通用程序安装器"""

    def __init__(self, log_file: str = LOG_FILE):
        self.log_file = log_file
        self.os_info = get_os_info()

    def _get_install_command(self, package: str) -> List[str]:
        """根据包管理器获取安装命令"""
        commands = {
            "pacman": ["pacman", "-Sy", "--noconfirm", package],  # Arch Linux, Manjaro
            "apt": ["apt-get", "install", "-y", package],  # Debian, Ubuntu
            "yum": ["yum", "install", "-y", package],  # CentOS, RHEL (旧版本)
            "dnf": ["dnf", "install", "-y", package],  # Fedora, CentOS 8+, RHEL 8+
            "zypper": ["zypper", "install", "-y", package],  # openSUSE
            "apk": ["apk", "add", package],  # Alpine Linux
            "emerge": ["emerge", package],  # Gentoo
        }

        if self.os_info.package_mgr in commands:
            return commands[self.os_info.package_mgr]
        else:
            # 通用命令，适用于大多数包管理器
            return [self.os_info.package_mgr, "install", "-y", package]

    def _update_package_cache(self):
        """更新包缓存"""
        update_commands = {
            "apt": ["apt-get", "update"],
            "pacman": ["pacman", "-Sy"],
            "apk": ["apk", "update"],
        }

        if self.os_info.package_mgr in update_commands:
            self.info("更新包缓存...")
            success, output = cmd_exec(update_commands[self.os_info.package_mgr])
            if not success:
                self.error(f"更新包缓存失败: {output}")

    def install_base_pkg(self, lnx_cmd: str, package_name: Optional[str] = None) -> bool:
        """
        安装基础包

        Args:
            lnx_cmd: 要检查的命令名
            package_name: 包名（如果与命令名不同）

        Returns:
            bool: 安装是否成功
        """
        # 检查命令是否存在
        if shutil.which(lnx_cmd):
            self.info(f"'{lnx_cmd}' 已安装")
            return True

        # 如果没有指定包名，则使用命令名
        if package_name is None:
            package_name = lnx_cmd

        self.info(f"自动安装 '{lnx_cmd}' (包名: {package_name})...")

        # 检查包管理器是否可用
        if self.os_info.package_mgr == "unknown":
            self.exiterr("无法检测到支持的包管理器")

        # 更新包缓存（某些发行版需要）
        self._update_package_cache()

        # 获取安装命令
        cmd = self._get_install_command(package_name)

        # 执行安装命令
        success, output = cmd_exec(cmd)

        # 记录时间
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 再次检查是否安装成功
        if not success or not shutil.which(lnx_cmd):
            error_msg = f"{lnx_cmd} 安装失败，请手动安装，日志: {self.log_file} [{current_time}]"
            self.exiterr(error_msg)
            return False
        else:
            success_msg = f"{lnx_cmd} 安装成功，日志: {self.log_file} [{current_time}]"
            self.success(success_msg)
            return True

    def install_multiple_packages(self, packages: List[str]) -> bool:
        """
        批量安装多个包

        Args:
            packages: 包列表，可以是字符串或元组(命令名, 包名)

        Returns:
            bool: 所有包是否都安装成功
        """
        all_success = True

        for pkg in packages:
            if isinstance(pkg, tuple):
                cmd_name, pkg_name = pkg
                success = self.install_base_pkg(cmd_name, pkg_name)
            else:
                success = self.install_base_pkg(pkg)

            if not success:
                all_success = False

        return all_success

    def get_system_info(self) -> dict:
        """获取系统信息"""
        info = {
            "platform": platform.system(),
            "architecture": platform.machine(),
            "distribution": "Unknown",
            "package_manager": self.os_info.package_mgr,
        }

        try:
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("PRETTY_NAME="):
                        info["distribution"] = line.split("=", 1)[1].strip().strip('"')
                        break
        except FileNotFoundError:
            pass

        return info


def main():
    """示例用法"""
    installer = LinuxInstaller()

    # 显示系统信息
    sys_info = installer.get_system_info()
    installer.info(f"系统信息: {sys_info['distribution']} ({sys_info['architecture']})")
    installer.info(f"包管理器: {sys_info['package_manager']}")

    # 单个包安装示例
    installer.install_base_pkg("curl")
    installer.install_base_pkg("wget")

    # 命令名与包名不同的情况
    installer.install_base_pkg("pip3", "python3-pip")  # Ubuntu/Debian

    # 批量安装示例
    packages = [
        "git",
        "vim",
        "htop",
        ("python3", "python3"),
        ("pip3", "python3-pip"),
    ]

    installer.info("开始批量安装包...")
    success = installer.install_multiple_packages(packages)

    if success:
        installer.success("所有包安装完成！")
    else:
        installer.error("部分包安装失败，请查看日志")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n安装被用户取消")
        sys.exit(1)
    except Exception as e:
        print(f"程序异常: {e}")
        sys.exit(1)
