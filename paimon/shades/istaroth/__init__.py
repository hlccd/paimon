"""时执 · Istaroth

职责：
  - 自进化触发：chat 累积浅判 should_propose（_propose_trigger）
  - skill 热重载：监听 skills/ 文件变化触发 reload（skill_watcher）
  - 自进化定时任务：周度清 rejected + 月度扫近 30 天会话（proposal_cron）

子模块：
- _propose_trigger.py —— 自进化触发器（chat 累积浅判 + run_propose_review_chain）
- skill_watcher.py    —— skill 文件热重载监听器
- proposal_cron.py    —— 自进化提案 cron（周度 prune + 月度扫描）
"""

