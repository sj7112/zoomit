#!/usr/bin/env python3

import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Dict, List, Tuple


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.cmd_handler import cmd_ex_str
from python.file_util import read_file, write_source_file
from python.msg_handler import MSG_ERROR, MSG_SUCCESS, _mf, error, string
from python.cache.os_info import OSInfo, OSInfoCache
from python.system import confirm_action
from python.debug_tool import print_array


def run_command(cmd, shell=True, capture_output=True, text=True):
    """执行系统命令并返回结果"""
    try:
        result = subprocess.run(cmd, shell=shell, capture_output=capture_output, text=text)
        return result
    except Exception as e:
        string(r"Failed to execute command: {}", e)
        return None


class SshSetup:
    """
    OpenSSH Setup class
    """

    lines: List[str]
    modified: False

    def modify_config_line(self, key, new_line):
        """Find and modify the matching line"""
        self.modified = True

        lines = self.lines
        modify = False
        for i, line in enumerate(lines):
            if re.match(rf"^\s*#?\s*({key})\s+(\S+)", line):
                if not modify:  # modify the first match
                    lines[i] = new_line
                    modify = True
                else:  # delete other matches
                    del lines[i]
                    i -= 1

        # If no matching line is found, add a new line
        if not modify:
            lines.append(new_line)

    def is_service_active(self, service_name):
        """检查服务是否激活"""
        return cmd_ex_str(f"systemctl is-active {service_name}")

    def get_config_port(self):
        """Read the uncommented SSH port number"""
        for line in self.lines:
            if line.strip().startswith("#"):
                continue
            match = re.match(r"^\s*Port\s+(\d+)", line)
            if match:
                return match.group(1)
        return 22

    def get_config_root_permit(self):
        """Read the uncommented root permission"""
        for line in self.lines:
            if line.strip().startswith("#"):
                continue
            match = re.match(r"^\s*PermitRootLogin\s+(\S+)", line)
            if match:
                return match.group(1)
        return None

    def config_sshd(self):
        """
        配置SSH服务
        功能: 检查sshd，交互式修改 SSH 端口和 root 登录权限
        """
        _os_info: OSInfo = OSInfoCache.get_instance().get()
        sshd_config = "/etc/ssh/sshd_config"

        # get configuration data
        if not os.path.exists(sshd_config):
            error(r"SSH configuration file {} does not exist", sshd_config)
            return 3

        # read file
        self.lines = read_file(sshd_config)

        # get current port and root permission
        curr_ssh_port = self.get_config_port()
        curr_root_permit = self.get_config_root_permit().lower() == "yes"

        # check SSH service status
        ssh_service = "ssh" if _os_info.ostype == "ubuntu" else "sshd"  # get service name
        if self.is_service_active(ssh_service):
            prompt = _mf(r"SSH is running (current port: {}). Do you want to reconfigure it?", curr_ssh_port)
            ret_code = confirm_action(prompt, default=False)
            if ret_code != 0:
                return 1

        # Prompt for SSH port
        while True:
            try:
                ssh_port = input(_mf(r"Enter new SSH port (current: {}): ", curr_ssh_port)).strip()
                if not ssh_port:
                    string(r"Keep current port: {}", curr_ssh_port)
                    break

                if ssh_port.isdigit() and 1 <= int(ssh_port) <= 65535:
                    self.modify_config_line("Port", f"Port {ssh_port}")
                    string(r"[{}] SSH port set to: {}", MSG_SUCCESS, ssh_port)
                    break

                string(r"[{}] Failed to set SSH port", MSG_ERROR)
            except KeyboardInterrupt:
                string("\nOperation cancelled")
                return 2

        # 询问是否允许root登录
        allow_root = confirm_action(_mf("Allow root login via SSH?:"), default=curr_root_permit)
        if allow_root == 0:
            if not curr_root_permit:
                self.modify_config_line("PermitRootLogin", "PermitRootLogin yes")
            string("[{}] Root login allowed", MSG_SUCCESS)
        elif allow_root == 1:
            if curr_root_permit:
                self.modify_config_line("PermitRootLogin", "PermitRootLogin no")
            string("[{}] Root login disabled", MSG_SUCCESS)
        else:
            return 2

        # write file
        if self.modified:
            write_source_file(sshd_config, self.lines)
        return 0


if __name__ == "__main__":
    try:
        OSInfoCache.get_instance().clear_cache()
        SshSetup().config_sshd()
    except KeyboardInterrupt:
        print("\n操作已取消")
        sys.exit(1)
    except Exception as e:
        print(f"程序执行出错: {e}")
        sys.exit(1)
