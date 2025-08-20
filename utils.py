from typing import Dict, List

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

def calculate_derivatives(attributes: Dict[str, float]) -> Dict:
    """计算衍生属性。"""
    strength = attributes.get("strength", 0)
    agility = attributes.get("agility", 0)
    stamina = attributes.get("stamina", 0)

    # 暴击率 = (力量+敏捷)×0.2%
    crit_rate = (strength + agility) * 0.002
    # 闪避率 = 敏捷×0.3%
    dodge_rate = agility * 0.003
    # 生命值 = 体力×10
    hp = stamina * 10

    # 应用上限
    crit_rate = min(crit_rate, 0.20) # 20%
    dodge_rate = min(dodge_rate, 0.15) # 15%

    return {
        "crit_rate": crit_rate,
        "dodge_rate": dodge_rate,
        "hp": int(hp)
    }
