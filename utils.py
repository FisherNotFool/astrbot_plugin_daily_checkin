import math
from typing import Dict, Any, List

def calculate_energy_level(attributes: Dict[str, float], formula_config: Dict) -> float:
    """根据属性和公式配置计算能级。"""
    linear_coeff = formula_config.get("linear_coefficient", 1.2)
    square_coeff = formula_config.get("square_coefficient", 0.04)

    sum_attrs = sum(attributes.values())
    sum_sq_attrs = sum(v**2 for v in attributes.values())

    level = sum_attrs * linear_coeff + sum_sq_attrs * square_coeff
    return round(level, 2)

def get_energy_rank(level: float, ranks_config: List[Dict]) -> str:
    """根据能级数值和等级配置表返回对应的能级。"""
    # ranks_config 应该是从高到低排序的
    for rank_info in ranks_config:
        if level >= rank_info.get("threshold", 0):
            return rank_info.get("rank", "Unknown")
    return "F" # 默认最低等级

def get_detailed_player_stats(user_data: Dict, presets: Dict, constants: Dict, config: Dict) -> Dict:
    """
    [修正版] 计算玩家最终详细属性的主函数。
    """
    # 1. 计算装备提供的总属性加成 (百分比形式)
    total_equip_bonus_percent = _calculate_total_equipment_bonus(user_data, presets, constants)

    # 2. 计算最终五维属性
    base_attrs = user_data.get("attributes", {})
    final_core_attrs = {}
    core_bonus_values = {} # 存储实际加成数值
    for key_upper, key_lower in {"S": "strength", "T": "stamina", "A": "agility", "C": "charisma", "I": "intelligence"}.items():
        base_val = base_attrs.get(key_lower, 0)
        bonus_percent = total_equip_bonus_percent.get(key_upper, 0)
        # [核心修正] 计算实际加成值
        bonus_val = base_val * bonus_percent
        final_core_attrs[key_upper] = base_val + bonus_val
        core_bonus_values[key_upper] = bonus_val

    # 3. 计算基础衍生属性
    base_derivatives = _calculate_base_derivatives(final_core_attrs)

    # 4. 应用装备百分比加成，得到最终衍生属性
    final_derivatives = {
        key: base_val * (1 + total_equip_bonus_percent.get(f"{key}%", 0))
        for key, base_val in base_derivatives.items()
    }

    # [核心修正] 能级计算现在从 config 读取配置
    energy_value = calculate_energy_level(final_core_attrs, config.get("level_formula", {}))
    energy_rank = get_energy_rank(energy_value, config.get("level_ranks", []))

    # 5. 组装返回结果
    detailed_stats = {
        "strength": {"base": base_attrs.get("strength",0), "bonus": core_bonus_values.get("S", 0), "final": final_core_attrs["S"]},
        "stamina": {"base": base_attrs.get("stamina",0), "bonus": core_bonus_values.get("T", 0), "final": final_core_attrs["T"]},
        "agility": {"base": base_attrs.get("agility",0), "bonus": core_bonus_values.get("A", 0), "final": final_core_attrs["A"]},
        "charisma": {"base": base_attrs.get("charisma",0), "bonus": core_bonus_values.get("C", 0), "final": final_core_attrs["C"]},
        "intelligence": {"base": base_attrs.get("intelligence",0), "bonus": core_bonus_values.get("I", 0), "final": final_core_attrs["I"]},
        "HP": {"base": base_derivatives["HP"], "bonus_percent": total_equip_bonus_percent.get("HP%", 0), "final": final_derivatives["HP"]},
        "ATK": {"base": base_derivatives["ATK"], "bonus_percent": total_equip_bonus_percent.get("ATK%", 0), "final": final_derivatives["ATK"]},
        "DEF": {"base": base_derivatives["DEF"], "bonus_percent": total_equip_bonus_percent.get("DEF%", 0), "final": final_derivatives["DEF"]},
        "SPD": {"base": base_derivatives["SPD"], "bonus_percent": total_equip_bonus_percent.get("SPD%", 0), "final": final_derivatives["SPD"]},
        "CRIT": {"base": base_derivatives["CRIT"], "bonus_percent": total_equip_bonus_percent.get("CRIT%", 0), "final": final_derivatives["CRIT"]},
        "CRIT_MUL": {"base": base_derivatives["CRIT_MUL"], "bonus_percent": total_equip_bonus_percent.get("CRIT_MUL%", 0), "final": final_derivatives["CRIT_MUL"]},
        "HIT": {"base": base_derivatives["HIT"], "bonus_percent": total_equip_bonus_percent.get("HIT%", 0), "final": final_derivatives["HIT"]},
        "EVD": {"base": base_derivatives["EVD"], "bonus_percent": total_equip_bonus_percent.get("EVD%", 0), "final": final_derivatives["EVD"]},
        "BLK": {"base": base_derivatives["BLK"], "bonus_percent": total_equip_bonus_percent.get("BLK%", 0), "final": final_derivatives["BLK"]},
        "BLK_MUL": {"base": base_derivatives["BLK_MUL"], "bonus_percent": total_equip_bonus_percent.get("BLK_MUL%", 0), "final": final_derivatives["BLK_MUL"]},
        "energy_level": {"value": energy_value, "rank": energy_rank}
    }
    return detailed_stats



