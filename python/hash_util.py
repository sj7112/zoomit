#!/usr/bin/env python3

import hashlib
import re
import os
import sys

# 动态添加当前目录到 sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from debug_tool import (
    print_array,
    test_assertion,
)

BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+_"  # url安全
SEPARATOR = "@@"
PROP_FUNC = {}  # key=Hash Code; value = path/program func_name
PROP_MSG = {}  # key=Hash Code + "_" + LineNo + "_" + order; value = message


# ==============================================================================
# _hash_djb2                计算hash code
# _number_to_base64         数值 => 64进制
# _padded_number_to_base64  数值_位数 => 64进制
# _base64_to_number         64进制 => 数值
# get_prop_func             获取hash code（True/False 是否找到了匹配节点）
# set_prop_func             hash code => 全局字典 PROP_FUNC
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


# ==============================================================================
# 程序 + 函数的hash code计算（6位字符串：线性探测解决冲突）
# ==============================================================================
def _hash_djb2(s):
    """
    DJB2哈希函数

    参数:
        s: 要哈希的字符串

    返回:
        整数哈希值，范围在0到(64^3-1)之间
    """
    hash_val = 5381
    mask = 64 * 64 * 64 - 1  # 相当于 64^3-1 = 262,144

    for c in s:
        hash_val = ((hash_val * 33) + ord(c)) & mask

    return hash_val


def get_prop_func(file, func):
    """
    查找哈希表索引位置

    参数:
        file_name: 文件名（示例格式: "bin/init_base_func.sh"）
        func_name: 函数名（示例格式: "select_mirror"）

    返回:
        如果找到匹配的键，返回(索引, True)
        如果找到可用的空位，返回(索引, False)
    """
    key = f"{file}{SEPARATOR}{func}"  # 格式: "bin/init_base_func.sh@@select_mirror"
    mask = 64 * 64 * 64 * 64 - 1  # 取模掩码
    idx = (_hash_djb2(key) * 64) & mask  # 起始索引，64对齐

    while True:
        if idx not in PROP_FUNC:
            return idx, False  # 空位，说明没找到

        if PROP_FUNC[idx] == key:
            return idx, True  # 找到匹配，说明存在

        # 探测下一个索引（跳过64倍数）
        idx = (idx + (2 if idx & 63 == 63 else 1)) & mask


def set_prop_func(file, func):
    """
    存储到全局字典 PROP_FUNC ，并返回其哈希索引位置

    参数:
        file_name: 文件名（示例格式: "bin/init_base_func.sh"）
        func_name: 函数名（示例格式: "select_mirror"）

    返回:
        字符串在字典中的索引位置
    """
    key = f"{file}{SEPARATOR}{func}"  # 格式: "bin/init_base_func.sh@@select_mirror"
    mask = 64 * 64 * 64 * 64 - 1  # 相当于 64^4-1 = 16,777,215
    idx = (_hash_djb2(key) * 64) & mask  # 初始索引（64对齐）

    # Linear probing for collision resolution
    while idx in PROP_FUNC:
        if PROP_FUNC[idx] == key:
            return idx  # 已存在，直接返回

        # 探测下一个索引（跳过64倍数）
        idx = (idx + (2 if idx & 63 == 63 else 1)) & mask

    PROP_FUNC[idx] = key  # 写入新值
    return idx


# ==============================================================================
# 函数 字符串文本的hash code计算（6位字符串 | 22位字符串）
# ==============================================================================
def djb2_with_salt_10(text: str, salt: int = 0) -> int:
    """均匀采样10个字符参与DJB2哈希计算，加上字符串长度作为salt"""
    hash_value = 5381
    step = max(1, len(text) // 10)
    for i in range(0, min(len(text), step * 10), step):
        hash_value = ((hash_value << 5) + hash_value) + ord(text[i])
    hash_value = ((hash_value << 5) + hash_value) + salt
    return hash_value & 0xFFFFFFFF


def set_prop_msgs(content):
    hashes = {}
    result = {}

    for str in content:
        parts = str.split(None, 3)
        type, lineno, order, msg = parts

        h = djb2_with_salt_10(msg, len(msg))

        if h in hashes:
            if hashes[h] == msg:
                continue  # 忽略重复
            # 冲突但不相同，使用 MD5
            for item in [hashes[h], msg]:
                md5_val = int.from_bytes(hashlib.md5(item.encode("utf-8")).digest(), byteorder="big")  # 改用 MD5
                result[md5_val] = item  # 存入后者，覆盖原来的
            del result[h]  # 删除之前的 DJB2 冲突键
        elif h not in result:
            result[h] = f"{msg} # {type}@{lineno}@{order.replace('-', '')}"  # 添加注释
            hashes[h] = msg

    # 最后循环 result，key 改为 64 进制
    result_base64 = {}
    for key, value in result.items():
        result_base64[_number_to_base64(key)] = value

    return result_base64


def get_prop_msg(hash, pos):
    """
    根据哈希码和计数获取消息

    参数:
        hash: 父函数的哈希码
        pos: 查找的计数值

    返回:
        找到的消息，如果未找到则返回None
    """
    # key=6位base64编码
    key = _padded_number_to_base64(f"{hash}_4", f"{pos}_2")
    return PROP_MSG.get(key)


# =============================================================================
# 调试测试函数（base64转换、PROP_FUNC）
# =============================================================================
def main():
    # 测试1：base64转换
    a = 1213312
    b = 0
    b64 = _padded_number_to_base64(f"{a}_4", f"{b}_2")
    c = _base64_to_number(b64[:4])  # 前4位
    d = _base64_to_number(b64[4:6])  # 后2位
    test_assertion("c == a and d == b", f"base64 convert: {b64}")

    # 测试2：PROP_FUNC key / value
    a = ["bin/init_base_func.sh", "select_mirror"]
    idx = set_prop_func(*a)
    test_assertion("idx == 9171520", f"set PROP_FUNC: {idx}")

    idx2, found = get_prop_func(*a)
    test_assertion(lambda: found and idx == idx2, f"get PROP_FUNC: {idx2}")


# =============================================================================
# 命令行入口（只有直接运行本脚本才进入）
# =============================================================================
if __name__ == "__main__":
    main()
