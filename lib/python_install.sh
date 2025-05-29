#!/bin/bash

# 确保只被加载一次
if [[ -z "${LOADED_PYTHON_INSTALL:-}" ]]; then
  LOADED_PYTHON_INSTALL=1

  # 声明全局变量
  : "${LIB_DIR:=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}" # bin direcotry
  source "$LIB_DIR/msg_handler.sh"

  PY_VERSION="3.10.14"
  PY_INST_DIR="$HOME/.local/python-$PY_VERSION"
  PY_TAR_URL="https://www.python.org/ftp/python/${PY_VERSION}/Python-${PY_VERSION}.tgz"
  PY_TAR_FILE="/tmp/Python-${PY_VERSION}.tgz"
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
    # curl -LC- "https://www.python.org/ftp/python/3.10.14/Python-3.10.14.tgz" -o "/tmp/Python-3.10.14.tgz"
    curl -LC- "$PY_TAR_URL" -o "$PY_TAR_FILE"
    # tar -xf "/tmp/Python-3.10.14.tgz" -C /tmp
    tar -xf "$PY_TAR_FILE" -C /tmp
    # cd "/tmp/Python-3.10.14"
    cd "/tmp/Python-${PY_VERSION}"

    # 编译安装
    # ./configure --prefix="$HOME/.local/python-3.10.14" --enable-optimizations
    ./configure --prefix="$PY_INST_DIR" --enable-optimizations
    make -j$(nproc)
    make install

    # 成功后输出路径
    echo "$PY_INST_DIR/bin/python3.10"
  }

  check_PY_VERSION() {
    # 判断是否已有 Python 3.10+
    local py_path=$(command -v python3 2>/dev/null || true)
    if [ -n "$py_path" ] && "$py_path" -c 'import sys; exit(0) if sys.version_info >= (3,10) else exit(1)'; then
      PY_BIN="$py_path"
      exit 0
    fi

    # 检查编译工具
    if [ "$(check_glibc)" -eq 0 ]; then
      exiterr "系统 glibc 版本过低，不能安装 Python 3.10"
    fi

    # 询问是否安装
    # local prompt=$(string "python 版本过低，是否安装 Python {0} 到 ~/.local？" "${PY_VERSION}")
    local prompt=$(string "python 版本过低，是否安装 Python ${PY_VERSION} 到 ~/.local？")
    if ! confirm_action "$prompt"; then
      exiterr "用户取消安装"
    fi

    # 源码编译安装python 3.10
    PY_BIN=install_py
    if [ -x "$PY_BIN" ]; then
      exit 0
    else
      exiterr "Python ${PY_VERSION} 安装失败"
    fi
  }

  install_py_venv() {
    if check_PY_VERSION; then
      "$PY_BIN" -m venv "$VENV_DIR" # 创建虚拟环境
    fi
  }

fi
