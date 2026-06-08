"""过滤模块 - 白名单/黑名单访问控制"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class AccessControl:
    """白名单/黑名单模式访问控制"""

    def __init__(self, config: dict, access_list_path: Path):
        self._access_mode = config.get("access_mode", "whitelist")
        self._group_list = set(str(g) for g in config.get("group_list", []))
        self._private_list = set(str(p) for p in config.get("private_list", []))
        self._config_path = access_list_path

        # 持久化名单到 JSON
        self._save_access_list()

    @property
    def access_mode(self) -> str:
        return self._access_mode

    def check_group(self, group_id: str) -> bool:
        """检查群聊是否有权限"""
        group_id = str(group_id)
        if self._access_mode == "whitelist":
            if not self._group_list:
                return True
            return group_id in self._group_list
        else:
            return group_id not in self._group_list

    def check_private(self, user_id: str) -> bool:
        """检查私聊是否有权限"""
        user_id = str(user_id)
        if self._access_mode == "whitelist":
            if not self._private_list:
                return True
            return user_id in self._private_list
        else:
            return user_id not in self._private_list

    def _save_access_list(self):
        """持久化名单到 JSON 文件"""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "access_mode": self._access_mode,
                "group_list": sorted(self._group_list),
                "private_list": sorted(self._private_list),
            }
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存名单失败: {e}")
