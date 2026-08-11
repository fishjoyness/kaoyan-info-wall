#!/usr/bin/env python3
"""
计算机考研信息墙 - 每日自动刷新脚本
抓取研招网公告页，过滤计算机相关条目，更新 HTML 文件的 DATA.items 数组。
由 GitHub Actions 每天 9:45（UTC 1:45）自动调用。
"""
import urllib.request
import re
import os
from datetime import datetime, timedelta

# ========== 配置 ==========
YANZHAO_URL = "https://yz.chsi.com.cn/kyzx/yxzc/"
HTML_FILE = "index.html"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# 计算机相关关键词（标题含任一即保留）
CS_KEYWORDS = [
    "计算机", "人工智能", "软件工程", "网络空间安全", "408",
    "电子信息", "数据结构", "智能科学", "集成电路", "网络安全",
    "信息与通信", "控制科学", "控制工程", "模式识别", "机器学习",
    "深度学习", "大数据", "云计算", "物联网", "密码学"
]

# 焦虑关键词（标题含任一即排除）
ANXIETY_WORDS = [
    "弃考", "焦虑", "压力", "崩溃", "最难", "绝望", "放弃",
    "emo", "想哭", "内耗", "煎熬", "卷死", "死磕", "心态爆炸",
    "怀疑人生", "退意"
]

# 排除关键词（非计算机方向）
EXCLUDE_WORDS = [
    "MBA", "EMBA", "MPAcc", "金融", "保险", "会计", "法律",
    "医学", "临床", "药学", "护理", "教育", "新闻", "传播",
    "艺术", "设计", "建筑", "土木", "化工", "材料",
    "少数民族", "退役", "士兵", "骨干", "调剂"
]


def fetch_yanzhao():
    """抓取研招网公告页，返回条目列表"""
    req = urllib.request.Request(YANZHAO_URL, headers={"User-Agent": USER_AGENT})
    html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8")

    items = []
    # 匹配含日期的 li 块
    li_blocks = re.findall(r"<li[^>]*>.*?</li>", html, re.DOTALL)
    for li in li_blocks:
        dates = re.findall(r"(\d{4}-\d{2}-\d{2})", li)
        links = re.findall(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', li)
        if not dates or not links:
            continue
        # 找到有实际标题内容的链接
        title = None
        link = None
        for href, text in links:
            text = text.strip()
            if text and len(text) > 8 and not text.startswith("&"):
                title = text
                link = href
                break
        if not title or not link:
            continue
        # 补全链接
        if link.startswith("/"):
            link = "https://yz.chsi.com.cn" + link
        items.append({"title": title, "url": link, "date": dates[0]})
    return items


def filter_cs_items(items):
    """过滤出计算机相关、非焦虑、非排除的条目"""
    result = []
    for it in items:
        title = it["title"]
        # 排除焦虑
        if any(w in title for w in ANXIETY_WORDS):
            continue
        # 排除非计算机方向
        if any(w in title for w in EXCLUDE_WORDS):
            continue
        # 必须含计算机相关关键词
        if not any(kw in title for kw in CS_KEYWORDS):
            continue
        result.append(it)
    return result


def filter_by_date(items, days=7):
    """只保留最近 N 天的条目，返回 (today_items, week_items)"""
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

    today_items = []
    week_items = []
    for it in items:
        if it["date"] >= week_ago:
            if it["date"] >= today:
                today_items.append(it)
            else:
                week_items.append(it)
    return today_items, week_items


def format_item(item, item_id, when, item_type="985"):
    """格式化为 JS 对象字符串"""
    # 日期格式 M/D
    date_obj = datetime.strptime(item["date"], "%Y-%m-%d")
    time_str = f"{date_obj.month}/{date_obj.day}"

    # 转义标题和 URL 中的特殊字符
    title = item["title"].replace("'", "\\'").replace('"', "")
    url = item["url"].replace("'", "\\'")

    # 生成摘要（截取标题前 40 字 + 日期）
    summary = f"研招网公告 · {item['date']}"

    return (
        f"    {{id:'{item_id}', when:'{when}', type:'{item_type}', topic:'招生', "
        f"source:'研招网 · 院校政策', time:'{time_str}',\n"
        f"     title:'{title}',\n"
        f"     summary:'{summary}',\n"
        f"     url:'{url}'}},\n"
    )


def update_html(today_items, week_items):
    """更新 HTML 文件的 DATA.items 数组"""
    with open(HTML_FILE, "r", encoding="utf-8") as f:
        html = f.read()

    # 1. 把所有 when:'24h' 降级为 when:'7d'
    html = html.replace("when:'24h'", "when:'7d'")

    # 2. 在 items: [ 后面插入新的 24h 条目
    new_24h = ""
    for i, it in enumerate(today_items):
        new_24h += format_item(it, f"auto{i+1}", "24h")
    for i, it in enumerate(week_items[:5]):  # 7d 最多补 5 条
        new_24h += format_item(it, f"auto7d{i+1}", "7d")

    if new_24h:
        # 在 items: [ 后插入
        html = re.sub(
            r"(items:\s*\[)",
            r"\1\n    // ========== 自动抓取（GitHub Actions）==========\n" + new_24h,
            html,
            count=1
        )

    # 3. 更新时间戳
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M")
    html = re.sub(
        r'数据快照：[^<]*',
        f'数据快照：{timestamp} · 自动刷新（GitHub Actions）· 想手动更新跟我说「刷新信息墙」',
        html
    )

    with open(HTML_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    return len(today_items), len(week_items)


def main():
    print("=== 计算机考研信息墙自动刷新 ===")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. 抓取研招网
    print("\n[1/4] 抓取研招网公告页...")
    try:
        all_items = fetch_yanzhao()
        print(f"  抓取到 {len(all_items)} 条公告")
    except Exception as e:
        print(f"  抓取失败: {e}")
        print("  跳过更新，只更新时间戳")
        # 只更新时间戳
        with open(HTML_FILE, "r", encoding="utf-8") as f:
            html = f.read()
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M")
        html = re.sub(r'数据快照：[^<]*', f'数据快照：{timestamp} · 自动刷新（GitHub Actions，抓取失败）', html)
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html)
        return

    # 2. 过滤计算机相关
    print("\n[2/4] 过滤计算机相关条目...")
    cs_items = filter_cs_items(all_items)
    print(f"  计算机相关: {len(cs_items)} 条")

    # 3. 按日期分类
    print("\n[3/4] 按日期分类...")
    today_items, week_items = filter_by_date(cs_items, days=7)
    print(f"  今日: {len(today_items)} 条")
    print(f"  近 7 天: {len(week_items)} 条")

    # 4. 更新 HTML
    print("\n[4/4] 更新 HTML 文件...")
    today_count, week_count = update_html(today_items, week_items)
    print(f"  已更新: 24h {today_count} 条, 7d {week_count} 条")

    print("\n=== 完成 ===")


if __name__ == "__main__":
    main()
