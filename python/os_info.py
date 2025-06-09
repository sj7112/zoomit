#!/usr/bin/env python3
"""
简化的OS信息初始化程序
"""

import re
from dataclasses import dataclass


@dataclass
class OSInfo:
    """操作系统信息数据类"""

    ostype: str = ""  # 发行版ID (如: ubuntu, debian, fedora)
    codename: str = ""  # 版本代号 (如: bookworm, bullseye, jammy)
    pretty_name: str = ""  # 完整名称 (如: Ubuntu 22.04.3 LTS)
    version_id: str = ""  # 版本号 (如: 11, 12, 22.04)
    package_mgr: str = ""  # 包管理器 (如: apt, yum, dnf, zypper, pacman)


def init_os_info(os_release_path: str = "/etc/os-release") -> OSInfo:
    """
    初始化OS信息

    Args:
        os_release_path: os-release文件路径

    Returns:
        OSInfo: 包含系统信息的数据对象
    """
    raw_data = {}

    # 解析os-release文件
    try:
        with open(os_release_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                match = re.match(r"^([A-Z_]+)=(.*)$", line)
                if match:
                    key, value = match.groups()
                    # 去除引号
                    if len(value) >= 2 and (
                        (value.startswith('"') and value.endswith('"'))
                        or (value.startswith("'") and value.endswith("'"))
                    ):
                        value = value[1:-1]
                    raw_data[key] = value
    except:
        pass  # 文件不存在或读取失败时使用空数据

    # 提取基本信息
    ostype = raw_data.get("ID", "unknown").lower()
    pretty_name = raw_data.get("PRETTY_NAME", "")
    version_id = raw_data.get("VERSION_ID", "")

    # 提取版本代号
    codename = raw_data.get("VERSION_CODENAME", "")
    if not codename:
        # 从VERSION字段提取括号中的代号
        version = raw_data.get("VERSION", "")
        if version:
            match = re.search(r"\(([^)]+)\)", version)
            if match:
                codename = match.group(1)

        # 从PRETTY_NAME提取常见代号
        if not codename and pretty_name:
            patterns = [
                r"\b(bookworm|bullseye|buster|stretch|jessie)\b",  # Debian
                r"\b(jammy|focal|bionic|xenial|trusty|noble)\b",  # Ubuntu
                r"\b(leap|tumbleweed)\b",  # openSUSE
            ]
            for pattern in patterns:
                match = re.search(pattern, pretty_name.lower())
                if match:
                    codename = match.group(1)
                    break

    # 标准化版本号
    if version_id:
        parts = version_id.split(".")
        if len(parts) >= 2:
            # Ubuntu格式 (22.04) 或 openSUSE Leap格式 (15.5)
            if (len(parts[0]) == 2 and len(parts[1]) == 2) or (parts[0] in ["15", "16"] and len(parts[1]) == 1):
                version_id = f"{parts[0]}.{parts[1]}"
            else:
                # Debian格式 (11)
                version_id = parts[0]

    # 确定包管理器
    package_mgr = "unknown"
    if ostype in ["debian", "ubuntu"]:
        package_mgr = "apt"
    elif ostype in ["fedora", "rhel", "centos", "rocky", "almalinux"]:
        package_mgr = "dnf" if ostype == "fedora" else "yum"
    elif ostype in ["opensuse", "opensuse-leap", "opensuse-tumbleweed", "sles"]:
        package_mgr = "zypper"
    elif ostype in ["arch", "manjaro", "endeavouros"]:
        package_mgr = "pacman"
    elif "debian" in raw_data.get("ID_LIKE", ""):
        package_mgr = "apt"

    return OSInfo(
        ostype=ostype, codename=codename, pretty_name=pretty_name, version_id=version_id, package_mgr=package_mgr
    )


def main():
    """演示用法"""
    os_info = init_os_info()

    print("=== OS信息 ===")
    print(f"发行版类型: {os_info.ostype}")
    print(f"版本代号: {os_info.codename}")
    print(f"完整名称: {os_info.pretty_name}")
    print(f"版本号: {os_info.version_id}")
    print(f"包管理器: {os_info.package_mgr}")

    print(f"\n简化显示: {os_info.ostype} {os_info.version_id} ({os_info.codename}) - {os_info.package_mgr}")


if __name__ == "__main__":
    main()
