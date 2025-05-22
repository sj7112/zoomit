#!/usr/bin/env python3

import os
import shutil
import tempfile


# 全局变量
env_network = {}
env_infrastructure = {}
keys_network = []
keys_infrastructure = []


def init_env(env_file):
    """
    初始化环境变量，从 .env 文件读取并存储到字典中
    """
    if not os.path.isfile(env_file):
        raise FileNotFoundError(f"{env_file} not found!")

    section = None
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                # 检测标题行 (#=xxx)
                if line.startswith("#="):
                    section = line[2:].strip()
                continue

            # 拆分键值对
            if "=" in line:
                key, value = map(str.strip, line.split("=", 1))
                if section == "network":
                    env_network[key] = value
                    keys_network.append(key)
                elif section == "infrastructure":
                    env_infrastructure[key] = value
                    keys_infrastructure.append(key)


def show_env():
    """
    显示环境变量
    """
    print("#=network")
    for key in keys_network:
        print(f"{key}={env_network[key]}")

    print("#=infrastructure")
    for key in keys_infrastructure:
        print(f"{key}={env_infrastructure[key]}")


def set_env(section, key, value):
    """
    修改环境变量值
    """
    if section == "network":
        env_network[key] = value
        if key not in keys_network:
            keys_network.append(key)
    elif section == "infrastructure":
        env_infrastructure[key] = value
        if key not in keys_infrastructure:
            keys_infrastructure.append(key)


def save_env(env_file, env_dict, backup=True):
    """
    保存环境变量到文件
    """
    if backup:
        shutil.copy(env_file, f"{env_file}.bak")

    temp_file = tempfile.NamedTemporaryFile(delete=False, mode="w")
    try:
        with open(env_file, "r") as f, temp_file:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line or stripped_line.startswith("#"):
                    temp_file.write(line)
                    continue

                # 拆分键值对
                key, _, value = stripped_line.partition("=")
                key = key.strip()
                if key in env_dict:
                    temp_file.write(f"{key}={env_dict[key]}\n")
                else:
                    temp_file.write(line)

        # 替换原文件
        shutil.move(temp_file.name, env_file)
    except Exception as e:
        os.unlink(temp_file.name)
        raise e


def main():
    """
    主程序，用于测试
    """
    # 配置路径
    BIN_DIR = os.path.dirname(os.path.abspath(__file__))
    CONF_DIR = os.path.join(os.path.dirname(BIN_DIR), "config")
    DOCKER_DIR = os.path.join(CONF_DIR, "docker")
    ENV_SYSTEM = os.path.join(CONF_DIR, ".env")
    ENV_DOCKER = os.path.join(DOCKER_DIR, ".env")

    # 初始化环境变量
    init_env(ENV_SYSTEM)
    init_env(ENV_DOCKER)

    # 修改示例
    old_base_ip = env_network.get("BASE_IP", "")
    set_env("network", "BASE_IP", "192.168.1.100")
    old_password = env_infrastructure.get("MYSQL_ROOT_PASSWORD", "")
    set_env("infrastructure", "MYSQL_ROOT_PASSWORD", "newpassword")

    # 保存到文件
    save_env(ENV_SYSTEM, env_network)
    save_env(ENV_DOCKER, env_infrastructure)

    # 改回原始值
    env_network["BASE_IP"] = old_base_ip
    env_infrastructure["MYSQL_ROOT_PASSWORD"] = old_password
    save_env(ENV_SYSTEM, env_network, backup=False)
    save_env(ENV_DOCKER, env_infrastructure, backup=False)

    # 显示环境变量
    show_env()


if __name__ == "__main__":
    main()
