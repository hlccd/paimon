"""原石仪表盘页面"""

from paimon.channels.webui.theme import (
    THEME_COLORS, BASE_CSS, NAVIGATION_CSS, NAV_LINKS_CSS, navigation_html,
)

DASHBOARD_CSS = """
    body { min-height: 100vh; }

    .container { max-width: 1200px; margin: 0 auto; padding: 24px; }
    .page-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }
    .page-header h1 { font-size: 24px; color: var(--text-primary); font-weight: 600; }
    .refresh-btn {
        padding: 8px 16px; background: var(--paimon-panel-light); color: var(--text-secondary);
        border: 1px solid var(--paimon-border); border-radius: 6px; cursor: pointer; font-size: 13px;
    }
    .refresh-btn:hover { border-color: var(--gold-dark); color: var(--gold); }

    .stat-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 28px; }
    .stat-card {
        background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 10px; padding: 20px; border-left: 3px solid var(--gold-dark);
    }
    .stat-card .label { font-size: 13px; color: var(--text-muted); margin-bottom: 8px; }
    .stat-card .value { font-size: 28px; font-weight: 700; color: var(--gold); }
    .stat-card .sub { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

    .tabs { display: flex; gap: 4px; margin-bottom: 24px; border-bottom: 1px solid var(--paimon-border); }
    .tab-btn {
        padding: 10px 20px; background: transparent; border: none; color: var(--text-muted);
        cursor: pointer; font-size: 14px; font-weight: 500; border-bottom: 2px solid transparent;
    }
    .tab-btn:hover { color: var(--text-primary); }
    .tab-btn.active { color: var(--gold); border-bottom-color: var(--gold); }
    .tab-panel { display: none; }
    .tab-panel.active { display: block; }

    .data-table { width: 100%; border-collapse: collapse; }
    .data-table th, .data-table td { padding: 12px 16px; border-bottom: 1px solid var(--paimon-border); font-size: 14px; }
    .data-table th { color: var(--gold); font-weight: 600; font-size: 13px; text-align: left; }
    .data-table th.r { text-align: right; }
    .data-table td.r { text-align: right; font-family: 'SF Mono', Monaco, Consolas, monospace; font-size: 13px; }
    .data-table tbody tr:hover td { background: var(--paimon-panel); }

    .chart-controls { display: flex; gap: 8px; align-items: center; margin-bottom: 20px; flex-wrap: wrap; }
    .ctrl-btn {
        padding: 6px 14px; background: var(--paimon-panel); border: 1px solid var(--paimon-border);
        border-radius: 6px; color: var(--text-secondary); cursor: pointer; font-size: 13px;
    }
    .ctrl-btn:hover { border-color: var(--gold-dark); color: var(--gold); }
    .ctrl-btn.active { background: var(--paimon-panel-light); border-color: var(--gold); color: var(--gold); }
    .ctrl-sep { width: 1px; height: 20px; background: var(--paimon-border); margin: 0 4px; }
    .ctrl-right { margin-left: auto; display: flex; gap: 4px; }

    /* 柱状图 */
    .chart-wrap { position: relative; padding-left: 56px; }
    .chart-y {
        position: absolute; left: 0; top: 0; bottom: 28px; width: 52px;
        display: flex; flex-direction: column; justify-content: space-between; align-items: flex-end;
    }
    .chart-y span { font-size: 11px; color: var(--text-muted); line-height: 1; }
    .chart-cols {
        display: flex; align-items: flex-end; gap: 3px;
        height: 220px;
        border-left: 1px solid var(--paimon-border);
        border-bottom: 1px solid var(--paimon-border);
        padding: 0 2px;
    }
    .chart-col {
        flex: 1; display: flex; flex-direction: column; align-items: center;
        min-width: 0; height: 100%;
        justify-content: flex-end;
    }
    .chart-bar {
        width: 70%; max-width: 42px; min-width: 6px;
        border-radius: 3px 3px 0 0;
        background: linear-gradient(0deg, var(--star-dark), var(--star-light));
        cursor: pointer; position: relative;
        transition: height .3s ease, opacity .2s;
    }
    .chart-bar.cost-bar { background: linear-gradient(0deg, var(--gold-dark), var(--gold-light)); }
    .chart-bar:hover { opacity: .8; }
    .chart-tip {
        display: none; position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%);
        background: var(--paimon-panel); border: 1px solid var(--gold-dark); border-radius: 6px;
        padding: 8px 12px; font-size: 12px; color: var(--text-primary); white-space: pre-line; z-index: 20;
        pointer-events: none; min-width: 120px; text-align: center; line-height: 1.5;
    }
    .chart-bar:hover .chart-tip { display: block; }
    .chart-labels {
        display: flex; gap: 3px; padding: 0 2px;
    }
    .chart-lbl {
        flex: 1; text-align: center; font-size: 11px; color: var(--text-muted);
        padding-top: 6px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }

    .empty-state { text-align: center; padding: 60px 20px; color: var(--text-muted); font-size: 14px; }
"""