def _calculate_total_equipment_bonus(user_data: Dict, presets: Dict, constants: Dict) -> Dict:
    """计算用户当前激活职业下，所有已穿戴装备提供的属性总和。"""
    active_class = user_data.get("active_class", "均衡使者")
    equipped_items = user_data.get("equipment_sets", {}).get(active_class, {})
    total_bonus = {}

    for slot, item_info in equipped_items.items():
        item_bonus = _calculate_single_item_stats(item_info, active_class, slot, presets, constants)
        for stat, value in item_bonus.items():
            total_bonus[stat] = total_bonus.get(stat, 0) + value

    return total_bonus


def _calculate_single_item_stats(item_info: Dict, class_name: str, slot: str, presets: Dict, constants: Dict) -> Dict:
    """计算单件装备在特定职业下的最终属性加成。"""
    grade = item_info.get("grade", "凡品")
    success_count = item_info.get("success_count", 0)

    # 获取装备的神品基础属性、品级系数、职业加成系数
    godly_stats = presets.get(class_name, {}).get(slot, {}).get("base_stats_godly", {})
    grade_coefficient = constants.get("grade_info", {}).get(grade, {}).get("coefficient", 0.1)
    class_multipliers = constants.get("class_bonus_multipliers", {}).get(class_name, {})
    k = constants.get("enhancement_k_values", {}).get(grade, 0.05)

    item_final_stats = {}
    for stat, godly_value in godly_stats.items():
        # 1. 计算当前品级的属性上限
        class_multiplier = class_multipliers.get(stat, 0.5)
        grade_cap = godly_value * grade_coefficient * class_multiplier

        # 2. 计算初始加成（0强）
        current_bonus = grade_cap * 0.30

        # 3. 模拟强化过程，累加非线性收益
        for _ in range(success_count):
            delta = (grade_cap - current_bonus) * k
            current_bonus += delta

        item_final_stats[stat] = current_bonus

    return item_final_stats


