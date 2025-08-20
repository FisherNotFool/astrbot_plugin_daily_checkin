import asyncio
import json
from pathlib import Path
from typing import Dict, Optional

# 1. 使用你提供的正确导入方式
from astrbot.api.all import *
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools


@register("daily_checkin", "FoolFish", "一个QQ群签到成长系统", "0.1.0")
class DailyCheckinPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        """
        插件初始化方法。
        - 接收并保存配置
        - 初始化数据文件路径
        - 创建数据读写的异步锁
        """
        super().__init__(context)
        self.config = config

        # 3. 使用你找到的正确方法 StarTool.get_data_dir() 获取数据目录
        # 这会在 astrbot/data/plugin_data/ 目录下创建一个名为 "daily_checkin" 的专属文件夹
        plugin_data_dir = StarTools.get_data_dir("daily_checkin")

        # 4. 在插件专属目录中定义数据文件路径，文件名可以更简洁
        self.user_data_path = plugin_data_dir / "user_data.json"
        self.shop_data_path = plugin_data_dir / "shop_data.json"

        self.user_data: Dict = {}
        self.shop_data: Dict = {}

        self.data_lock = asyncio.Lock()

        logger.info("签到插件已加载，配置已读取。")


    async def initialize(self):
        """异步初始化，之后我们将在这里加载数据和设置定时任务。"""
        pass

    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令"""
        base_price = self.config.get("shop_settings", {}).get("base_price", "未找到")
        yield event.plain_result(f"Hello! 签到插件已加载。从配置中读取到商店基础价格为: {base_price}")

    async def terminate(self):
        """插件卸载/停用时调用，之后我们将在这里保存数据。"""
        pass
