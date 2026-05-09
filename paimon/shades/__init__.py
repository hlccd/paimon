"""四影 · 自进化提案管线（生 / 审 / 派 / 收）。

子模块：
- naberius/   生执 → propose_skill（凝练 skill 草案落 skill_proposals 域）
- jonova/     死执 → review_proposal（审提案质量，写 verdict + skill_proposals.review_verdict）
- istaroth/   时执 → archive 归档 + summary + propose 触发 hook + L1 记忆提取 + 上下文压缩

入口：
- 用户主动 `/evolve` 命令（paimon/core/commands/evolve.py）
- 时执 archive hook 自动判 should_propose 触发
- 三月 cron：月度扫近 30 天任务 / 周度清 30 天前 rejected 提案

落盘归冰神（paimon/skill_loader/apply_proposal.py）。
"""