DASHBOARD_BODY = """
    <div class="container">
        <div class="page-header">
            <h1>📊 用量</h1>
            <button class="refresh-btn" onclick="refreshAll()">刷新</button>
        </div>

        <div class="stat-cards">
            <div class="stat-card"><div class="label">总调用次数</div><div class="value" id="cCalls">-</div></div>
            <div class="stat-card"><div class="label">总 Token</div><div class="value" id="cTokens">-</div><div class="sub" id="cTokensSub"></div></div>
            <div class="stat-card"><div class="label">总花费</div><div class="value" id="cCost">-</div></div>
            <div class="stat-card"><div class="label">缓存命中率</div><div class="value" id="cCache">-</div><div class="sub" id="cCacheSub"></div></div>
        </div>

        <div class="tabs">
            <button class="tab-btn active" onclick="switchTab('detail',this)">调用明细</button>
            <button class="tab-btn" onclick="switchTab('chart',this)">统计图表</button>
        </div>

        <div id="detail" class="tab-panel active">
            <div id="detailEl"><div class="empty-state">加载中...</div></div>
        </div>

        <div id="chart" class="tab-panel">
            <div class="chart-controls">
                <button class="ctrl-btn active" data-p="day" onclick="setP('day',this)">按日</button>
                <button class="ctrl-btn" data-p="week" onclick="setP('week',this)">按周</button>
                <button class="ctrl-btn" data-p="month" onclick="setP('month',this)">按月</button>
                <div class="ctrl-sep"></div>
                <button class="ctrl-btn" data-p="hour" onclick="setP('hour',this)">按小时</button>
                <button class="ctrl-btn" data-p="weekday" onclick="setP('weekday',this)">按星期</button>
                <div class="ctrl-right">
                    <button class="ctrl-btn active" data-m="tokens" onclick="setM('tokens',this)">Token</button>
                    <button class="ctrl-btn" data-m="cost" onclick="setM('cost',this)">花费</button>
                </div>
            </div>
            <div id="chartArea"><div class="empty-state">加载中...</div></div>
        </div>
    </div>
"""

