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
  PY_TAR_URL="https://www.python.org/ftp/python/${PY_VERSION}/Python-${PY_VERSION}.tgz"
  PY_TAR_FILE="/tmp/Python-${PY_VERSION}.tgz"
  PY_GZ_FILE="/tmp/cpython-${PY_VERSION}-standalone.tar.gz"
  PY_BIN=""
  VENV_DIR="$HOME/.venv"

  # 检查 glibc 版本 >= 2.17
  check_glibc() {
    local GLIBC_OK=0
    if command -v ldd >/dev/null; then
      GLIBC_VER=$(ldd --version 2>/dev/null | head -n1 | grep -oE '[0-9]+\.[0-9]+')
      GLIBC_MAJOR=${GLIBC_VER%%.*}
      GLIBC_MINOR=${GLIBC_VER##*.}
      if [ "$GLIBC_MAJOR" -gt 2 ] || { [ "$GLIBC_MAJOR" -eq 2 ] && [ "$GLIBC_MINOR" -ge 17 ]; }; then
        GLIBC_OK=1
      fi
    fi
    echo "$GLIBC_OK"
  }

  # 源码编译安装python 3.10
  install_py() {
    # 下载源码
    echo "wget -c -q --show-progress -O $PY_TAR_FILE $PY_TAR_URL"
    wget -c -q --show-progress -O "$PY_TAR_FILE" "$PY_TAR_URL"
    tar -xf "$PY_TAR_FILE" -C /tmp
    cd "/tmp/Python-${PY_VERSION}"

    # 编译安装
    ./configure --prefix="$PY_INST_DIR" --enable-optimizations
    make -j$(nproc)
    make install

    # 成功后输出路径
    PY_BIN="$PY_INST_DIR/bin/python3.10"
  }

  check_py_version() {
    # 判断是否已有 Python 3.10+
    local py_path=$(command -v python3 2>/dev/null || true)
    if [ -n "$py_path" ] && "$py_path" -c 'import sys; exit(0) if sys.version_info >= (3,10) else exit(1)'; then
      # 确保 venv 和 ensurepip 都存在
      if "$py_path" -m venv --help >/dev/null 2>&1 \
        && "$py_path" -m ensurepip --version >/dev/null 2>&1; then
        PY_BIN="$py_path"
        return 0
      fi
    fi

    # 检查编译工具
    if [ "$(check_glibc)" -eq 0 ]; then
      exiterr "系统 glibc 版本过低，不能安装 Python 3.10"
    fi

    # 询问是否安装
    local prompt
    if [ -n "$py_path" ]; then
      prompt=$(string "无法创建虚拟环境，是否安装 Python ${PY_VERSION} 到 ~/.local？")
    else
      prompt=$(string "Python 版本过低，是否安装 Python ${PY_VERSION} 到 ~/.local？")
    fi
    if ! confirm_action "$prompt"; then
      exiterr "用户取消安装"
    fi

    # 源码编译安装python 3.10
    install_py
    if [ -x "$PY_BIN" ]; then
      return 0
    else
      exiterr "Python ${PY_VERSION} 安装失败"
    fi
  }

  # install_py_venv() {
  #   if check_py_version; then
  #     "$PY_BIN" -m venv "$VENV_DIR" # 创建虚拟环境
  #   fi
  # }

  ## ---------------------------------------------
  ## ---------------------------------------------
  ## ---------------------------------------------
  # 判断是否已有 Python 3.10+
  check_python_version() {
    local py_path=$1
    if [ -n "$py_path" ] && "$py_path" -c 'import sys; exit(0) if sys.version_info >= (3,10) else exit(1)'; then
      # 确保 venv 和 ensurepip 都存在
      if "$py_path" -m venv --help >/dev/null 2>&1 \
        && "$py_path" -m ensurepip --version >/dev/null 2>&1; then
        PY_BIN="$py_path"
        return 0
      fi
    fi
    return 1
  }

  # 检查 Python 是否已安装
  check_existing_python() {
    local default_bin="$(command -v python3 2>/dev/null || true)"
    local local_bin="$PY_INST_DIR/bin/python3"
    if check_python_version "$default_bin"; then
      return 0
    elif check_python_version "$local_bin"; then
      return 0
    else
      return 1
    fi
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

  # 下载并安装 Python standalone
  install_python_standalone() {
    local system_type=$(detect_system)
    local python_url=$(get_python_url "$system_type")

    info "下载 Python $PY_VERSION standalone..."
    info "下载地址: $python_url"

    # 下载文件（支持断点续传）
    echo "wget -c -q --show-progress -O $PY_GZ_FILE $python_url"
    wget -c -q --show-progress -O "$PY_GZ_FILE" "$python_url"

    # 解压到安装目录
    info "安装 Python 到 $PY_INST_DIR..."
    mkdir -p "$PY_INST_DIR" # 确保安装目录存在
    if ! tar -xf "$PY_GZ_FILE" -C "$PY_INST_DIR" --strip-components=1; then
      exiterr "解压安装失败"
    fi

    # 清理临时文件
    info "Python $PY_VERSION 安装完成！"
  }

  # 验证 Python 安装
  verify_python() {
    local python_bin="$PY_INST_DIR/bin/python3"

    if [[ ! -x "$python_bin" ]]; then
      exiterr "Python 安装验证失败: $python_bin 不存在或不可执行"
    fi

    local inst_version=$("$python_bin" --version 2>&1 | awk '{print $2}')
    if [[ "$inst_version" != "$PY_VERSION" ]]; then
      exiterr "版本不匹配: 期望 $PY_VERSION, 实际 $inst_version"
    fi

    info "Python 验证成功: $inst_version"
  }

  # 创建虚拟环境并安装常用包
  create_venv_with_packages() {
    info "创建虚拟环境 $VENV_DIR..."

    # 删除已存在的虚拟环境
    if [[ -d "$VENV_DIR" ]]; then
      if confirm_action "虚拟环境 $VENV_DIR 已存在，是否删除重建？"; then
        rm -rf "$VENV_DIR"
      else
        warning "跳过虚拟环境创建"
        return
      fi
    fi

    # 创建虚拟环境
    if ! "$PY_BIN" -m venv "$VENV_DIR"; then
      exiterr "创建虚拟环境失败"
    else
      sh_pip_install # 激活虚拟环境并安装所需的基础包
      success "虚拟环境创建成功！"
    fi
  }

  # 安装 Python 并创建虚拟环境
  install_py_venv() {
    # 检查是否需要重新安装 Python
    if ! check_existing_python; then
      install_python_standalone
      verify_python
    fi

    # 创建虚拟环境并安装包
    create_venv_with_packages
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
