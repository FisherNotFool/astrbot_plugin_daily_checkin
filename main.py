import asyncio
import json
from pathlib import Path
from typing import Dict, Optional
import random
from datetime import date, timedelta
from typing import Dict, Optional, Tuple

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
        self.fortunes: Dict = {} # 新增: 用于存储签文

        self.data_lock = asyncio.Lock()

        # [新增] 在初始化时加载 fortunes.json
        try:
            fortunes_path = Path(__file__).parent / "fortunes.json"
            with open(fortunes_path, 'r', encoding='utf-8') as f:
                self.fortunes = json.load(f)
            logger.info("签文数据加载成功。")
        except Exception as e:
            logger.error(f"加载签文数据 fortunes.json 失败: {e}")

        logger.info("签到插件已加载，配置已读取。")

    # [新增] 获取品级和签文的辅助函数
    def _get_rp_grade_and_fortune(self, base_rp: int) -> Tuple[str, str]:
        """根据基础人品值返回对应的品级和一条随机签文。"""
        grade = ""
        if base_rp == 100: grade = "👑 至尊皇家喵"
        elif base_rp == 1: grade = "💎 超级非酋喵"
        elif base_rp == 50: grade = "✨ 幸运双子喵"
        elif base_rp in [33, 66, 88, 99]: grade = "🎯 幸运靶心喵"
        elif 1 < base_rp <= 10: grade = "🌧️ 小乌云喵"
        elif 11 <= base_rp <= 30: grade = "🌤️ 温温喵喵茶"
        elif 31 <= base_rp <= 60: grade = "🌈 跳跳幸运糖"
        elif 61 <= base_rp <= 80: grade = "🌟 梦幻流星雨"
        elif 81 <= base_rp < 100: grade = "🌠 银河欧皇喵"
        else: grade = "❓ 神秘代码喵"

        # 从加载的签文数据中随机选择一条
        fortune_list = self.fortunes.get(grade, self.fortunes.get("❓ 神秘代码喵", ["签文丢失了喵！"]))
        fortune = random.choice(fortune_list)

        return grade, fortune


    async def _load_data(self):
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

    async def _save_data(self):
        async with self.data_lock:
            try:
                with open(self.user_data_path, 'w', encoding='utf-8') as f:
                    json.dump(self.user_data, f, ensure_ascii=False, indent=4)
                with open(self.shop_data_path, 'w', encoding='utf-8') as f:
                    json.dump(self.shop_data, f, ensure_ascii=False, indent=4)
            except Exception as e:
                logger.error(f"保存数据时发生错误: {e}")

    async def initialize(self):
        await self._load_data()
        logger.info("数据加载完成。")

    @filter.command("jrrp", alias={'签到', '今日人品'})
    async def daily_check_in(self, event: AstrMessageEvent):
        """每日签到指令，获取人品和可能的彩蛋奖励。"""
        user_id = event.get_sender_id()
        today_str = date.today().isoformat()

        async with self.data_lock:
            if user_id not in self.user_data:
                initial_attrs = self.config.get("initial_attributes", {})
                self.user_data[user_id] = {
                    "rp": 0, "attributes": initial_attrs.copy(),
                    "check_in": {"continuous_days": 0, "last_date": ""}
                }

            user = self.user_data[user_id]
            check_in_info = user["check_in"]

            if check_in_info["last_date"] == today_str:
                yield event.plain_result("你今天已经签到过了，明天再来吧！")
                return

            yesterday_str = (date.today() - timedelta(days=1)).isoformat()
            if check_in_info["last_date"] == yesterday_str:
                check_in_info["continuous_days"] += 1
            else:
                check_in_info["continuous_days"] = 1

            cfg_checkin = self.config.get("check_in_settings", {})
            max_days = cfg_checkin.get("max_continuous_days", 15)
            bonus_per_day = cfg_checkin.get("bonus_per_day", 0.02)
            continuous_days = min(check_in_info["continuous_days"], max_days)

            base_rp = random.randint(cfg_checkin.get("base_rp_min", 1), cfg_checkin.get("base_rp_max", 100))
            multiplier = 1 + (continuous_days - 1) * bonus_per_day
            total_rp_gain = round(base_rp * multiplier)
            user["rp"] += total_rp_gain

            bonus_msg = ""
            attributes_to_update = []
            attribute_list = list(user["attributes"].keys())
            if base_rp == 100: attributes_to_update = random.sample(attribute_list, k=min(len(attribute_list), 5))
            elif base_rp in [1, 50]: attributes_to_update = random.sample(attribute_list, k=min(len(attribute_list), 2))
            elif base_rp in [33, 66, 88, 99]: attributes_to_update = random.sample(attribute_list, k=min(len(attribute_list), 1))

            if attributes_to_update:
                attribute_increment = self.config.get("shop_settings", {}).get("attribute_increment", 0.1)
                bonus_parts = []
                for attr in attributes_to_update:
                    user["attributes"][attr] = round(user["attributes"][attr] + attribute_increment, 1)
                    bonus_parts.append(f"{attr.capitalize()}+{attribute_increment}")
                bonus_msg = f"\n✨幸运暴击！获得 {', '.join(bonus_parts)}"

            check_in_info["last_date"] = today_str

            # [修改] 使用新的格式生成回复
            grade, fortune = self._get_rp_grade_and_fortune(base_rp)

            divider = "❀✧⋆✦❃✧⋆❀❃✦⋆✧❀✧⋆✦❃✧⋆❀❃✦⋆✧❀"

            rp_calc_str = f"({base_rp} {f'x {multiplier:.2f}' if multiplier > 1 else ''})"

            reply = (
                f"{divider}\n"
                f"【喵星人品检测报告书】\n"
                f"⋆⋆⃕　品级：{grade}\n"
                f"⋆⋆⃕　人品值：{total_rp_gain} {rp_calc_str}\n\n"
                f"❃✦⋆ 签 文 ⋆✦❃\n"
                f"{fortune}"
                f"{bonus_msg}\n"
                f"{divider}"
            )
            yield event.plain_result(reply)

    async def terminate(self):
        await self._save_data()
        logger.info("数据已成功保存。")