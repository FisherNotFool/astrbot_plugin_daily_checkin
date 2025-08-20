import asyncio
import json
from pathlib import Path
from typing import Dict, Optional

# 使用 all 导入，确保所有 API 都可用
from astrbot.api.all import *
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools


@register("daily_checkin", "FoolFish", "一个QQ群签到成长系统", "0.1.0")
class DailyCheckinPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        plugin_data_dir = StarTools.get_data_dir("daily_checkin")
        self.user_data_path = plugin_data_dir / "user_data.json"
        self.shop_data_path = plugin_data_dir / "shop_data.json"
        self.user_data: Dict = {}
        self.shop_data: Dict = {}
        self.data_lock = asyncio.Lock()
        logger.info("签到插件已加载，配置已读取。")

    # [新增] 1. 数据加载函数
    async def _load_data(self):
        """从 JSON 文件加载用户和商店数据，如果文件不存在则初始化为空字典。"""
        async with self.data_lock:
            try:
                with open(self.user_data_path, 'r', encoding='utf-8') as f:
                    self.user_data = json.load(f)
                logger.info("成功加载用户数据。")
            except FileNotFoundError:
                logger.info("未找到用户数据文件，将创建新文件。")
                self.user_data = {}

            try:
                with open(self.shop_data_path, 'r', encoding='utf-8') as f:
                    self.shop_data = json.load(f)
                logger.info("成功加载商店数据。")
            except FileNotFoundError:
                logger.info("未找到商店数据文件，将创建新文件。")
                self.shop_data = {}

    # [新增] 2. 数据保存函数
    async def _save_data(self):
        """将内存中的用户和商店数据异步保存到 JSON 文件。"""
        async with self.data_lock:
            try:
                with open(self.user_data_path, 'w', encoding='utf-8') as f:
                    json.dump(self.user_data, f, ensure_ascii=False, indent=4)
                with open(self.shop_data_path, 'w', encoding='utf-8') as f:
                    json.dump(self.shop_data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.error(f"保存数据时发生错误: {e}")

    async def initialize(self):
        """
        异步初始化。
        - 加载数据
        - (未来)设置定时任务
        """
        # [修改] 3. 在插件启动时调用加载数据函数
        await self._load_data()
        logger.info("数据加载完成。")

    @filter.command("jrrp", alias={'签到', '今日人品'})
    async def daily_check_in(self, event: AstrMessageEvent):
        """每日签到指令，获取人品和可能的彩蛋奖励。"""
        user_id = event.get_sender_id()

        # 1. 确保用户数据结构存在
        # 使用 async with self.data_lock 确保数据操作的原子性
        async with self.data_lock:
            if user_id not in self.user_data:
                # 如果是新用户，则初始化数据
                initial_attrs = self.config.get("initial_attributes", {})
                self.user_data[user_id] = {
                    "rp": 0,
                    "attributes": {
                        "strength": initial_attrs.get("strength", 1.0),
                        "agility": initial_attrs.get("agility", 1.0),
                        "stamina": initial_attrs.get("stamina", 1.0),
                        "intelligence": initial_attrs.get("intelligence", 1.0),
                        "charisma": initial_attrs.get("charisma", 1.0)
                    },
                    "check_in": {
                        "continuous_days": 0,
                        "last_date": "" # 空字符串表示从未签到
                    }
                }

        # 2. 返回签到结果
        # （我们将在下一步实现这里的详细逻辑）
        user_rp = self.user_data[user_id].get("rp", 0)
        yield event.plain_result(f"这是 Jrrp 指令的占位符。签到功能开发中...\n你当前的 RP 为: {user_rp}")


    async def terminate(self):
        """
        插件卸载/停用时调用。
        - 保存数据
        """
        # [修改] 4. 在插件关闭前调用保存数据函数
        await self._save_data()
        logger.info("数据已成功保存。")
