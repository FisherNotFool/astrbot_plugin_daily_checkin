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
from . import utils, battle


@register("daily_checkin", "FoolFish", "一个QQ群签到成长系统", "1.0.0")
class DailyCheckinPlugin(Star):
    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        # 将初始属性硬编码为类常量
        self.INITIAL_ATTRIBUTES = {
            "strength": 1.0, "agility": 1.0, "stamina": 1.0,
            "intelligence": 1.0, "charisma": 1.0
        }
        # 定义职业映射
        self.CLASS_MAP = {
            "1": "均衡使者", "均衡使者": "均衡使者",
            "2": "狂刃战士", "狂刃战士": "狂刃战士",
            "3": "磐石守卫", "磐石守卫": "磐石守卫",
            "4": "迅捷术师", "迅捷术师": "迅捷术师"
        }
        self.config = config
        plugin_data_dir = StarTools.get_data_dir("daily_checkin")
        self.user_data_path = plugin_data_dir / "user_data.json"
        self.shop_data_path = plugin_data_dir / "shop_data.json"

        self.user_data: Dict = {}
        self.shop_data: Dict = {}
        self.fortunes: Dict = {} # 存储签文
        self.game_constants: Dict = {}    # 存储游戏预设
        self.equipment_presets: Dict = {} # 存储装备预设

        self.data_lock = asyncio.Lock()
        self.save_task: Optional[asyncio.Task] = None # 用于存放后台保存任务

        # 加载所有静态数据文件
        try:
            current_dir = Path(__file__).parent
            with open(current_dir / "fortunes.json", 'r', encoding='utf-8') as f:
                self.fortunes = json.load(f)
            with open(current_dir / "game_constants.json", 'r', encoding='utf-8') as f:
                self.game_constants = json.load(f)
            with open(current_dir / "equipment_presets.json", 'r', encoding='utf-8') as f:
                self.equipment_presets = json.load(f)
            logger.info("所有静态数据 (fortunes, constants, presets) 加载成功。")
        except Exception as e:
            logger.error(f"加载静态数据文件时发生错误: {e}")

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
        """刷新商店的商品价格、购买次数以及抽奖券价格。"""
        async with self.data_lock:
            logger.info("开始每日刷新商店...")
            cfg_shop = self.config.get("shop_settings", {})

            # 刷新属性价格
            base_price = cfg_shop.get("base_price", 50)
            fluctuation = cfg_shop.get("price_fluctuation", 0.5)
            min_price = int(base_price * (1 - fluctuation))
            max_price = int(base_price * (1 + fluctuation))
            attribute_keys = self.INITIAL_ATTRIBUTES.keys()
            new_prices = {attr: random.randint(min_price, max_price) for attr in attribute_keys}

            # [新增] 刷新抽奖券价格
            ticket_base_price = cfg_shop.get("draw_ticket_base_price", 300)
            min_ticket_price = int(ticket_base_price * (1 - fluctuation))
            max_ticket_price = int(ticket_base_price * (1 + fluctuation))
            new_ticket_price = random.randint(min_ticket_price, max_ticket_price)

            self.shop_data = {
                "last_refresh_date": date.today().isoformat(),
                "remaining_purchases": cfg_shop.get("daily_purchase_limit", 10),
                "prices": new_prices,
                "draw_ticket_price": new_ticket_price
            }
        # 刷新是一个重要事件，立即保存一次数据
        await self._save_data()
        logger.info(f"商店刷新完成, 新价格: {new_prices}, 抽奖券价格: {new_ticket_price}")



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
                class_names = self.game_constants.get("class_bonus_multipliers", {}).keys()
                self.user_data[user_id] = {
                    "nickname": None,
                    "rp": 0,
                    "resources": {"enhancement_stones": 0, "draw_tickets": 0},
                    "attributes": self.INITIAL_ATTRIBUTES.copy(),
                    "check_in": {"continuous_days": 0, "last_date": ""},
                    "active_class": "均衡使者",
                    "equipment_sets": {class_name: {} for class_name in class_names}
                }
                # 提示新用户设置昵称
                yield event.plain_result("欢迎新朋友喵！已为你创建角色喵~请使用 `/设置昵称 [你的昵称]` 来完成注册哦喵！=￣ω￣=")


            user = self.user_data[user_id]
            check_in_info = user["check_in"]

            if check_in_info["last_date"] == today_str:
                yield event.plain_result("你今天已经签到过了，明天再来吧喵！")
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
            ticket_bonus_msg = ""
            attributes_to_update = []
            attribute_list = list(user["attributes"].keys())
            
            if base_rp == 100: attributes_to_update = random.sample(attribute_list, k=min(len(attribute_list), 5))
            elif base_rp in [1, 50]: attributes_to_update = random.sample(attribute_list, k=min(len(attribute_list), 2))
            elif base_rp in [33, 66, 88, 99]: attributes_to_update = random.sample(attribute_list, k=min(len(attribute_list), 1))

            if attributes_to_update:
                # 增加抽奖券
                user['resources']['draw_tickets'] += 1
                ticket_bonus_msg = "\n🎟️意外之喜！获得【抽奖券x1】"
                
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
                f"{ticket_bonus_msg}\n"
                f"{divider}"
            )
            yield event.plain_result(reply)
        await self._save_data()     #立即保存一次数据

    @filter.command("设置昵称", alias={'set_nickname'})
    async def set_nickname(self, event: AstrMessageEvent, nickname: str):
        """设置用户在机器人中的唯一昵称。"""
        user_id = event.get_sender_id()

        async with self.data_lock:
            if user_id not in self.user_data:
                yield event.plain_result("你还没有角色哦，请先使用 /jrrp 签到创建角色喵！")
                return

            # 检查昵称唯一性
            for uid, udata in self.user_data.items():
                if udata.get("nickname") == nickname and uid != user_id:
                    yield event.plain_result(f"抱歉喵＞﹏＜，昵称 “{nickname}” 已经被其他玩家占用了，换一个吧！")
                    return

            # 更新昵称
            self.user_data[user_id]['nickname'] = nickname

        await self._save_data() # 立即保存重要变更
        yield event.plain_result(f"昵称设置成功！你的昵称现在是 “{nickname}” 啦！")


    @filter.command("切换职业", alias={'set_class'})
    async def set_class(self, event: AstrMessageEvent, class_identifier: str):
        """切换当前激活的职业。"""
        user_id = event.get_sender_id()

        # 解析输入的职业标识符
        target_class = self.CLASS_MAP.get(class_identifier)

        if not target_class:
            yield event.plain_result(
                "\n无效的职业喵！(￣ε(#￣) 请输入职业全名或对应数字：\n"
                "1. 均衡使者\n"
                "2. 狂刃战士\n"
                "3. 磐石守卫\n"
                "4. 迅捷术师"
            )
            return

        async with self.data_lock:
            if user_id not in self.user_data:
                yield event.plain_result("你还没有角色哦，请先使用 /jrrp 签到创建角色喵！")
                return

            current_class = self.user_data[user_id].get('active_class')
            if current_class == target_class:
                yield event.plain_result(f"你当前职业已经是【{target_class}】了，无需切换喵！(○｀ 3′○)")
                return

            # 更新激活职业
            self.user_data[user_id]['active_class'] = target_class

        await self._save_data() # 立即保存重要变更
        yield event.plain_result(f"职业切换成功喵！当前职业：【{target_class}】！")



    @filter.command("状态", alias={'我的状态', 'status'})
    async def show_status(self, event: AstrMessageEvent):
        """显示用户全面的、包含装备和详细属性的状态面板。"""
        user_id = event.get_sender_id()

        async with self.data_lock:
            if user_id not in self.user_data:
                yield event.plain_result("你还没有签到过，没有状态信息哦。请先使用 /jrrp 进行签到。")
                return

            user = self.user_data[user_id]

            # 1. 调用核心引擎，获取所有最终计算数据
            stats = utils.get_detailed_player_stats(user, self.equipment_presets, self.game_constants, self.config)

            nickname = user.get("nickname", "尚未设置")
            divider = "❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀"

            # --- 2. 构建各大分栏 ---

            # 分栏1: 资源
            res = user.get("resources", {})
            res_lines = [
                f"💰 人品: {user.get('rp', 0)}",
                f"🎟️ 抽奖券: {res.get('draw_tickets', 0)}",
                f"💎 强化石: {res.get('enhancement_stones', 0)}",
                f"📅 连续签到: {user.get('check_in', {}).get('continuous_days', 0)} 天"
            ]
            resources_str = "\n".join(res_lines)

            # 分栏2: 职业与装备
            active_class = user.get("active_class", "未知")
            equipped_items = user.get("equipment_sets", {}).get(active_class, {})
            equip_lines = [f"⚜️ 职业: {active_class}"]
            slot_map_cn = {"head": "头部", "chest": "胸甲", "legs": "腿部", "feet": "脚部", "weapon": "武器"}
            for slot_key, slot_name_cn in slot_map_cn.items():
                item_info = equipped_items.get(slot_key)
                if item_info:
                    grade = item_info['grade']
                    level = item_info['success_count']
                    item_name = self.equipment_presets[active_class][slot_key]['names'][grade]
                    equip_lines.append(f"  {slot_name_cn}: {grade}-{item_name}(+{level})")
                else:
                    equip_lines.append(f"  {slot_name_cn}: 未装备")
            equipment_str = "\n".join(equip_lines)

            # 格式化函数，用于生成 "最终值 (+加成)" 的字符串
            def format_stat(stat_dict, is_percent=False):
                final = stat_dict['final']
                bonus = stat_dict.get('bonus', stat_dict.get('bonus_percent', 0))
                if is_percent:
                    return f"{final:.2%} (+{bonus:.2%})" if bonus else f"{final:.2%}"
                else:
                    return f"{final:.1f} (+{bonus:.1f})" if bonus else f"{final:.1f}"
                
            # 实现五维属性中文显示
            attr_chinese_name_map = {
                "strength": "力量",
                "agility": "敏捷",
                "stamina": "体力",
                "intelligence": "智力",
                "charisma": "魅力"
            }

            # 分栏3: 五维属性
            core_attrs_lines = []
            for key, emoji in [("strength", "💪"), ("agility", "🏃"), ("stamina", "❤️"), ("intelligence", "🧠"), ("charisma", "✨")]:
                s = stats[key]
                chinese_name = attr_chinese_name_map[key]
                bonus_str = f" (+{s['bonus']:.1f})" if s['bonus'] else ""
                core_attrs_lines.append(f"{emoji} {chinese_name}: {s['final']:.1f}{bonus_str}")
            core_attrs_str = "\n".join(core_attrs_lines)

            # 分栏4: 衍生属性与能级
            # 注意HP的格式化是整数
            derivatives_lines = []
            # (属性键, 中文名, emoji, 是否为纯百分比)
            attr_map = [
                ("HP", "生命值", "🩸", False), ("ATK", "攻击力", "💥", False), ("DEF", "防御力", "🛡️", False),
                ("SPD", "速度", "⚡", False), ("HIT", "命中率", "🎯", True), ("EVD", "闪避率", "🍃", True),
                ("CRIT", "暴击率", "💥", True), ("CRIT_MUL", "暴击倍率", "☠️", True),
                ("BLK", "格挡率", "🛡️", True), ("BLK_MUL", "格挡减伤", "🩹", True)
            ]
            for key, name, emoji, is_pure_percent in attr_map:
                s = stats[key]
                bonus_str = f" (+{s['bonus_percent']:.2%})" if s['bonus_percent'] else ""
                if is_pure_percent:
                    derivatives_lines.append(f"{emoji} {name}: {s['final']:.2%}{bonus_str}")
                else:
                    final_val = int(s['final']) if key == "HP" else f"{s['final']:.1f}"
                    derivatives_lines.append(f"{emoji} {name}: {final_val}{bonus_str}")

            energy = stats['energy_level']
            derivatives_lines.append(f"🔮 能级: {energy['value']:.2f} ({energy['rank']})")
            derivatives_str = "\n".join(derivatives_lines)

            # --- 3. 组装最终回复 ---
            reply = (
                f"\n--- 💠 {nickname}的状态报告 💠 ---\n"
                f"{resources_str}\n"
                f"{divider}\n"
                f"{equipment_str}\n"
                f"{divider}\n"
                f"{core_attrs_str}\n"
                f"{divider}\n"
                f"{derivatives_str}"
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
        draw_ticket_price = self.shop_data.get("draw_ticket_price", 300)

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
            "❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
            f"{'\n'.join(shop_items_str)}\n"
            f"   🎟️ 抽奖券 - {draw_ticket_price}\n"
            "❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
            f"🎯 剩余属性总购买次数: {remaining}/{daily_limit}\n"
            f"😉 你的人品值: {user_rp} {rp_emoji}\n"
            "💡 提示: 先到先得，机不可失失不再来~"
        )
        yield event.plain_result(reply)


    @filter.command("购买", alias={'buy'})
    async def buy_item(self, event: AstrMessageEvent, item_name: str, quantity: int = 1):
        """在商店中消耗人品购买属性或抽奖券。"""
        user_id = event.get_sender_id()

        if quantity <= 0:
            yield event.plain_result("购买数量必须是大于0的整数呀~ 请重新输入呢")
            return

        if self.shop_data.get("last_refresh_date") != date.today().isoformat():
            await self._refresh_shop()

        # [核心修正] 把所有 yield 和 return 的逻辑先放在 async with 块外面处理
        reply_message = None

        async with self.data_lock:
            if user_id not in self.user_data:
                reply_message = "你还没有签到过哦~ 无法购买。请先 /jrrp 签到吧喵~"
            else:
                user = self.user_data[user_id]
                shop = self.shop_data

                # --- 购买抽奖券 ---
                if item_name in ["抽奖券", "ticket"]:
                    ticket_price = shop.get("draw_ticket_price", 300)
                    total_cost = ticket_price * quantity
                    if user['rp'] < total_cost:
                        reply_message = f"人品不够啦~ 购买{quantity}张抽奖券需要 {total_cost} 人品，但你只有 {user['rp']} 人品喵。继续努力吧(ง •_•)ง"
                    else:
                        user['rp'] -= total_cost
                        user['resources']['draw_tickets'] += quantity
                        reply_message = (
                            f"\n✨ 购买成功啦！ ✨\n"
                            f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                            f"消耗人品：{total_cost}\n"
                            f"剩余人品：{user['rp']}\n"
                            f"当前抽奖券：{user['resources']['draw_tickets']} ({quantity}↑)\n"
                            f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                            f"继续加油喵~ (≧∇≦)/"
                        )

                # --- 购买属性 ---
                else:
                    attr_map = {"力量": "strength", "敏捷": "agility", "体力": "stamina", "智力": "intelligence", "魅力": "charisma"}
                    internal_attr_key = attr_map.get(item_name)
                    if not internal_attr_key:
                        reply_message = f"喵~ 没有名为“{item_name}”的商品呢~ 可以购买的商品有：力量、敏捷、体力、智力、魅力、抽奖券哦~"
                    else:
                        single_price = shop.get("prices", {}).get(internal_attr_key)
                        if not single_price:
                            reply_message = "呜... 商店数据好像出了点问题，找不到这个商品的价格呢~"
                        else:
                            total_cost = single_price * quantity
                            remaining_purchases = shop.get("remaining_purchases", 0)

                            if quantity > remaining_purchases:
                                reply_message = f"抱歉呀~ 你想购买 {quantity} 次，但商店今天只剩下 {remaining_purchases} 次购买机会了呢~"
                            elif user['rp'] < total_cost:
                                reply_message = f"人品不够啦~ 购买需要 {total_cost} 人品，但你现在只有 {user['rp']} 人品呢。继续努力吧(ง •_•)ง"
                            else:
                                shop['remaining_purchases'] -= quantity
                                user['rp'] -= total_cost
                                attribute_increment = self.config.get("shop_settings", {}).get("attribute_increment", 0.1)
                                total_increment = attribute_increment * quantity
                                user['attributes'][internal_attr_key] = round(user['attributes'][internal_attr_key] + total_increment, 1)
                                new_attribute_value = user['attributes'][internal_attr_key]
                                reply_message = (
                                    f"\n✨ 购买成功啦！ ✨\n"
                                    f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                                    f"消耗人品：{total_cost}\n"
                                    f"剩余人品：{user['rp']}\n"
                                    f"当前{item_name}值：{new_attribute_value:.1f} ({total_increment:.1f}↑)\n"
                                    f"剩余属性总购买次数：{shop['remaining_purchases']}次\n"
                                    f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                                    f"继续加油喵~ (≧∇≦)/"
                                )
        # 在 async with self.data_lock 块结束后，锁已经被释放了
        # 在这里调用 _save_data 是安全的
        await self._save_data()

        if reply_message:
            yield event.plain_result(reply_message)



    @filter.command("抽奖", alias={'draw'})
    async def draw_lottery(self, event: AstrMessageEvent, quantity: int = 1):
        """消耗抽奖券进行抽奖，支持批量。"""
        user_id = event.get_sender_id()
        if quantity <= 0:
            yield event.plain_result("抽奖次数必须是大于0的整数哦~")
            return

        async with self.data_lock:
            if user_id not in self.user_data:
                yield event.plain_result("你还没有角色呢，请先使用 /jrrp 创建角色喵！")
                return

            user = self.user_data[user_id]

            if user['resources']['draw_tickets'] < quantity:
                yield event.plain_result(f"你的抽奖券不足喵！想抽 {quantity} 次，但只有 {user['resources']['draw_tickets']} 张。快去商店购买喵ヾ(≧▽≦*)o")
                return

            user['resources']['draw_tickets'] -= quantity

            # [核心修正] 初始化 results 字典，用于存放所有类型的奖励
            results = {
                "rp": 0,
                "stone": 0,
                "equipment": [], # 使用列表存放获得的装备名
                "attribute_bonus": [] # 使用列表存放获得的属性点
            }

            for _ in range(quantity):
                # 抽奖逻辑 (保持不变)
                pool = [(("equipment",), 0.1), (("rp", 50, 200), 0.5), (("stone", 1, 1), 0.2), (("stone", 2, 2), 0.15), (("stone", 3, 3), 0.05)]
                rewards, weights = zip(*pool)
                chosen_reward = random.choices(rewards, weights=weights, k=1)[0]
                reward_type = chosen_reward[0]

                # 根据奖励类型发放奖励
                if reward_type == "rp":
                    rp_gain = random.randint(chosen_reward[1], chosen_reward[2])
                    user['rp'] += rp_gain
                    results['rp'] += rp_gain

                elif reward_type == "stone":
                    stone_gain = chosen_reward[1]
                    user['resources']['enhancement_stones'] += stone_gain
                    results['stone'] += stone_gain

                elif reward_type == "equipment":
                    # [核心修正] 将装备获取结果存入 results 字典，而不是临时变量
                    all_possible_items = [(cls, slt) for cls, slts in self.equipment_presets.items() for slt in slts.keys()]
                    user_owned_items = set((cls, slt) for cls, slts in user.get("equipment_sets", {}).items() for slt in slts.keys())
                    unowned_items = [item for item in all_possible_items if item not in user_owned_items]

                    if not unowned_items:
                        attr_keys = list(self.INITIAL_ATTRIBUTES.keys())
                        chosen_attr = random.choice(attr_keys)
                        user['attributes'][chosen_attr] = round(user['attributes'][chosen_attr] + 0.5, 1)
                        results['attribute_bonus'].append(f"⭐ 随机属性点: {chosen_attr.capitalize()} +0.5")
                    else:
                        active_class = user.get("active_class", "均衡使者")
                        preferred_unowned = [item for item in unowned_items if item[0] == active_class]
                        target_pool = preferred_unowned if random.random() < 0.5 and preferred_unowned else unowned_items
                        chosen_class, chosen_slot = random.choice(target_pool)
                        user['equipment_sets'][chosen_class][chosen_slot] = {"grade": "凡品", "success_count": 0}
                        item_name = self.equipment_presets[chosen_class][chosen_slot]["names"]["凡品"]
                        results['equipment'].append(f"🎊 【{item_name}】({chosen_class})")

            # --- [核心修正] 构建能展示所有奖励的最终报告 ---
            summary_lines = [f"\n✧⋆✦❃ 抽奖 {quantity} 次 报告 ❃✦⋆✧"]
            if results['rp'] > 0:
                summary_lines.append(f"💰 人品 + {results['rp']}")
            if results['stone'] > 0:
                summary_lines.append(f"💎 强化石 + {results['stone']}")
            if results['equipment']:
                summary_lines.extend(results['equipment'])
            if results['attribute_bonus']:
                summary_lines.extend(results['attribute_bonus'])

            if not any([results['rp'], results['stone'], results['equipment'], results['attribute_bonus']]):
                 summary_lines.append("💨 好像什么都没抽到...下次一定！")

            summary_lines.append("❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀")
            summary_lines.append(f"剩余抽奖券 🎟️: {user['resources']['draw_tickets']} ({quantity} ↓)")
            summary_lines.append(f"当前强化石 💎: {user['resources']['enhancement_stones']} ({results['stone']} ↑)")
            summary_lines.append(f"当前人品值 💰: {user['rp']} ({results['rp']} ↑)")
            reply_msg = "\n".join(summary_lines)

        await self._save_data()
        yield event.plain_result(reply_msg)

    @filter.command("强化", alias={'enhance'})
    async def enhance_item(self, event: AstrMessageEvent, slot_name: str):
        """消耗资源强化当前职业的指定槽位装备。"""
        user_id = event.get_sender_id()

        # 1. 输入校验
        slot_map = {"武器": "weapon", "头盔": "head", "胸甲": "chest", "腿甲": "legs", "脚部": "feet"}
        slot_key = slot_map.get(slot_name)
        if not slot_key:
            yield event.plain_result(f"无效的槽位名称喵！请输入以下槽位名称: {', '.join(slot_map.keys())}")
            return

        async with self.data_lock:
            # 2. 检查用户和装备是否存在
            if user_id not in self.user_data:
                yield event.plain_result("你还没有角色呢，请先使用 /jrrp 创建角色喵！")
                return

            user = self.user_data[user_id]
            active_class = user['active_class']
            item_info = user['equipment_sets'][active_class].get(slot_key)

            if not item_info:
                yield event.plain_result(f"你当前职业【{active_class}】还没有 [{slot_name}] 装备喵，快去抽奖获取喵(●'◡'●)！")
                return

            # 3. 计算消耗和成功率
            current_level = item_info['success_count']
            costs = utils.get_enhancement_costs(current_level)
            success_rate = utils.calculate_success_rate(current_level)

            # 4. 检查资源是否足够
            if user['resources']['enhancement_stones'] < costs['stones']:
                yield event.plain_result(f"【强化石】不足喵！需要[{costs['stones']}]颗，你只有[{user['resources']['enhancement_stones']}]颗喵。努力攒攒吧(✿◠‿◠)")
                return
            if user['rp'] < costs['rp']:
                yield event.plain_result(f"【人品】不足喵！需要[{costs['rp']}]点，你只有[{user['rp']}]点。")
                return

            # 5. 扣除资源 (无论成功失败都扣)
            user['resources']['enhancement_stones'] -= costs['stones']
            user['rp'] -= costs['rp']

            # 6. 进行强化判定
            roll = random.random()
            if roll <= success_rate:
                # --- 强化成功 ---
                item_info['success_count'] += 1
                new_level = item_info['success_count']
                grade_info = self.game_constants['grade_info'][item_info['grade']]
                upgrade_req = grade_info.get('upgrade_req')

                reply_msg =(       f"\n✨ 强化成功啦！ ✨\n"
                                    f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                                    f"💰 当前人品值：{user['rp']} ({costs['rp']} ↓)\n"
                                    f"💎 当前强化石：{user['resources']['enhancement_stones']} ({costs['stones']} ↓)\n"
                                    f"🔨 当前{slot_name}: +{new_level} (成功率: {success_rate:.1%})\n"
                                    f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                                    f"继续加油喵~ (≧∇≦)/")

                # 检查是否进阶
                if upgrade_req and new_level >= upgrade_req:
                    grade_order = list(self.game_constants['grade_info'].keys())
                    current_grade_index = grade_order.index(item_info['grade'])
                    if current_grade_index < len(grade_order) - 1:
                        new_grade = grade_order[current_grade_index + 1]
                        item_info['grade'] = new_grade
                        item_info['success_count'] = 0
                        item_name = self.equipment_presets[active_class][slot_key]['names'][new_grade]
                        reply_msg += f"\n🎉🎉🎉 恭喜！装备进阶为【{new_grade} - {item_name}】！强化等级已重置。"

            else:
                # --- 强化失败 ---
                reply_msg =(       f"\n🌧 强化失败喵... 🌧\n"
                                    f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                                    f"💰 当前人品值：{user['rp']} ({costs['rp']} ↓)\n"
                                    f"💎 当前强化石：{user['resources']['enhancement_stones']} ({costs['stones']} ↓)\n"
                                    f"❀✧⋆✦❃⋆❃✧❀✧❃⋆❃✦⋆✧❀\n"
                                    f"继续努力喵〒▽〒")

        await self._save_data()
        yield event.plain_result(reply_msg)

    @filter.command("PVP", alias={'挑战'})
    async def pvp_challenge(self, event: AstrMessageEvent, target_nickname: str):
        """向指定昵称的玩家发起挑战。"""
        challenger_id = event.get_sender_id()

        async with self.data_lock:
            # 1. 查找挑战者和被挑战者
            challenger_data = self.user_data.get(challenger_id)
            if not challenger_data or not challenger_data.get("nickname"):
                yield event.plain_result("你还没有设置昵称喵！请先使用 `/设置昵称` 来打响你的名号！")
                return

            challenger_nickname = challenger_data["nickname"]
            if challenger_nickname == target_nickname:
                yield event.plain_result("不能挑战自己哦喵！")
                return

            defender_id = None
            defender_data = None
            for uid, udata in self.user_data.items():
                if udata.get("nickname") == target_nickname:
                    defender_id = uid
                    defender_data = udata
                    break

            if not defender_data:
                yield event.plain_result(f"找不到名为 “{target_nickname}” 的玩家，是不是打错了喵？")
                return

            # 2. 为双方生成战斗属性
            challenger_stats = utils.get_detailed_player_stats(challenger_data, self.equipment_presets, self.game_constants, self.config)
            challenger_stats['name'] = challenger_nickname # 添加名字用于日志

            defender_stats = utils.get_detailed_player_stats(defender_data, self.equipment_presets, self.game_constants, self.config)
            defender_stats['name'] = target_nickname

            # 3. 调用战斗模拟器
            winner_name, battle_log = battle.simulate_battle(challenger_stats, defender_stats)

            # 4. 发送战报
            yield event.plain_result(battle_log)

    @filter.command("显示昵称", alias={'昵称列表'})
    async def show_all_nicknames(self, event: AstrMessageEvent):
        """显示所有已设置昵称的玩家列表。"""
        nicknames = []
        async with self.data_lock:
            # 遍历所有用户数据，收集已设置的昵称
            for user in self.user_data.values():
                nickname = user.get("nickname")
                if nickname: # 确保昵称不为None或空字符串
                    nicknames.append(nickname)

        if not nicknames:
            yield event.plain_result("目前还没有玩家设置昵称哦~")
            return

        # 格式化输出
        title = "--- 📝 玩家昵称列表 📝 ---"
        # 使用 enumerate 创建带编号的列表
        formatted_list = [f"{i+1}. {name}" for i, name in enumerate(nicknames)]

        reply_message = f"{title}\n" + "\n".join(formatted_list)

        yield event.plain_result(reply_message)


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
