#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_PYTHON_INSTALL:-}" ]]; then
  LOADED_PYTHON_INSTALL=1

  # 声明全局变量
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  source "$LIB_DIR/msg_handler.sh"
  source "$LIB_DIR/bash_utils.sh"
  source "$LIB_DIR/python_bridge.sh"

  PY_BASE_URL="https://github.com/astral-sh/python-build-standalone/releases/download"
  PY_VERSION="3.10.17"
  PY_REL_DATE="20250517" # 使用稳定的发布版本

  PY_INST_DIR="$HOME/.local/python-$PY_VERSION"
  PY_GZ_FILE="/tmp/cpython-${PY_VERSION}-standalone.tar.gz"
  PY_BIN=""
  VENV_DIR="$HOME/.venv"

  # ==============================================================================
  # 安装python虚拟环境
  # ==============================================================================
  # 判断是否已有 Python 3.10+
  check_py_version() {
    local py_path=$1
    if [ -n "$py_path" ] && "$py_path" -c 'import sys; exit(0) if sys.version_info >= (3,10) else exit(1)' 2>/dev/null; then
      # 确保 venv 和 ensurepip 都存在
      if "$py_path" -m venv --help >/dev/null 2>&1 \
        && "$py_path" -m ensurepip --version >/dev/null 2>&1; then
        PY_BIN="$py_path"
        return 0
      fi
    fi
    return 1
  }

  # 检测系统架构和发行版
  detect_system() {
    local arch=$(uname -m) # 检测架构
    case "$arch" in
      x86_64) arch="x86_64" ;;
      aarch64 | arm64) arch="aarch64" ;;
      armv7l) arch="armv7" ;;
      *) exiterr "不支持的架构: $arch" ;;
    esac

    echo "$arch-linux" # 不考虑linux-musl
  }

  # 获取 Python standalone 下载 URL
  get_python_url() {
    local system_type="$1"

    # 根据系统类型选择合适的构建
    case "$system_type" in
      x86_64-linux)
        echo "$PY_BASE_URL/$PY_REL_DATE/cpython-$PY_VERSION+$PY_REL_DATE-x86_64-unknown-linux-gnu-install_only.tar.gz"
        ;;
      aarch64-linux)
        echo "$PY_BASE_URL/$PY_REL_DATE/cpython-$PY_VERSION+$PY_REL_DATE-aarch64-unknown-linux-gnu-install_only.tar.gz"
        ;;
      *)
        exiterr "不支持的系统类型: $system_type"
        ;;
    esac
  }

  # 智能 wget 函数
  smart_wget() {
    local output="$1"
    local url="$2"

    if wget --help 2>&1 | grep -q -- '--show-progress'; then
      echo "wget -c -q --show-progress -O $output $url"
      wget -c -q --show-progress -O "$output" "$url"
    else
      echo "wget -c -q -O $output $url"
      wget -c -q -O "$output" "$url"
    fi
  }

  # 下载并安装 Python standalone
  install_py_standalone() {
    local loc_bin="$1"
    local system_type=$(detect_system)
    local python_url=$(get_python_url "$system_type")

    # 下载文件（支持断点续传）
    info "下载 Python $PY_VERSION standalone..."
    smart_wget "$PY_GZ_FILE" "$python_url"

    # 解压到安装目录
    info "安装 Python 到 $PY_INST_DIR..."
    mkdir -p "$PY_INST_DIR" # 确保安装目录存在
    if ! tar -xf "$PY_GZ_FILE" -C "$PY_INST_DIR" --strip-components=1; then
      exiterr "解压安装失败"
    fi

    # 验证是否可用
    if ! check_py_version "$loc_bin"; then
      exiterr "Python 安装失败: $loc_bin 不存在或不可执行"
    else
      info "Python $PY_VERSION 安装完成！"
    fi
  }

  # 创建虚拟环境并安装常用包
  create_py_venv() {
    # 删除已存在的虚拟环境
    if [[ -d "$VENV_DIR" ]]; then
      if ! confirm_action "虚拟环境 $VENV_DIR 已存在，是否删除重建？"; then
        if confirm_action "是否重建 pip 和所需 python 库？"; then
          return 0 # 重建pip
        else
          warning "跳过虚拟环境创建"
          return 1
        fi
      else
        rm -rf "$VENV_DIR"
      fi
    else
      info "创建虚拟环境 $VENV_DIR..."
    fi

    # 创建虚拟环境
    if "$PY_BIN" -m venv "$VENV_DIR"; then
      success "虚拟环境创建成功！"
      return 0 # 创建pip
    else
      exiterr "创建虚拟环境失败"
      return 1
    fi
  }

  # 安装 Python 并创建虚拟环境
  install_py_venv() {
    # 检查是否需要重新安装 Python
    local def_bin="$(command -v python3 2>/dev/null || true)"
    local loc_bin="$PY_INST_DIR/bin/python3"
    if ! check_py_version "$def_bin" && ! check_py_version "$loc_bin"; then
      install_py_standalone "$loc_bin"
    fi

    # 创建虚拟环境并安装包
    if create_py_venv; then
      sh_install_pip # 安装 pip 和所需的基础包
    fi
  }

  # ==============================================================================
  # 主程序（用于测试）
  # ==============================================================================
  if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then

    if [[ "$DEBUG" == "1" ]]; then
      # set -x          # 启用命令追踪
      set -e          # 启用脚本错误即退出
      set -u          # 启用未定义变量报错
      set -o pipefail # 启用管道失败时退出
    else
      set +x          # 关闭命令追踪
      set -e          # 确保遇到错误退出
      set -u          # 确保未定义变量时报错
      set -o pipefail # 确保管道中的命令失败会导致脚本退出
    fi

    # 主函数
    main() {
      info "Python $PY_VERSION Standalone 自动安装脚本"
      install_py_venv
    }

    # 执行主函数
    main "$@"
  fi

fi
