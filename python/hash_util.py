#!/usr/bin/env python3

import hashlib
import os
import sys
from ruamel.yaml import YAML

# 动态添加当前目录到 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from debug_tool import (
    test_assertion,
)

BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+_"  # url安全
HASH = "Z-HASH"
HASH_YML = "hash"
PROP_FILE = {}  # key=path/program; value = Hash Code
PROP_FUNC = {}  # key=Hash Code; value = path/program func_name
PROP_MSG = {}  # key=Hash Code + "_" + LineNo + "_" + order; value = message
YML_PATH = "/usr/local/shell/config/lang/_lang.yml"


# ==============================================================================
# _djb2_with_salt           计算hash code
# _number_to_base64         数值 => 64进制
# _padded_number_to_base64  数值_位数 => 64进制
# _base64_to_number         64进制 => 数值
# get_prop_files            获取hash code（True/False 是否找到了匹配节点）
# set_prop_file             hash code => 全局字典 PROP_FILE
# get_prop_msg              hash code + order => 64进制hash code
# set_prop_msg              hash code + order => 全局字典 PROP_MSG
# ==============================================================================


# ==============================================================================
# base64转换函数
# ==============================================================================
def _number_to_base64(num):
    """
    将数字转换为base64字符串

    参数:
        num: 要转换的数字

    返回:
        base64编码的字符串
    """

    # 处理0的特殊情况
    if num == 0:
        return "A"  # 0在base64中通常表示为A

    result = ""
    num = int(num)
    while num > 0:
        result = BASE64_CHARS[num % 64] + result
        num //= 64

    return result


def _padded_number_to_base64(*args):
    """
    固定长度64进制转换
    支持多个参数，每个参数可以是:
    - 数字 或 "数字_长度": 数字转换为(固定长度的)base64编码
    - "字符串!" 或 "字符串!_长度": 直接使用64进制字符串(固定长度)

    指定长度时，结果不满指定长度自动左侧填充A，超过指定长度只取右侧指定位数

    参数:
        *args: 可变数量的参数
               如: _padded_number_to_base64("123456_3", 789, "ABC!", "DEF!_2")

    返回:
        固定长度的base64编码字符串
    """
    result = ""

    for arg in args:
        # 模式匹配
        match str(arg):
            # Case 1: 有指定长度的情况 ("数字_位数" 或 "字符串!_位数")
            case length_format if "_" in length_format:
                value, length = length_format.split("_", 1)
                length = int(length)

                # 如果以"!"结尾视为64进制，否则将10进制数字转换为64进制
                s_64 = value[:-1] if value.endswith("!") else _number_to_base64(int(value))

                # 格式化为指定长度
                result += "A" * (length - len(s_64)) + s_64 if len(s_64) < length else s_64[-length:]

            # Case 2: 无指定长度的情况 ("数字" 或 "字符串!")
            case direct_value:
                # 如果是数值，转为64进制，否则直接使用去掉!的字符串
                result += direct_value[:-1] if direct_value.endswith("!") else _number_to_base64(int(direct_value))

    return result


def _base64_to_number(s):
    """
    将base64字符串转换为数字

    参数:
        s: base64编码的字符串

    返回:
        解码后的数字
    """

    # 检查输入是否为空
    if not s:
        return 0

    result = 0
    for c in s:
        # 找到字符在字符集中的位置
        position = BASE64_CHARS.find(c) + 1
        result = result * 64 + position - 1

    return result


def init_meta_props():
    # 读yaml
    with open(YML_PATH, "r") as f:
        data = YAML().load(f)
    file_yml = data["file"] = data["file"] if isinstance(data.get("file"), dict) else {}
    # 重置全局变量
    for item in file_yml.values():
        PROP_FILE[item[HASH]] = True


# ==============================================================================
# 函数 字符串文本的hash code计算（6位字符串 | 22位字符串）
# ==============================================================================
def _djb2_with_salt(text: str, freq: int = 20) -> int:
    """均匀采样若干个字符参与DJB2哈希计算，加上字符串长度作为salt"""
    hash_value = 5381
    step = max(1, len(text) // freq)
    for i in range(0, min(len(text), step * freq), step):
        hash_value = (((hash_value << 5) + hash_value) + ord(text[i])) & 0xFFFFFFFF
    return (((hash_value << 5) + hash_value) + len(text)) & 0xFFFFFFFF


def _djb2_with_salt_20(text: str) -> int:
    """均匀采样20个字符参与DJB2哈希计算，字符串长度作为salt"""
    return _djb2_with_salt(text, 20)


def md5(text: str) -> int:
    """返回MD5数值"""
    return int.from_bytes(hashlib.md5(text.encode("utf-8")).digest(), byteorder="big")


def set_prop_files(lang_data, file_yml):
    hashes = {}
    result = {}

    for s in file_yml.keys():
        h = _djb2_with_salt_20(s)

        if h in hashes:
            if hashes[h] == s:
                continue  # 忽略重复
            # 冲突但不相同，使用 MD5
            for item in [hashes[h], s]:
                result[md5(item)] = item  # 改用 MD5 覆盖原来的hash code
            del result[h]  # 删除之前的 DJB2 冲突键
        elif h not in result:
            result[h] = s
            hashes[h] = s

    # 最后写回配置文件
    for key, value in result.items():
        PROP_FILE[key] = True  # 全局变量
        file_yml[value][HASH_YML] = key  # yml配置
        if value in lang_data:
            lang_data[value][HASH] = key  # properties配置


def get_prop_file(s):
    if not PROP_FILE:
        init_meta_props()

    h = _djb2_with_salt_20(s)
    if h in PROP_FILE:
        return h  # 返回 hash code
    else:
        return md5(s)  # 改用 MD5


def set_prop_msgs(content):
    hashes = {}
    result = {}

    for s in content:
        parts = s.split(None, 3)
        type, lineno, order, msg = parts

        h = _djb2_with_salt_20(msg)

        if h in hashes:
            if hashes[h] == msg:
                continue  # 忽略重复
            # 冲突但不相同，使用 MD5
            for item in [hashes[h], msg]:
                result[md5(item)] = item  # 改用 MD5 覆盖原来的hash code
            del result[h]  # 删除之前的 DJB2 冲突键
        elif h not in result:
            result[h] = f"{msg} #{type}@{lineno}@{order.replace('-', '')}"  # 添加注释
            hashes[h] = msg

    # 最后循环 result，key 改为 64 进制
    result_base64 = {}
    for key, value in result.items():
        result_base64[_padded_number_to_base64(f"{key}_6")] = value

    return result_base64


# =============================================================================
# 调试测试函数（base64转换、PROP_FILE）
# =============================================================================
def main():
    # 测试1：base64转换
    a = 1213312
    b = 0
    b64 = _padded_number_to_base64(f"{a}_4", f"{b}_2")
    c = _base64_to_number(b64[:4])  # 前4位
    d = _base64_to_number(b64[4:6])  # 后2位
    test_assertion("c == a and d == b", f"base64 convert: {b64}")

    # 测试2：PROP_FILE key / value
    a = "bin/init_main.sh"
    idx = _djb2_with_salt_20(a)
    test_assertion("idx == 3525264606", f"set PROP_FILE: {idx}")

    idx2 = get_prop_file(a)
    test_assertion(lambda: idx == idx2, f"get PROP_FILE: {idx2}")


# =============================================================================
# 命令行入口（只有直接运行本脚本才进入）
# =============================================================================
if __name__ == "__main__":
    main()
