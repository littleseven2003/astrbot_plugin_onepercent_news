"""过滤模块 - 群聊/私聊独立黑白名单访问控制

规则：
- 黑名单模式 + 名单为空 → 全部允许
- 黑名单模式 + 名单不为空 → 名单内禁止，其余允许
- 白名单模式 + 名单为空 → 全部禁止
- 白名单模式 + 名单不为空 → 名单内允许，其余禁止
"""

import json
from pathlib import Path

from astrbot.api import logger


class AccessControl:
    """群聊/私聊独立的白名单/黑名单访问控制。"""

    def __init__(self, config: dict, access_list_path: Path):
        # 群聊
        self._group_mode = config.get("group_access_mode", "blacklist")
        self._group_list = set(str(g) for g in config.get("group_blacklist" if self._group_mode == "blacklist" else "group_whitelist", []))
        # 私聊
        self._private_mode = config.get("private_access_mode", "blacklist")
        self._private_list = set(str(p) for p in config.get("private_blacklist" if self._private_mode == "blacklist" else "private_whitelist", []))

        self._config_path = access_list_path
        self._save_access_list()

    # ---------- 权限检查 ----------

    def check_group(self, group_id: str) -> bool:
        group_id = str(group_id)
        if self._group_mode == "blacklist":
            if not self._group_list:
                return True
            return group_id not in self._group_list
        else:  # whitelist
            if not self._group_list:
                return False
            return group_id in self._group_list

    def check_private(self, user_id: str) -> bool:
        user_id = str(user_id)
        if self._private_mode == "blacklist":
            if not self._private_list:
                return True
            return user_id not in self._private_list
        else:  # whitelist
            if not self._private_list:
                return False
            return user_id in self._private_list

    # ---------- 推送目标获取 ----------

    def get_push_targets(self) -> tuple[list[str], list[str]]:
        """获取自动推送的目标群号和 QQ 号。

        - 白名单模式：推送白名单中的全部条目
        - 黑名单模式：无法枚举全部，返回空
        - 黑名单模式 + 名单为空：无法枚举，返回空
        """
        groups = []
        privates = []

        if self._group_mode == "whitelist" and self._group_list:
            groups = sorted(self._group_list)
        if self._private_mode == "whitelist" and self._private_list:
            privates = sorted(self._private_list)

        return groups, privates

    # ---------- 持久化 ----------

    def _save_access_list(self):
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "group_access_mode": self._group_mode,
                "group_list": sorted(self._group_list),
                "private_access_mode": self._private_mode,
                "private_list": sorted(self._private_list),
            }
            with open(self._config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"保存名单失败: {e}")
