import asyncio
import json
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime, timedelta
import random

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
        today_str = datetime.now().strftime("%Y-%m-%d")

        async with self.data_lock:
            # 1. 初始化新用户数据
            if user_id not in self.user_data:
                initial_attrs = self.config.get("initial_attributes", {})
                self.user_data[user_id] = {
                    "rp": 0,
                    "attributes": { "strength": initial_attrs.get("strength", 5.0), "agility": initial_attrs.get("agility", 5.0), "stamina": initial_attrs.get("stamina", 5.0), "intelligence": initial_attrs.get("intelligence", 5.0), "charisma": initial_attrs.get("charisma", 5.0) },
                    "check_in": { "continuous_days": 0, "last_date": "" }
                }

            user = self.user_data[user_id]

            # 2. 检查是否已经签到
            if user["check_in"]["last_date"] == today_str:
                yield event.plain_result(f"你今天已经签到过了，明天再来吧！\n当前人品: {user['rp']}")
                return

            # 3. 处理连续签到
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            if user["check_in"]["last_date"] == yesterday:
                user["check_in"]["continuous_days"] += 1
            else:
                # 断签
                user["check_in"]["continuous_days"] = 1

            user["check_in"]["last_date"] = today_str

            # 4. 计算人品收益
            check_in_cfg = self.config.get("check_in_settings", {})
            base_rp = random.randint(check_in_cfg.get("base_rp_min", 1), check_in_cfg.get("base_rp_max", 100))

            # 计算倍率
            max_days = check_in_cfg.get("max_continuous_days", 15)
            bonus_per_day = check_in_cfg.get("bonus_per_day", 0.02)
            continuous_days = min(user["check_in"]["continuous_days"], max_days)
            bonus_multiplier = 1 + (continuous_days - 1) * bonus_per_day

            total_rp = round(base_rp * bonus_multiplier)
            user["rp"] += total_rp

            # 5. 构建回复消息
            reply_msg = (
                f"签到成功！\n"
                f"基础人品: {base_rp}\n"
                f"连续签到 {user['check_in']['continuous_days']} 天 (加成: x{bonus_multiplier:.2f})\n"
                f"获得人品: {total_rp}\n"
                f"当前总人品: {user['rp']}"
            )

            # 6. 处理彩蛋 (我们将在下一步添加)
            # ... 彩蛋逻辑 ...

            # 7. 保存数据
            await self._save_data()

        # 在锁外发送消息
        yield event.plain_result(reply_msg)



    async def terminate(self):
        """
        插件卸载/停用时调用。
        - 保存数据
        """
        # [修改] 4. 在插件关闭前调用保存数据函数
        await self._save_data()
        logger.info("数据已成功保存。")
