#!/usr/bin/env python3

"""
Language Cache with diskcache
Redis-like python cache for sharing language messages loaded from properties files.
Base module, DO NOT depends on other modules
"""

import os
from pathlib import Path
import re
from datetime import datetime
import sys
from typing import Dict, List, Optional, Union
from diskcache import Cache


sys.path.append(str(Path(__file__).resolve().parent.parent.parent))  # add root sys.path

from python.debug_tool import print_array


# 获取当前文件的绝对路径的父目录
PARENT_DIR = Path(__file__).resolve().parent.parent.parent
PROP_PATH = PARENT_DIR / "config" / "lang"
DEFAULT_LANG = "en"
CODE_POSTFIX = ".py"
CACHE_PATH = "/tmp/sj_cache"
INIT_KEY = "__lang_cache_initialized__"


def read_lang_prop(fn):
    """读取配置文件为数组"""
    with open(fn, "r", encoding="utf-8") as fh:
        lines = fh.readlines()
    return [line.rstrip("\n") for line in lines]


def get_lang_file(prefix: str = "") -> str:
    """Get the path to the message language file"""
    lang_format = os.environ.get("LANGUAGE")  # e.g. zh_CN:zh
    if ":" in lang_format:
        primary_lang = lang_format.split(":")[0]  # zh_CN
        fallback_lang = lang_format.split(":")[1]  # zh
    else:
        primary_lang = lang_format
        fallback_lang = None

    # First, look for the complete language file
    primary_file = os.path.join(PROP_PATH, f"{prefix}{primary_lang}.properties")
    if os.path.isfile(primary_file):
        return primary_file

    # Next, look for the simplified language file
    if fallback_lang:
        fallback_file = os.path.join(PROP_PATH, f"{prefix}{fallback_lang}.properties")
        if os.path.isfile(fallback_file):
            return fallback_file

    # If neither is found, return default file
    return os.path.join(PROP_PATH, f"{prefix}{DEFAULT_LANG}.properties")


def load_message_prop() -> Dict[str, str]:
    """Load message translations for .py files"""
    lang_file = get_lang_file()
    lines = read_lang_prop(lang_file)

    language_msgs: Dict[str, str] = {}
    current_file = ""

    try:
        i = 0
        while i < len(lines):
            line = lines[i]

            # Check for file marker: #■=filename
            file_match = re.match(r"^#\s*■=(.+)$", line)
            if file_match:
                filename = file_match.group(1).strip()
                # Only process .py files
                if filename.endswith(CODE_POSTFIX):
                    current_file = filename
                else:
                    current_file = ""
                i += 1
                continue

            # Skip if not processing .py file, empty lines, or comments
            if not current_file or not line.strip() or line.lstrip().startswith("#"):
                i += 1
                continue

            # Match key-value pairs KEY=VALUE
            kv_match = re.match(r"^([A-Za-z0-9_-]+)=(.*)$", line)
            if kv_match:
                key = kv_match.group(1)
                value_ln = kv_match.group(2)
                value = value_ln

                # Handle multi-line values ending with "\"
                if value_ln.rstrip().endswith("\\"):
                    while i < len(lines):
                        i += 1
                        value_ln = lines[i]
                        value = value.rstrip()[:-1] + "\n" + value_ln  # Remove trailing backslash
                        if not value_ln.rstrip().endswith("\\"):
                            break  # Last line has no trailing backslash

                # Store in dictionary with file prefix
                full_key = f"{current_file}:{key}"
                language_msgs[full_key] = value

            i += 1

    except Exception as e:
        print(f"[ERROR] Error loading properties file {lang_file}: {e}")
        return {}

    # message for debug
    time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[INFO] Loaded {len(language_msgs)} py messages from {lang_file} on {time}")
    print()

    return language_msgs


class LangCache:
    _instance = None  # 单例缓存实例

    def __new__(cls, cache_path: str = CACHE_PATH):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.cache_path = cache_path
            cls._instance.cache = None
            cls._instance._closed = True
        return cls._instance

    @classmethod
    def get_instance(cls):
        instance = cls.__new__(cls)
        instance.init_cache()  # 确保初始化只做一次
        return instance

    def init_cache(self) -> None:
        """
        一次性写入所有语言数据，每条记录独立存储
        """
        if self.cache is None or self._closed or not os.path.exists(self.cache_path):
            self.cache = Cache(self.cache_path)
            self._closed = False

        if self.cache.get(INIT_KEY):  # 缓存已经初始化过
            return

        lang_dict: Dict[str, str] = load_message_prop()
        with self.cache.transact():
            for k, v in lang_dict.items():
                self.cache.set(k, v)
        self.cache.set(INIT_KEY, True)

    def get(self, keys: Optional[Union[str, List[str]]] = None) -> Optional[Union[str, Dict[str, Optional[str]]]]:
        """
        按需读取：
        - keys=None 返回全部数据（慎用，耗内存）
        - keys=单个字符串 返回单条
        - keys=字符串列表 返回多条，返回 dict
        """
        if self.cache is None or self._closed:
            raise RuntimeError("Cache not initialized")

        if keys is None:
            # 读取全部所有key，注意几百条可以，更多数据不推荐
            all_keys = list(self.cache.iterkeys())
            return {k: self.cache.get(k) for k in all_keys}
        if isinstance(keys, str):
            return self.cache.get(keys)
        if isinstance(keys, list):
            return {k: self.cache.get(k) for k in keys}

    def close_cache(self):
        """
        Close the cache and release resources
        """
        if self.cache and not self._closed:
            self.cache.close()
            self._closed = True

    def clear_cache(self):
        """
        Clear the cache and delete the cache file
        """
        if self.cache and not self._closed:
            self.cache.close()
            self._closed = True
        self.cache = Cache(self.cache_path)
        self.cache.clear()


# ==== 使用示例 ====

if __name__ == "__main__":
    lang_cache = LangCache.get_instance()

    print_array(lang_cache.get())  # all items
    print(lang_cache.get("python/i18n.py:A7XPUC"))  # single line
    print_array(
        lang_cache.get(
            [
                "python/file_util.py:DvpZ6Q",
                "python/file_util.py:Dxey7R",
                "python/i18n.py:A7XPUC",
                "python/i18n.py:Aw30Tu",
            ]
        )
    )  # multiline

    lang_cache.close_cache()
