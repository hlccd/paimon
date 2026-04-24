#!/usr/bin/env python3
"""
通用评分模块 - 适用于所有股票的基准评分逻辑

评分体系（100分）：
- 股息维度 (35分): 当前股息率 + 分红稳定性
- 估值维度 (25分): 根据行业特征差异化评估
- 质量维度 (20分): 市值规模 + 分红实施状态 + 分红率合理性
- 财务维度 (10分): ROE + 利润增长 + 负债率（通用标准）
- 成长维度 (10分): 分红持续性 + 股息率趋势
"""

from datetime import datetime


class UniversalScorer:
    """通用评分器 - 基准版本"""

    @staticmethod
    def score_stock(stock_data, classification, financial_data=None):
        """
        多维度评分 - 行业差异化 + 财务指标

        Args:
            stock_data: 股票基础数据（包含股息、估值、市值等）
            classification: 行业分类信息（来自base.classify_stock）
            financial_data: 财务数据（ROE、利润增长率、负债率等，可选）

        Returns:
            dict: 各维度得分 {'dividend': X, 'valuation': Y, 'quality': Z, 'growth': W, 'financial': V}
        """
        score = {'dividend': 0, 'valuation': 0, 'quality': 0, 'growth': 0, 'financial': 0}

        dy = stock_data['dividend_yield']
        history = stock_data['history_count']
        pe = stock_data.get('pe', 0)
        pb = stock_data.get('pb', 0)
        mcap = stock_data.get('market_cap', 0)
        payout = stock_data.get('payout_ratio', 0)

        # ============================================================
        # 1. 股息维度 (35分，降低5分给财务)
        # ============================================================
        # 当前股息率（22分）
        if dy >= 0.08: score['dividend'] += 22      # 超高股息
        elif dy >= 0.06: score['dividend'] += 19    # 高股息
        elif dy >= 0.05: score['dividend'] += 15    # 良好
        elif dy >= 0.04: score['dividend'] += 10    # 中等
        else: score['dividend'] += 5                 # 偏低

        # 分红稳定性（13分）- 连续性
        if history >= 15: score['dividend'] += 13   # 超稳定
        elif history >= 10: score['dividend'] += 10 # 稳定
        elif history >= 7: score['dividend'] += 6   # 较稳定
        else: score['dividend'] += 3                 # 一般

        # ============================================================
        # 2. 估值维度 (25分，降低5分给财务) - 行业差异化
        # ============================================================
        metric = classification.get('valuation_metric', 'PE')

        if metric == "PB":  # 银行
            if pb > 0:
                if pb < 0.7:
                    score['valuation'] += 23  # 深度低估
                elif pb < 0.9:
                    score['valuation'] += 19  # 低估
                elif pb < 1.1:
                    score['valuation'] += 13  # 合理
                elif pb < 1.3:
                    score['valuation'] += 8   # 略高
                else:
                    score['valuation'] += 4   # 高估

        elif metric == "PE":  # 公用事业、高速公路、交通运输
            if pe > 0:
                if pe < 10:
                    score['valuation'] += 21  # 低估
                elif pe < 12:
                    score['valuation'] += 17  # 合理偏低
                elif pe < 15:
                    score['valuation'] += 12  # 合理
                elif pe < 18:
                    score['valuation'] += 8   # 略高
                else:
                    score['valuation'] += 4   # 高估
            # PB 辅助（防御性行业 PB < 2 加分）
            if pb > 0 and pb < 2.0:
                score['valuation'] += 4

        elif metric == "PEG":  # 消费、医药（成长型）
            # 简化：因为没有增长率数据，用 PE + 股息率综合评估
            if pe > 0 and pe < 20:
                score['valuation'] += 15
            elif pe > 0 and pe < 30:
                score['valuation'] += 10
            # 高股息补偿高 PE
            if dy >= 0.05:
                score['valuation'] += 6
            elif dy >= 0.04:
                score['valuation'] += 4

        elif metric == "PE_ROE":  # 制造业
            # 简化：优先看 PE，ROE 数据缺失时用分红率替代
            if pe > 0:
                if pe < 10:
                    score['valuation'] += 17
                elif pe < 15:
                    score['valuation'] += 12
                elif pe < 20:
                    score['valuation'] += 8
            # 用分红率替代 ROE（分红率高说明盈利稳定）
            if payout >= 0.4:
                score['valuation'] += 8
            elif payout >= 0.3:
                score['valuation'] += 4

        elif metric == "PB_DEBT":  # 房地产、周期股
            if pb > 0:
                if pb < 0.8:
                    score['valuation'] += 15  # 破净
                elif pb < 1.0:
                    score['valuation'] += 12  # 接近破净
                elif pb < 1.2:
                    score['valuation'] += 8   # 合理
                else:
                    score['valuation'] += 4   # 高估
            # 周期股惩罚（市场高点时风险大）
            if classification['is_cyclical']:
                score['valuation'] -= 4

        else:
            # 默认通用估值（PE + PB 综合）
            if pe > 0 and pe < 15:
                score['valuation'] += 12
            elif pe > 0 and pe < 25:
                score['valuation'] += 8
            if pb > 0 and pb < 2.0:
                score['valuation'] += 8
            elif pb > 0 and pb < 3.0:
                score['valuation'] += 4

        # ============================================================
        # 3. 质量维度 (20分)
        # ============================================================
        # 市值规模（10分）- 聚焦超大盘股
        if mcap > 200_000_000_000:   # > 2000亿（超大盘）
            score['quality'] += 10
        elif mcap > 100_000_000_000: # > 1000亿（大盘）
            score['quality'] += 8
        elif mcap > 50_000_000_000:  # > 500亿（中大盘）
            score['quality'] += 6
        else:                         # > 300亿（门槛）
            score['quality'] += 3

        # 分红实施状态（5分）
        status = stock_data.get('status', '')
        if status in ['实施', '已实施']:
            score['quality'] += 5
        elif status in ['股东大会通过', '董事会预案']:
            score['quality'] += 3

        # 分红率合理性（5分）- 30%-70% 最健康
        if 0.35 <= payout <= 0.65:
            score['quality'] += 5  # 最佳区间
        elif 0.25 <= payout <= 0.75:
            score['quality'] += 3  # 合理区间
        elif payout > 0:
            score['quality'] += 1  # 至少有分红

        # ============================================================
        # 4. 财务维度 (10分) - 通用标准
        # ============================================================
        if financial_data:
            roe = financial_data.get('roe')
            profit_growth = financial_data.get('profit_growth')
            debt_ratio = financial_data.get('debt_ratio')

            # ROE 评分（5分）- 通用标准
            if roe is not None:
                if roe >= 15: score['financial'] += 5    # 优秀
                elif roe >= 12: score['financial'] += 4  # 良好
                elif roe >= 10: score['financial'] += 3  # 中等
                elif roe >= 8: score['financial'] += 2   # 一般
                else: score['financial'] += 1            # 偏低

            # 成长性评分（3分）- 通用标准
            if profit_growth is not None:
                if profit_growth >= 15: score['financial'] += 3      # 高增长
                elif profit_growth >= 10: score['financial'] += 2.5  # 良好增长
                elif profit_growth >= 5: score['financial'] += 2     # 稳定增长
                elif profit_growth >= 0: score['financial'] += 1     # 微增长
                # 负增长不扣分（周期股常见）

            # 负债风险评分（2分）- 通用标准
            if debt_ratio is not None:
                if debt_ratio < 50: score['financial'] += 2      # 低杠杆
                elif debt_ratio < 65: score['financial'] += 1.5  # 中等杠杆
                elif debt_ratio < 80: score['financial'] += 1    # 较高杠杆
                # >= 80% 不扣分，只是0分

        # ============================================================
        # 5. 成长维度 (10分)
        # ============================================================
        # 分红持续性（6分）
        if history >= 15:
            score['growth'] += 6
        elif history >= 10:
            score['growth'] += 4
        elif history >= 7:
            score['growth'] += 2

        # 股息率趋势（4分）- 高股息说明盈利增长或分红提升
        if dy >= 0.06:
            score['growth'] += 4  # 高股息通常意味着盈利稳定
        elif dy >= 0.04:
            score['growth'] += 2

        return score

    @staticmethod
    def build_reasons(stock_data, score, classification, financial_data=None):
        """
        生成评分理由（行业差异化 + 财务指标）

        Returns:
            list[str]: 评分理由列表
        """
        reasons = []
        dy = stock_data['dividend_yield']
        pe = stock_data.get('pe', 0)
        pb = stock_data.get('pb', 0)
        history = stock_data['history_count']
        payout = stock_data.get('payout_ratio', 0)
        mcap_yi = stock_data.get('market_cap', 0) / 100_000_000
        metric = classification.get('valuation_metric', 'PE')
        recent_count = stock_data.get('recent_dividend_count', 1)

        # 股息维度理由（显示年化+最近分红次数）
        dy_level = "超高" if dy >= 0.08 else "高" if dy >= 0.06 else "良好" if dy >= 0.05 else "中等"
        stability = "超稳定" if history >= 15 else "稳定" if history >= 10 else "较稳定"
        dividend_note = f"近12月{recent_count}次" if recent_count > 1 else "年度分红"
        reasons.append(f"[股息 {score['dividend']:.0f}/35] {dy_level}年化股息率 {dy*100:.1f}%（{dividend_note}），{stability}（累计{history}次）")

        # 估值维度理由（根据行业类型）
        if metric == "PB":  # 银行
            pb_level = "深度低估" if pb < 0.7 else "低估" if pb < 0.9 else "合理" if pb < 1.1 else "略高"
            reasons.append(f"[估值 {score['valuation']:.0f}/25] 银行股看PB，当前 {pb:.2f}（{pb_level}），PE={pe:.1f}")
        elif metric == "PE":  # 公用事业
            pe_level = "低估" if pe < 10 else "合理偏低" if pe < 12 else "合理" if pe < 15 else "略高"
            reasons.append(f"[估值 {score['valuation']:.0f}/25] 防御性行业看PE，当前 {pe:.1f}（{pe_level}），PB={pb:.2f}")
        elif metric == "PEG":  # 消费/医药
            reasons.append(f"[估值 {score['valuation']:.0f}/25] 成长型行业，PE={pe:.1f}，高股息补偿估值")
        elif metric == "PE_ROE":  # 制造业
            reasons.append(f"[估值 {score['valuation']:.0f}/25] 制造业看PE+盈利，PE={pe:.1f}，分红率{payout*100:.0f}%")
        elif metric == "PB_DEBT":  # 周期股
            pb_status = "破净" if pb < 1.0 else "接近破净" if pb < 1.2 else "合理"
            reasons.append(f"[估值 {score['valuation']:.0f}/25] 周期股看PB，{pb:.2f}（{pb_status}），⚠️ 需关注景气度")
        else:
            reasons.append(f"[估值 {score['valuation']:.0f}/25] PE={pe:.1f}，PB={pb:.2f}")

        # 质量维度理由
        scale = "超大盘" if mcap_yi > 2000 else "大盘" if mcap_yi > 1000 else "中大盘" if mcap_yi > 500 else "中盘"
        status = stock_data.get('status', '')
        status_text = f"，{status}" if status in ['实施', '已实施', '股东大会通过'] else ""
        reasons.append(f"[质量 {score['quality']:.0f}/20] {scale}股（{mcap_yi:.0f}亿），分红率{payout*100:.0f}%{status_text}")

        # 财务维度理由（新增）
        if financial_data and score['financial'] > 0:
            roe = financial_data.get('roe')
            profit_growth = financial_data.get('profit_growth')
            debt_ratio = financial_data.get('debt_ratio')

            financial_parts = []
            if roe is not None:
                roe_level = "优秀" if roe >= 15 else "良好" if roe >= 12 else "中等" if roe >= 10 else "偏低"
                financial_parts.append(f"ROE {roe:.1f}%（{roe_level}）")
            if profit_growth is not None:
                growth_level = "高增长" if profit_growth >= 15 else "稳增" if profit_growth >= 5 else "微增" if profit_growth >= 0 else "负增长"
                financial_parts.append(f"利润增长 {profit_growth:.1f}%（{growth_level}）")
            if debt_ratio is not None:
                debt_level = "低" if debt_ratio < 50 else "中" if debt_ratio < 65 else "高"
                financial_parts.append(f"负债率 {debt_ratio:.1f}%（{debt_level}）")

            if financial_parts:
                reasons.append(f"[财务 {score['financial']:.1f}/10] {' | '.join(financial_parts)}")
        else:
            reasons.append(f"[财务 0/10] 财务数据缺失")

        # 成长维度理由
        growth_text = "长期稳定分红" if history >= 15 else "持续分红多年" if history >= 10 else "分红记录良好"
        reasons.append(f"[成长 {score['growth']:.0f}/10] {growth_text}，股息表现优异")

        # 特别提示
        if classification['is_cyclical']:
            reasons.append("⚠️ 周期股：当前PB较低可能是行业底部信号，但需关注景气度变化")
        if classification['is_defensive']:
            reasons.append("✅ 防御性行业：适合长期配置，波动较小")

        return reasons

    @staticmethod
    def format_report(results, top_n):
        """
        格式化输出报告

        Args:
            results: 候选股票列表（已排序）
            top_n: 显示前N名

        Returns:
            str: 格式化的报告文本
        """
        lines = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M')

        lines.append(f"\n🔍 红利股扫描报告（{now}）")
        lines.append("━" * 55)

        lines.append(f"\n🏆 TOP {top_n} 推荐（按综合评分排序）\n")

        for i, stock in enumerate(results[:top_n], 1):
            sd = stock['stock_data']
            sc = stock['score']
            total = sum(sc.values())
            stars = '★' * (int(total) // 18) + '☆' * (5 - int(total) // 18)
            industry = sd['industry']

            tag = '⚠️' if stock['classification']['is_cyclical'] else '🏭'
            cycle_note = '（周期股）' if stock['classification']['is_cyclical'] else ''

            recent_count = sd.get('recent_dividend_count', 1)
            dividend_text = f"年化{sd['dividend_yield']*100:.1f}%（近12月{recent_count}次）" if recent_count > 1 else f"{sd['dividend_yield']*100:.1f}%"

            lines.append(f"{i}. {sd['name']} ({sd['code']}) {tag} {industry}{cycle_note}")
            lines.append(f"   综合评分：{total:.1f}/100 {stars}")
            lines.append(f"")
            lines.append(f"   📈 关键指标")
            lines.append(f"   - 股息率：{dividend_text} | 历史分红：{sd['history_count']}次")
            lines.append(f"   - 市盈率：{sd['pe']:.1f} | 市净率：{sd['pb']:.2f}")
            lines.append(f"   - 市值：{sd['market_cap']/100000000:.0f}亿 | 最新价：{sd['price']:.2f}")

            # 显示财务指标（如果有）
            if 'financial_data' in stock and stock['financial_data']:
                fd = stock['financial_data']
                roe = fd.get('roe')
                profit_growth = fd.get('profit_growth')
                debt_ratio = fd.get('debt_ratio')

                financial_indicators = []
                if roe is not None:
                    financial_indicators.append(f"ROE {roe:.1f}%")
                if profit_growth is not None:
                    financial_indicators.append(f"利润增长 {profit_growth:.1f}%")
                if debt_ratio is not None:
                    financial_indicators.append(f"负债率 {debt_ratio:.1f}%")

                if financial_indicators:
                    lines.append(f"   - 财务数据：{' | '.join(financial_indicators)}")

            lines.append(f"")
            lines.append(f"   💡 评分明细")
            for reason in stock['reasons']:
                lines.append(f"   {reason}")
            lines.append("")
            lines.append("━" * 55)
            lines.append("")

        # 投资建议
        lines.append("💡 投资建议")
        lines.append("1. 优先配置：防御性行业（银行、电力、高速公路）")
        lines.append("2. 适度配置：优质消费、制造业龙头")
        lines.append("3. 谨慎配置：周期股（需择时，关注宏观）")
        lines.append("4. 分散投资：建议配置 10-15 只，分散行业风险")
        lines.append("")
        lines.append("⚠️ 风险提示：本报告仅供参考，不构成投资建议。股市有风险，投资需谨慎。")

        return '\n'.join(lines)
