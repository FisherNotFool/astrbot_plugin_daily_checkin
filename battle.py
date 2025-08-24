import random
from typing import Dict, Tuple

MAX_TURNS = 30
K_CONSTANT = 100

def simulate_battle(p1_stats: Dict, p2_stats: Dict) -> Tuple[str, str]:
    """
    模拟两个玩家之间的战斗，返回胜利者名称和详细的战斗日志。
    此函数是PVP和未来PVE的核心，完全兼容。
    """
    # --- 初始化战斗 ---
    log = ["\n❀✧⋆✦ ⚔️ 战斗开始 ⚔️ ✦⋆✧❀"]
    p1_hp = p1_stats['HP']['final']
    p2_hp = p2_stats['HP']['final']

    # 步骤1: 速度判定先手
    if p1_stats['SPD']['final'] > p2_stats['SPD']['final']:
        attacker, defender = p1_stats, p2_stats
        attacker_hp, defender_hp = p1_hp, p2_hp
    elif p1_stats['SPD']['final'] < p2_stats['SPD']['final']:
        attacker, defender = p2_stats, p1_stats
        attacker_hp, defender_hp = p2_hp, p1_hp
    else:
        if random.randint(0, 100) <= 50:
            attacker, defender = p1_stats, p2_stats
            attacker_hp, defender_hp = p1_hp, p2_hp
        else:
            attacker, defender = p2_stats, p1_stats
            attacker_hp, defender_hp = p2_hp, p1_hp

    log.append(f"速度比拼：{attacker['name']} ({attacker['SPD']['final']:.1f}) vs {defender['name']} ({defender['SPD']['final']:.1f})\n")
    log.append(f"✨ 【{attacker['name']}】速度更快，获得先手！")

    turn_count = 1
    extra_turn_count = 0

    # --- 主战斗循环 ---
    while attacker_hp > 0 and defender_hp > 0 and turn_count <= MAX_TURNS:
        log.append(f"\n——— 回合 {turn_count}-追加 {extra_turn_count} ———")
        log.append(f"【{attacker['name']}】 [HP: {int(attacker_hp)}]  -> 【{defender['name']}】 [HP: {int(defender_hp)}]")

        # 步骤2: 命中判定 (使用0-1小数进行计算)
        hit_rate = max(min(attacker['HIT']['final'] - defender['EVD']['final'], 1.0), 0.05)
        if random.random() > hit_rate:
            log.append(f"🍃 【{attacker['name']}】的攻击被【{defender['name']}】闪避了！ (命中率: {hit_rate:.1%})")
        else:
            # 步骤3: 暴击判定与基础伤害
            is_crit = random.random() <= attacker['CRIT']['final']
            pre_damage = attacker['ATK']['final']
            if is_crit:
                pre_damage *= attacker['CRIT_MUL']['final']
                log.append(f"💥 【{attacker['name']}】打出了致命一击！ (暴击率: {attacker['CRIT']['final']:.1%})")

            # 步骤4-5: 格挡判定
            is_blocked = random.random() <= defender['BLK']['final']
            if is_blocked:
                pre_damage *= (1 - defender['BLK_MUL']['final'])
                log.append(f"🛡️ 【{defender['name']}】成功格挡了部分伤害！ (格挡率: {defender['BLK']['final']:.1%})")

            # 步骤6: 防御力结算最终伤害
            dr_def = min(defender['DEF']['final'] / (defender['DEF']['final'] + K_CONSTANT), 0.5) # 防御上限50%
            final_damage = max(pre_damage * (1 - dr_def), 1)
            defender_hp -= final_damage
            log.append(f"💔 【{defender['name']}】受到[{int(final_damage)}]点伤害，剩余HP: [{max(0, int(defender_hp))}]")

            if defender_hp <= 0:
                break # 战斗结束

        # 步骤7: 追加回合判定 (最大追加2次)
        if extra_turn_count < 2:
            base_add_rate = min((attacker['SPD']['final'] / (attacker['SPD']['final'] + defender['SPD']['final'])) * 0.25, 0.5)
            current_add_rate = base_add_rate * (0.5 ** extra_turn_count)
            if random.random() <= current_add_rate:
                extra_turn_count += 1
                log.append(f"⚡ 【{attacker['name']}】凭借速度优势触发了追加回合！ (第{extra_turn_count}次追加,追加概率{current_add_rate:.1%})")
                continue # 跳过回合交换，继续攻击

        # 步骤8: 切换攻击方
        attacker, defender = defender, attacker
        attacker_hp, defender_hp = defender_hp, attacker_hp
        turn_count += 1
        extra_turn_count = 0 # 重置追加回合计数

    # --- 战斗结束判定 ---
    winner = None
    if p1_stats['name'] == attacker['name']: p1_hp, p2_hp = attacker_hp, defender_hp
    else: p1_hp, p2_hp = defender_hp, attacker_hp

    if p1_hp <= 0: winner = p2_stats
    elif p2_hp <= 0: winner = p1_stats
    elif turn_count > MAX_TURNS:
        log.append(f"\n❀✧⋆✦ 回合达到上限({MAX_TURNS})，战斗强制结束 ✦⋆✧❀")
        p1_hp_percent = p1_hp / p1_stats['HP']['final']
        p2_hp_percent = p2_hp / p2_stats['HP']['final']
        if p1_hp_percent > p2_hp_percent: winner = p1_stats
        elif p2_hp_percent > p1_hp_percent: winner = p2_stats
        log.append(f"根据剩余血量百分比判定: 【{p1_stats['name']}】 ({p1_hp_percent:.1%}) vs 【{p2_stats['name']}】 ({p2_hp_percent:.1%})")

    if winner:
        log.append(f"\n👑 战斗结束，胜者是【{winner['name']}】！")
        return winner['name'], "\n".join(log)
    else:
        log.append(f"\n--- 🤝 战斗结束，双方平局！ ---")
        return "平局", "\n".join(log)