DASHBOARD_SCRIPT = """
    <script>
    (function(){
        var P='day', M='tokens', cache={}, BAR_H=200;
        var WD=['周日','周一','周二','周三','周四','周五','周六'];
        function esc(s){return s?s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'):'';}
        function fN(n){return(n||0).toLocaleString();}
        function fC(n){return'$'+(n||0).toFixed(4);}
        function fS(n){if(n>=1e6)return(n/1e6).toFixed(1)+'M';if(n>=1e3)return(n/1e3).toFixed(1)+'K';return n.toFixed(0);}

        window.switchTab=function(id,btn){
            document.querySelectorAll('.tab-btn').forEach(function(t){t.classList.remove('active');});
            document.querySelectorAll('.tab-panel').forEach(function(p){p.classList.remove('active');});
            if(btn)btn.classList.add('active');
            var el=document.getElementById(id);if(el)el.classList.add('active');
            if(id==='chart'&&!cache[P])fetchC(P);
        };

        function renderCards(g){
            document.getElementById('cCalls').textContent=fN(g.count);
            var tot=(g.total_input_tokens||0)+(g.total_output_tokens||0);
            document.getElementById('cTokens').textContent=fN(tot);
            document.getElementById('cTokensSub').textContent='输入 '+fN(g.total_input_tokens)+' / 输出 '+fN(g.total_output_tokens);
            document.getElementById('cCost').textContent=fC(g.total_cost_usd);
            var cw=g.total_cache_creation_tokens||0,cr=g.total_cache_read_tokens||0,ct=cw+cr;
            document.getElementById('cCache').textContent=ct>0?((cr/ct)*100).toFixed(1)+'%':'-';
            document.getElementById('cCacheSub').textContent='写入 '+fN(cw)+' / 命中 '+fN(cr);
        }

        function renderDetail(detail){
            var el=document.getElementById('detailEl');
            if(!detail||!detail.length){el.innerHTML='<div class="empty-state">暂无数据</div>';return;}
            var rows=detail.map(function(d){
                var t=(d.input_tokens||0)+(d.output_tokens||0);
                return'<tr><td>'+esc(d.component)+'</td><td>'+esc(d.purpose||'-')+'</td>'
                    +'<td class="r">'+fN(t)+'</td><td class="r">'+fN(d.input_tokens)+'</td>'
                    +'<td class="r">'+fN(d.output_tokens)+'</td><td class="r">'+fN(d.cache_read_tokens||0)+'</td>'
                    +'<td class="r">'+fC(d.cost_usd)+'</td><td class="r">'+fN(d.count)+'</td></tr>';
            }).join('');
            el.innerHTML='<table class="data-table"><thead><tr>'
                +'<th>组件</th><th>用途</th><th class="r">总 Token</th><th class="r">输入</th>'
                +'<th class="r">输出</th><th class="r">缓存命中</th><th class="r">花费</th><th class="r">调用次数</th>'
                +'</tr></thead><tbody>'+rows+'</tbody></table>';
        }

        async function loadStats(){
            try{
                var r=await fetch('/api/token_stats');var d=await r.json();
                renderCards(d.global);renderDetail(d.detail);
            }catch(e){
                document.getElementById('detailEl').innerHTML='<div class="empty-state">加载失败</div>';
            }
        }

        window.setP=function(p,btn){
            P=p;
            document.querySelectorAll('.ctrl-btn[data-p]').forEach(function(b){b.classList.remove('active');});
            if(btn)btn.classList.add('active');
            cache[p]?renderC():fetchC(p);
        };
        window.setM=function(m,btn){
            M=m;
            document.querySelectorAll('.ctrl-btn[data-m]').forEach(function(b){b.classList.remove('active');});
            if(btn)btn.classList.add('active');
            renderC();
        };

        async function fetchC(p){
            var el=document.getElementById('chartArea');
            el.innerHTML='<div class="empty-state">加载中...</div>';
            var cnt=p==='day'?14:p==='week'?8:p==='month'?6:30;
            try{
                var r=await fetch('/api/token_stats/timeline?period='+p+'&count='+cnt);
                var d=await r.json();
                cache[p]=d.data||[];
                renderC();
            }catch(e){el.innerHTML='<div class="empty-state">加载失败</div>';}
        }

        function fill(data){
            if(P==='hour'){
                var m={};data.forEach(function(d){m[d.period]=d;});
                var o=[];for(var h=0;h<24;h++)o.push(m[h]||{period:h,input_tokens:0,output_tokens:0,cost_usd:0,count:0,cache_creation_tokens:0,cache_read_tokens:0});
                return o;
            }
            if(P==='weekday'){
                var m={};data.forEach(function(d){m[d.period]=d;});
                var o=[];for(var w=0;w<7;w++)o.push(m[w]||{period:w,input_tokens:0,output_tokens:0,cost_usd:0,count:0,cache_creation_tokens:0,cache_read_tokens:0});
                return o;
            }
            return data;
        }

        function lbl(d){
            if(P==='hour')return d.period+':00';
            if(P==='weekday')return WD[d.period]||d.period;
            var s=String(d.period||'');
            if(P==='day'&&s.length===10)return s.slice(5);
            return s;
        }

        function renderC(){
            var raw=cache[P]||[];
            var el=document.getElementById('chartArea');
            if(!raw.length){el.innerHTML='<div class="empty-state">所选范围暂无数据</div>';return;}

            var data=fill(raw);
            var isCost=M==='cost';
            var maxV=0;
            var items=data.map(function(d){
                var v=isCost?(d.cost_usd||0):((d.input_tokens||0)+(d.output_tokens||0));
                if(v>maxV)maxV=v;
                return{l:lbl(d),v:v,cost:d.cost_usd||0,tok:(d.input_tokens||0)+(d.output_tokens||0),cnt:d.count||0};
            });
            if(maxV<=0)maxV=1;

            // Y axis
            var yHtml='';
            for(var i=4;i>=0;i--){
                var yv=maxV*i/4;
                yHtml+='<span>'+(isCost?fC(yv):fS(yv))+'</span>';
            }

            // Bars (pixel heights)
            var barsHtml='';
            var lblsHtml='';
            items.forEach(function(it){
                var h=Math.round(it.v/maxV*BAR_H);
                if(it.v>0&&h<3)h=3;
                var cls=isCost?'chart-bar cost-bar':'chart-bar';
                var tip=it.l+'\\n'+fN(it.tok)+' tok\\n'+fC(it.cost)+'\\n'+it.cnt+'次调用';
                barsHtml+='<div class="chart-col"><div class="'+cls+'" style="height:'+h+'px"><div class="chart-tip">'+esc(tip)+'</div></div></div>';
                lblsHtml+='<div class="chart-lbl">'+esc(it.l)+'</div>';
            });

            el.innerHTML='<div class="chart-wrap">'
                +'<div class="chart-y">'+yHtml+'</div>'
                +'<div class="chart-cols" style="height:'+BAR_H+'px">'+barsHtml+'</div>'
                +'<div class="chart-labels">'+lblsHtml+'</div>'
                +'</div>';
        }

        window.refreshAll=function(){cache={};loadStats();fetchC(P);};
        window.onload=function(){loadStats();fetchC('day');};
    })();
    </script>
"""


def build_dashboard_html() -> str:
    return (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Paimon - 仪表盘</title>
    <style>"""
        + THEME_COLORS
        + BASE_CSS
        + NAVIGATION_CSS
        + NAV_LINKS_CSS
        + DASHBOARD_CSS
        + """</style>
</head>
<body>"""
        + navigation_html("dashboard")
        + DASHBOARD_BODY
        + DASHBOARD_SCRIPT
        + """</body>
</html>"""
    )