def _calculate_base_derivatives(core_attrs: Dict) -> Dict:
    """根据最终五维，计算所有基础衍生属性（应用你的最新公式）。"""
    S = core_attrs.get("S", 0)
    T = core_attrs.get("T", 0)
    A = core_attrs.get("A", 0)
    C = core_attrs.get("C", 0)
    I = core_attrs.get("I", 0)

    # 使用 safe_div 避免除以零的错误
    def safe_div(numerator, denominator):
        return numerator / denominator if denominator != 0 else 0

    derivatives = {}
    derivatives["HP"] = 50 * T + 20 * S + 10 * I
    derivatives["ATK"] = 8 * S + 3 * A + 0.5 * I
    derivatives["DEF"] = 5 * T + 2 * S + math.sqrt(A) if A > 0 else 5 * T + 2 * S
    derivatives["SPD"] = 3 * A + 0.5 * I + 0.2 * C
    derivatives["CRIT"] = (15 * (1 - math.exp(-0.03 * A)) + 5 * safe_div(C, C + 50)) / 100
    derivatives["CRIT_MUL"] = min(1.5 + 0.015 * S + 0.01 * min(C, 50), 2.5)
    derivatives["HIT"] = (80 + 15 * safe_div(I, I + 30) + 5 * safe_div(A, A + 100)) / 100
    derivatives["EVD"] = (15 * (1 - math.exp(-0.03 * A)) + 5 * safe_div(T, T + 100)) / 100
    derivatives["BLK"] = (20 * safe_div(T, T + 50) + 5 * safe_div(S, S + 100)) / 100
    derivatives["BLK_MUL"] = 0.1 + 0.14 * safe_div(T, T + 40) + 0.06 * safe_div(S, S + 60)

    # 将概率值（如暴击率）转换为 0-1 的小数，便于后续计算
    return derivatives

def get_enhancement_costs(enhancement_level: int) -> Dict[str, int]:
    """根据当前强化等级计算消耗的强化石和人品值。"""
    n = enhancement_level

    # 计算强化石消耗
    if n <= 5:
        stone_cost = 1
    elif 5 < n <= 10:
        stone_cost = 2
    elif 10 < n <= 20:
        stone_cost = 3
    elif 20 < n <= 25:
        stone_cost = 4
    else: # n > 25
        stone_cost = 5

    # 计算人品消耗
    if n <= 10:
        rp_cost = 50 + 5 * n
    elif 10 < n <= 20:
        rp_cost = 100 + 150 * (1 - math.exp(-0.3 * (n - 10)))
    else:  # n > 20
        rp_cost = 500 - 257.5 * math.exp(-0.1 * (n - 20))

    return {"stones": stone_cost, "rp": int(rp_cost)}

def calculate_success_rate(enhancement_level: int) -> float:
    """根据当前强化等级计算成功率。"""
    n = enhancement_level
    if n <= 20:
        # 线性衰减：从90%到40%
        return 0.9 - (0.5 * n / 20)
    else:
        # 指数衰减：从40%收敛到10%
        return 0.1 + 0.3 * math.exp(-0.15 * (n - 20))

def calculate_boss_stats(boss_name: str, base_five_stats: Dict) -> Dict:
    """
    根据Boss的基础五维和专属公式，生成一个兼容战斗引擎的属性块。
    """
    S = base_five_stats.get("S", 0)
    T = base_five_stats.get("T", 0)
    A = base_five_stats.get("A", 0)
    C = base_five_stats.get("C", 0)
    I = base_five_stats.get("I", 0)

    def safe_div(numerator, denominator):
        return numerator / denominator if denominator != 0 else 0

    # 计算衍生属性
    derivatives = {
        "HP": 500 * T + 100 * S + 50 * I,
        "ATK": 4 * S + A + 0.2 * I,
        "DEF": 10 * T + 5 * S + 2 * (math.sqrt(A) if A > 0 else 0),
        "SPD": 0.5 * A + 0.1 * I,
        "CRIT": (5 + 10 * safe_div(I, I + 100)) / 100,
        "CRIT_MUL": 1.5 + 0.005 * S,
        "HIT": (90 + 5 * safe_div(I, I + 200)) / 100,
        "EVD": (2 + 5 * safe_div(A, A + 200)) / 100,
        "BLK": (30 * safe_div(T, T + 80) + 10 * safe_div(S, S + 150)) / 100,
        "BLK_MUL": 0.2 + 0.25 * safe_div(T, T + 100)
    }

    # 组装成兼容 simulate_battle 的格式
    battle_ready_stats = {"name": boss_name}
    for key, value in derivatives.items():
        battle_ready_stats[key] = {"final": value}

    return battle_ready_stats
