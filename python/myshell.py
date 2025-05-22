#!/usr/bin/env python3

import json
import os
import sys
import typer


# 动态添加当前目录到 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from network_util import check_ip

# 创建 Typer 应用
app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False, pretty_exceptions_enable=False)


@app.callback()
def callback():
    """
    服务器管理工具库 - 提供多种配置和管理功能(对接shell脚本)

    使用 --help 查看可用命令
    """
    pass  # 回调函数，为整个应用提供帮助文本


@app.command("sh_check_ip")  # 明确指定命令名称，包括下划线
def sh_check_ip_command(
    sudo_cmd: str = typer.Argument(..., help="sudo 命令前缀（sudo 或空字符串）"),
):
    """
    检查服务器是否使用静态IP并提供交互式选项
    """
    print(json.dumps(check_ip(sudo_cmd)))  # 输出 JSON 格式的结果


if __name__ == "__main__":
    app()
