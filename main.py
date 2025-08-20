import asyncio
import json
from pathlib import Path
from typing import Dict, Optional
import random
from datetime import date, timedelta

# 使用 all 导入，确保所有 API 都可用
from astrbot.api.all import *
from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger # 使用 astrbot 提供的 logger 接口


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
        today_str = date.today().isoformat()

        # 使用异步锁确保数据操作的线程安全
        async with self.data_lock:
            # 1. 初始化新用户数据
            if user_id not in self.user_data:
                initial_attrs = self.config.get("initial_attributes", {})
                self.user_data[user_id] = {
                    "rp": 0,
                    "attributes": initial_attrs.copy(), # 使用copy避免多用户共享一个字典对象
                    "check_in": {"continuous_days": 0, "last_date": ""}
                }

            user = self.user_data[user_id]
            check_in_info = user["check_in"]

            # 2. 检查今天是否已经签到
            if check_in_info["last_date"] == today_str:
                yield event.plain_result("你今天已经签到过了，明天再来吧！")
                return

            # --- 开始签到核心逻辑 ---

            # 3. 计算连续签到天数
            yesterday_str = (date.today() - timedelta(days=1)).isoformat()
            if check_in_info["last_date"] == yesterday_str:
                check_in_info["continuous_days"] += 1
            else:
                check_in_info["continuous_days"] = 1 # 断签或首次签到

            # 读取配置
            cfg_checkin = self.config.get("check_in_settings", {})
            max_days = cfg_checkin.get("max_continuous_days", 15)
            bonus_per_day = cfg_checkin.get("bonus_per_day", 0.02)

            # 限制最高连续天数
            continuous_days = min(check_in_info["continuous_days"], max_days)

            # 4. 计算人品收益
            base_rp = random.randint(cfg_checkin.get("base_rp_min", 1), cfg_checkin.get("base_rp_max", 100))
            multiplier = 1 + (continuous_days - 1) * bonus_per_day
            total_rp_gain = round(base_rp * multiplier)
            user["rp"] += total_rp_gain

            # 5. 处理彩蛋奖励
            bonus_msg = ""
            attributes_to_update = []
            attribute_list = list(user["attributes"].keys())

            if base_rp == 100:
                attributes_to_update = random.sample(attribute_list, k=min(len(attribute_list), 5))
            elif base_rp in [1, 50]:
                attributes_to_update = random.sample(attribute_list, k=min(len(attribute_list), 2))
            elif base_rp in [33, 66, 88, 99]:
                attributes_to_update = random.sample(attribute_list, k=min(len(attribute_list), 1))

            if attributes_to_update:
                attribute_increment = self.config.get("shop_settings", {}).get("attribute_increment", 0.1)
                bonus_parts = []
                for attr in attributes_to_update:
                    user["attributes"][attr] += attribute_increment
                    user["attributes"][attr] = round(user["attributes"][attr], 1) # 避免精度问题
                    bonus_parts.append(f"{attr.capitalize()}+{attribute_increment}") # e.g., Strength+0.1
                bonus_msg = f"\n✨幸运暴击！获得 {', '.join(bonus_parts)}"

            # 6. 更新签到日期
            check_in_info["last_date"] = today_str

            # 7. 构建并发送回复消息
            reply = (
                f"签到成功！\n"
                f"基础人品: {base_rp}\n"
                f"连续签到: {continuous_days}天 (加成: x{multiplier:.2f})\n"
                f"本次获得: {total_rp_gain} 人品\n"
                f"当前总人品: {user['rp']}"
                f"{bonus_msg}"
            )
            yield event.plain_result(reply)


    async def terminate(self):
        """
        插件卸载/停用时调用。
        - 保存数据
        """
        # [修改] 4. 在插件关闭前调用保存数据函数
        await self._save_data()
        logger.info("数据已成功保存。")
