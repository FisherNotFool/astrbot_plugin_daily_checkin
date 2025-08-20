import asyncio
import json
from pathlib import Path
from typing import Dict
import random
from datetime import date, timedelta
from typing import Dict, Optional, Tuple

# 使用 all 导入，确保所有 API 都可用
from astrbot.api.all import *
from astrbot.api import AstrBotConfig
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register, StarTools
from astrbot.api import logger # 使用 astrbot 提供的 logger 接口
from . import utils


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
        self.save_task: Optional[asyncio.Task] = None # 用于存放后台保存任务

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


    async def _periodic_save(self):
        """后台循环任务，用于定时保存数据。"""
        interval = self.config.get("system_settings", {}).get("auto_save_interval_seconds", 300)
        while True:
            await asyncio.sleep(interval)
            logger.info(f"开始执行定时保存任务（间隔: {interval}秒）...")
            await self._save_data()
            logger.info("定时保存任务完成。")


    async def _refresh_shop(self):
        """刷新商店的商品价格和购买次数。"""
        async with self.data_lock:
            logger.info("开始每日刷新商店...")
            cfg_shop = self.config.get("shop_settings", {})
            base_price = cfg_shop.get("base_price", 50)
            fluctuation = cfg_shop.get("price_fluctuation", 0.5)
            min_price = int(base_price * (1 - fluctuation))
            max_price = int(base_price * (1 + fluctuation))

            attribute_keys = self.config.get("initial_attributes", {}).keys()
            new_prices = {attr: random.randint(min_price, max_price) for attr in attribute_keys}

            self.shop_data = {
                "last_refresh_date": date.today().isoformat(),
                "remaining_purchases": cfg_shop.get("daily_purchase_limit", 10),
                "prices": new_prices
            }
        # 刷新是一个重要事件，立即保存一次数据
        await self._save_data()
        logger.info(f"商店刷新完成, 新价格: {new_prices}")


    async def initialize(self):
        """
        异步初始化。
        - 加载数据
        - 启动后台定时保存任务
        """
        await self._load_data()
        logger.info("数据加载完成。")

        # 启动后台定时保存任务
        self.save_task = asyncio.create_task(self._periodic_save())
        logger.info("后台定时保存任务已启动。")

        



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

            divider = "❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀"

            rp_calc_str = f"({base_rp} {f'x {multiplier:.2f}' if multiplier > 1 else ''})"

            reply = (
                f"{divider}\n"
                f"【喵星人品检测报告书】\n"
                f"⋆⋆⃕　品级：{grade}\n"
                f"⋆⋆⃕　人品值：{total_rp_gain} {rp_calc_str}\n"
                f"⋆⋆⃕　连续签到：{continuous_days} 天\n"
                f"⋆⋆⃕　当前总人品：{user['rp']}\n\n"
                f"❃✦⋆ 签 文 ⋆✦❃\n"
                f"{fortune}"
                f"{bonus_msg}\n"
                f"{divider}"
            )
            yield event.plain_result(reply)

    @filter.command("状态", alias={'我的状态', 'status'})
    async def show_status(self, event: AstrMessageEvent):
        """显示用户的当前状态面板。"""
        user_id = event.get_sender_id()

        async with self.data_lock:
            if user_id not in self.user_data:
                yield event.plain_result("你还没有签到过，没有状态信息哦。请先使用 /jrrp 进行签到。")
                return

            user = self.user_data[user_id]
            attrs = user["attributes"]
            check_in = user["check_in"]

            # 1. 调用 utils 中的函数进行计算
            energy_val = utils.calculate_energy_level(attrs, self.config.get("level_formula", {}))
            energy_rank = utils.get_energy_rank(energy_val, self.config.get("level_ranks", []))
            derivatives = utils.calculate_derivatives(attrs)

            # 2. 格式化输出
            divider = "--- ❀ 个人状态 ❀ ---"
            reply = (
                f"\n{divider}\n"
                f"💪 力量: {attrs.get('strength', 0):.1f}\n"
                f"🏃 敏捷: {attrs.get('agility', 0):.1f}\n"
                f"❤️ 体力: {attrs.get('stamina', 0):.1f}\n"
                f"🧠 智力: {attrs.get('intelligence', 0):.1f}\n"
                f"✨ 魅力: {attrs.get('charisma', 0):.1f}\n"
                f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                f"🩸 生命值: {derivatives['hp']}\n"
                f"⚜️ 能级: {energy_val:.2f} ({energy_rank})\n"
                f"💥 暴击率: {derivatives['crit_rate']:.2%}\n"
                f"🍃 闪避率: {derivatives['dodge_rate']:.2%}\n"
                f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                f"💰 剩余人品: {user.get('rp', 0)}\n"
                f"📅 连续签到: {check_in.get('continuous_days', 0)} 天"
            )
            yield event.plain_result(reply)


    @filter.command("商店", alias={'shop'})
    async def show_shop(self, event: AstrMessageEvent):
        """显示当日商店的商品价格和剩余购买次数。"""
        # 刷新商店
        if self.shop_data.get("last_refresh_date") != date.today().isoformat():
            await self._refresh_shop()

        user_id = event.get_sender_id()
        prices = self.shop_data.get("prices", {})

        # 找到最低价，用于高亮
        min_price = min(prices.values()) if prices else 0

        shop_items_str = []
        item_icons = {
            "strength": "💪", 
            "agility": "⚡", 
            "stamina": "❤️", 
            "intelligence": "🧠", 
            "charisma": "✨"
        }
        item_name_cn = {
            "strength":"力量", 
            "agility":"敏捷", 
            "stamina":"体力", 
            "intelligence":"智力", 
            "charisma":"魅力"
        }
        
        for item, price in prices.items():
            icon = item_icons.get(item, "🎁")
            name = item_name_cn.get(item, "未知")
            # 为特惠商品添加特殊标记和颜色提示
            if price == min_price:
                shop_items_str.append(f"   {icon} {name} - {price} (特惠!)")
            else:
                shop_items_str.append(f"   {icon} {name} - {price}")

        # 获取用户人品，对新用户做兼容
        user_rp = self.user_data.get(user_id, {}).get("rp", 0)
        # 根据人品值添加不同的表情
        rp_emoji = "💯" if user_rp >= 80 else "👍" if user_rp >= 60 else "😐" if user_rp >= 30 else "⚠️"

        # 构建更美观的回复
        daily_limit = self.config.get('shop_settings', {}).get('daily_purchase_limit', 10)
        remaining = self.shop_data.get('remaining_purchases', 0)
        
        # 使用不同的分隔线和表情符号增强视觉效果
        reply = (
            "\n📦 今日商店 📦\n"
            "==================\n"
            f"{'\n'.join(shop_items_str)}\n"
            "==================\n"
            f"🎯 剩余总购买次数: {remaining}/{daily_limit}\n"
            f"😉 你的人品值: {user_rp} {rp_emoji}\n"
            "💡 提示: 先到先得，机不可失失不再来~"
        )
        yield event.plain_result(reply)


    @filter.command("购买", alias={'buy'})
    async def buy_item(self, event: AstrMessageEvent, item_name: str, quantity: int = 1):
        """
        在商店中消耗人品购买属性。
        使用示例: /购买 力量 5  或  /购买 力量
        """
        user_id = event.get_sender_id()

        # --- 1. 输入校验 ---
        # 属性中文名到内部键名的映射
        attr_map = {"力量": "strength", "敏捷": "agility", "体力": "stamina", "智力": "intelligence", "魅力": "charisma"}
        if item_name not in attr_map:
            yield event.plain_result(f"喵~ 没有名为“{item_name}”的商品呢~ 可以购买的商品有：力量、敏捷、体力、智力、魅力哦~")
            return

        internal_attr_key = attr_map[item_name]

        if quantity <= 0:
            yield event.plain_result("购买数量必须是大于0的整数呀~ 请重新输入呢")
            return

        # --- 2. 懒刷新商店，确保价格最新 ---
        if self.shop_data.get("last_refresh_date") != date.today().isoformat():
            await self._refresh_shop()

        # --- 3. 核心购买逻辑与校验（加锁以保证原子性） ---
        async with self.data_lock:
            # 检查用户是否存在
            if user_id not in self.user_data:
                yield event.plain_result("你还没有签到过哦~ 无法购买商品呢。请先使用 /jrrp 签到吧喵~")
                return

            user = self.user_data[user_id]
            shop = self.shop_data

            single_price = shop.get("prices", {}).get(internal_attr_key)
            if not single_price:
                 yield event.plain_result("呜... 商店数据好像出了点问题，找不到这个商品的价格呢~")
                 return

            total_cost = single_price * quantity
            remaining_purchases = shop.get("remaining_purchases", 0)

            # 多重条件检查
            if quantity > remaining_purchases:
                yield event.plain_result(f"抱歉呀~ 你想购买 {quantity} 次，但商店今天只剩下 {remaining_purchases} 次购买机会了呢~")
                return

            if user['rp'] < total_cost:
                yield event.plain_result(f"人品不够啦~ 购买需要 {total_cost} 人品，但你现在只有 {user['rp']} 人品呢。再努力攒一攒吧喵~")
                return

            # --- 4. 执行交易 ---
            shop['remaining_purchases'] -= quantity
            user['rp'] -= total_cost

            attribute_increment = self.config.get("shop_settings", {}).get("attribute_increment", 0.1)
            total_increment = attribute_increment * quantity

            user['attributes'][internal_attr_key] += total_increment
            # 取一位小数避免精度问题
            user['attributes'][internal_attr_key] = round(user['attributes'][internal_attr_key], 1)

            new_attribute_value = user['attributes'][internal_attr_key]

        # --- 5. 立即保存数据 ---
        await self._save_data()

        # --- 6. 发送成功反馈 ---
        yield event.plain_result(
            f"\n✨ 购买成功啦！ ✨\n"
            f"-------------------\n"
            f"消耗人品：{total_cost}\n"
            f"剩余人品：{user['rp']}\n"
            f"当前{item_name}值：{new_attribute_value:.1f}({total_increment:.1f}↑)\n"
            f"-------------------\n"
            f"继续加油哦~ (≧∇≦)/"
        )

    @filter.command("test")
    async def test_set_rp(self, event: AstrMessageEvent, amount: int):
        """
        [测试指令] 直接设置自己的人品值。
        使用示例: /test 1000
        """
        user_id = event.get_sender_id()

        async with self.data_lock:
            # 检查用户是否存在，如果不存在则无法设置
            if user_id not in self.user_data:
                yield event.plain_result("无法设置人品：你还没有签到过，请先 /jrrp 创建角色。")
                return

            # 直接修改用户的人品值
            self.user_data[user_id]['rp'] = amount

        # 立即保存数据以确保测试结果生效
        await self._save_data()

        yield event.plain_result(f"✅ 测试指令执行成功：你的人品值已设置为 {amount}。")


    async def terminate(self):
        """
        插件卸载/停用时调用。
        - 取消后台任务
        - 执行最终的数据保存
        """
        if self.save_task:
            self.save_task.cancel()
            logger.info("后台定时保存任务已取消。")

        await self._save_data()
        logger.info("数据已成功保存。")
