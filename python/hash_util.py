#!/usr/bin/env python3

import hashlib
import math
from pathlib import Path
import sys
from ruamel.yaml import YAML


sys.path.append(str(Path(__file__).resolve().parent.parent))  # add root sys.path

from python.debug_tool import test_assertion

DUPL_HASH = "Z-HASH"  # hash池（一个文件中不允许有重复的hash）
BASE64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"  # url安全
PROP_FILE = {}  # key=path/program; value = 待翻译消息列表

# 获取当前文件的绝对路径的父目录
PARENT_DIR = Path(__file__).resolve().parent.parent
YML_PATH = PARENT_DIR / "config" / "lang" / "_lang.yml"


# ==============================================================================
# _djb2_with_salt           计算hash code
# _number_to_base64         数值 => 64进制
# _padded_number_to_base64  数值_位数 => 64进制
# _base64_to_number         64进制 => 数值
# set_func_msgs             待翻译内容列表(单文件) => 64进制hash code
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
    for key in file_yml.keys():
        PROP_FILE[key] = False  # 初始化时候，设置为false；实际使用时，逐步加入进来


# ==============================================================================
# 函数 字符串文本的hash code计算（6位字符串 | 22位字符串）
# ==============================================================================
def _find_largest_prime_below(n: int) -> int:
    """返回小于 n 的最大质数（针对小数 < 10^5 有效）"""
    # 小于等于5时，直接查表（包含<0）
    if n <= 5:
        lookup = [0, 0, 1, 1, 2, 3]
        return lookup[max(0, n)]

    # 从 n-1 开始倒序搜索，只查 6k±1 形式的候选
    i = n - 1 if (n - 1) % 6 in (1, 5) else n - 2
    while i >= 5:
        if i % 2 == 0 or i % 3 == 0:
            i -= 1
            continue
        sqrt_i = int(math.isqrt(i))
        is_prime = True
        for d in range(5, sqrt_i + 1, 6):
            if i % d == 0 or i % (d + 2) == 0:
                is_prime = False
                break
        if is_prime:
            return i
        i -= 2 if i % 6 == 5 else 4  # 保证 6k±1 步进

    return 3  # 最后兜底，理论上不会到这


def _find_smaller_prime(step: int) -> int:
    """找到和20互质，小于limit的合适质数"""
    primes = [19, 17, 13, 11, 7, 3]
    for prime in primes:
        if prime < step:
            return prime
    return 1  # 默认返回3


def _djb2_with_salt_bytes(text: str, freq: int = 20, encoding: str = "utf-8") -> int:
    """基于字节的DJB2哈希函数"""
    # 将字符串转换为字节流
    byte_data = text.encode(encoding)
    byte_length = len(byte_data)
    step = max(1, byte_length // freq)

    # 字节流采样
    offset = _find_largest_prime_below(byte_length - step * freq)  # 用质数作为采样头部偏离值
    new_byte_data = []
    if step == 1:
        new_byte_data = byte_data[offset : offset + freq]  # 全部采样
    else:
        times = _find_smaller_prime(step)  # 小于 step 和 20 的质数，增加step的随机性
        idx = offset
        for i in range(freq):
            new_byte_data.append(byte_data[idx])  # 均匀采样
            idx += step * times
            if idx >= byte_length:
                idx = offset  # 利用互质的特性(费马小定理)

    # 用采样数据计算hash
    hash_value = 5381
    for byte_value in new_byte_data:
        hash_value = (((hash_value << 5) + hash_value) + byte_value) & 0xFFFFFFFF

    # 使用字节长度作为salt
    return (((hash_value << 5) + hash_value) + byte_length) & 0xFFFFFFFF


def _djb2_with_salt_20(text: str) -> int:
    """均匀采样20个字符参与DJB2哈希计算，字符串长度作为salt"""
    return _djb2_with_salt_bytes(text, 20)


def md5(text: str) -> str:
    """返回MD5数值"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def set_func_msgs(file_rec, func_name, content):
    """为每个函数中的对应文本获取hash"""
    d_hash = file_rec[DUPL_HASH]
    for s in content:
        parts = s.split(None, 2)
        type, ln_no, msg = parts

        h = _djb2_with_salt_20(msg)
        if h in file_rec:
            if file_rec[h]["msg"] == msg:
                continue  # 忽略重复
            d_hash[h] = True  # 记录之前的 DJB2 冲突键
            h = md5(msg)  # 出现冲突，使用 MD5

        file_rec[h] = {
            "msg": msg,  # 消息体
            "func": func_name,  # 函数名(临时变量)
            "cmt": f"{type}@{ln_no}",  # 添加注释
        }


def set_file_msgs(results, sh_file):
    """hash冲突解决以及文件内容转换"""
    result = {}
    file_rec = results[sh_file]
    d_hash = file_rec.pop(DUPL_HASH)  #  获取重复hash记录（同时删除临时记录）
    for key, value in file_rec.items():
        func_name = value.pop("func")  # 函数名(临时变量)
        if func_name not in result:
            result[func_name] = {}

        if key in d_hash:
            key = md5(value["msg"])  # key改为MD5格式
        elif type(key) == int:  # 已有MD5格式key不变
            key = _padded_number_to_base64(f"{key}_6")  # key 改为6位 64 进制

        result[func_name][key] = value  # 消息体和备注

    results[sh_file] = result  # 维持顺序：按func_name排序


# =============================================================================
# 调试测试函数（base64转换）
# =============================================================================
def main():
    # 测试1：hash计算
    a = "检测到服务器已配置静态IP，是否调整IP？"
    b = _djb2_with_salt_20(a)
    print(b)
    # 测试2：base64转换
    a = b
    b6 = _padded_number_to_base64(f"{a}_6")
    print(b6)
    b = 0
    b64 = _padded_number_to_base64(f"{a}_4", f"{b}_2")
    c = _base64_to_number(b64[:4])  # 前4位
    d = _base64_to_number(b64[4:6])  # 后2位
    test_assertion("c == a and d == b", f"base64 convert: {b64}")


# =============================================================================
# Command-line entry point
# =============================================================================
if __name__ == "__main__":
    main()
