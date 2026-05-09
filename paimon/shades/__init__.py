"""四影 · 自进化提案管线（生执 / 死执 / 空执 / 时执）。

子模块：
- naberius/   生执 → 凝练 skill 草案；按用户反馈重写
- jonova/     死执 → 审草案质量并裁决（通过 / 要修 / 直拒）
- asmoday/    空执 → skill 域写入与管理（提案落盘 / 启动装载 / 声明注册）
- istaroth/   时执 → 自进化触发 + skill 热重载 + 自进化两个 cron

入口：
- 用户主动 `/evolve` 命令
- 时执自进化触发：对话每 5 条用户消息浅判
- 三月调度月度 cron / 周度 cron（dispatcher 是时执）

落盘归空执（paimon/shades/asmoday/apply_proposal.py）。
"""
