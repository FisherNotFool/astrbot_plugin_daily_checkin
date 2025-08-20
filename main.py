import asyncio
from pathlib import Path
from typing import Dict

from astrbot.api.config import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger

# 1. 修改插件注册信息
@register("daily_checkin", "卢言 & FoolFish", "一个QQ群签到成长系统", "0.1.0")
# 2. 修改类名，使其更有意义
class DailyCheckinPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        """
        插件初始化方法。
        - 接收并保存配置
        - 初始化数据文件路径
        - 创建数据读写的异步锁
        """
        super().__init__(context)
        # 3. 保存从 _conf_schema.json 加载的配置
        self.config = config

        # 4. 定义数据文件的路径，确保它们在 astrbot/data 目录下
        data_dir = self.context.get_data_path()
        self.user_data_path = data_dir / "checkin_user_data.json"
        self.shop_data_path = data_dir / "checkin_shop_data.json"

        # 5. 初始化用于存储数据的变量
        self.user_data: Dict = {}
        self.shop_data: Dict = {}

        # 6. 创建一个异步锁，用于防止并发读写数据时发生冲突
        self.data_lock = asyncio.Lock()

        logger.info("签到插件已加载，配置已读取。")


    async def initialize(self):
        """异步初始化，之后我们将在这里加载数据和设置定时任务。"""
        pass

    # 我们暂时保留 helloworld 指令用于测试
    @filter.command("helloworld")
    async def helloworld(self, event: AstrMessageEvent):
        """这是一个 hello world 指令"""
        # 之后我们可以修改这里来测试配置是否加载成功
        base_price = self.config.get("shop_settings", {}).get("base_price", "未找到")
        yield event.plain_result(f"Hello! 签到插件已加载。从配置中读取到商店基础价格为: {base_price}")

    async def terminate(self):
        """插件卸载/停用时调用，之后我们将在这里保存数据。"""
        pass
