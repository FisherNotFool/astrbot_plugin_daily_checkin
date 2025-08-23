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

def get_detailed_player_stats(user_data: Dict, presets: Dict, constants: Dict) -> Dict:
    """
    计算玩家最终详细属性的主函数。
    这是所有需要战斗属性的指令的唯一入口点。
    """
    # 1. 计算装备提供的总属性加成
    total_equip_bonus = _calculate_total_equipment_bonus(user_data, presets, constants)

    # 2. 计算最终五维属性
    base_attrs = user_data.get("attributes", {})
    final_core_attrs = {
        "S": base_attrs.get("strength", 0) + total_equip_bonus.get("S", 0),
        "T": base_attrs.get("stamina", 0) + total_equip_bonus.get("T", 0),
        "A": base_attrs.get("agility", 0) + total_equip_bonus.get("A", 0),
        "C": base_attrs.get("charisma", 0) + total_equip_bonus.get("C", 0),
        "I": base_attrs.get("intelligence", 0) + total_equip_bonus.get("I", 0)
    }

    # 3. 基于最终五维，计算基础衍生属性
    base_derivatives = _calculate_base_derivatives(final_core_attrs)

    # 4. 应用装备的百分比加成，得到最终衍生属性
    final_derivatives = {
        key: base_val * (1 + total_equip_bonus.get(f"{key}%", 0))
        for key, base_val in base_derivatives.items()
    }

    # 5. 组装成详细的、带过程的返回结果
    detailed_stats = {
        "strength": {"base": base_attrs.get("strength",0), "bonus": total_equip_bonus.get("S", 0), "final": final_core_attrs["S"]},
        "stamina": {"base": base_attrs.get("stamina",0), "bonus": total_equip_bonus.get("T", 0), "final": final_core_attrs["T"]},
        "agility": {"base": base_attrs.get("agility",0), "bonus": total_equip_bonus.get("A", 0), "final": final_core_attrs["A"]},
        "charisma": {"base": base_attrs.get("charisma",0), "bonus": total_equip_bonus.get("C", 0), "final": final_core_attrs["C"]},
        "intelligence": {"base": base_attrs.get("intelligence",0), "bonus": total_equip_bonus.get("I", 0), "final": final_core_attrs["I"]},
        "HP": {"base": base_derivatives["HP"], "bonus_percent": total_equip_bonus.get("HP%", 0), "final": final_derivatives["HP"]},
        "ATK": {"base": base_derivatives["ATK"], "bonus_percent": total_equip_bonus.get("ATK%", 0), "final": final_derivatives["ATK"]},
        "DEF": {"base": base_derivatives["DEF"], "bonus_percent": total_equip_bonus.get("DEF%", 0), "final": final_derivatives["DEF"]},
        "SPD": {"base": base_derivatives["SPD"], "bonus_percent": total_equip_bonus.get("SPD%", 0), "final": final_derivatives["SPD"]},
        "CRIT": {"base": base_derivatives["CRIT"], "bonus_percent": total_equip_bonus.get("CRIT%", 0), "final": final_derivatives["CRIT"]},
        "CRIT_MUL": {"base": base_derivatives["CRIT_MUL"], "bonus_percent": total_equip_bonus.get("CRIT_MUL%", 0), "final": final_derivatives["CRIT_MUL"]},
        "HIT": {"base": base_derivatives["HIT"], "bonus_percent": total_equip_bonus.get("HIT%", 0), "final": final_derivatives["HIT"]},
        "EVD": {"base": base_derivatives["EVD"], "bonus_percent": total_equip_bonus.get("EVD%", 0), "final": final_derivatives["EVD"]},
        "BLK": {"base": base_derivatives["BLK"], "bonus_percent": total_equip_bonus.get("BLK%", 0), "final": final_derivatives["BLK"]},
        "BLK_MUL": {"base": base_derivatives["BLK_MUL"], "bonus_percent": total_equip_bonus.get("BLK_MUL%", 0), "final": final_derivatives["BLK_MUL"]},
    }

    # 6. 计算能级和排名
    energy_value = calculate_energy_level(final_core_attrs, constants.get("level_formula", {}))
    energy_rank = get_energy_rank(energy_value, constants.get("level_ranks", []))

    # 7. 将能级信息也加入到返回的字典中
    detailed_stats["energy_level"] = {"value": energy_value, "rank": energy_rank}
    

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
