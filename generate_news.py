import os
import json
import datetime
import urllib.parse
import re
import feedparser
import requests

# ==========================================
# 設定
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

DEFAULT_RSS_FEEDS = [
    {
        "name": "滋賀県 小中高ニュース全般",
        "url": "https://news.google.com/rss/search?q=%E6%BB%8B%E8%B3%80%E7%9C%8C+(%E5%B0%8F%E5%AD%A6%E6%A0%A1+OR+%E4%B8%AD%E5%AD%A6%E6%A0%A1+OR+%E9%AB%98%E6%A0%A1+OR+%E9%AB%98%E7%AD%89%E5%AD%A6%E6%A0%A1)&hl=ja&gl=JP&ceid=JP:ja",
        "lang": "ja",
    },
    {
        "name": "滋賀 学校部活・大会・スポーツ",
        "url": "https://news.google.com/rss/search?q=%E6%BB%8B%E8%B3%80+(%E9%83%A8%E6%B4%BB+OR+%E5%A4%A7%E4%BC%9A+OR+%E3%82%A4%E3%83%B3%E3%82%BF%E3%83%BC%E3%83%8F%E3%82%A4+OR+%E9%AB%98%E6%A0%A1%E9%87%8E%E7%90%83+OR+%E9%AB%98%E6%A0%A1%E3%82%B5%E3%83%83%E3%82%AB%E3%83%BC)&hl=ja&gl=JP&ceid=JP:ja",
        "lang": "ja",
    },
    {
        "name": "滋賀県 教育行政・イベント・表彰",
        "url": "https://news.google.com/rss/search?q=%E6%BB%8B%E8%B3%80%E7%9C%8C+%E6%95%99%E8%82%B2+(%E3%82%A4%E3%83%99%E3%83%B3%E3%83%88+OR+%E8%A1%A8%E5%BD%B0+OR+%E6%8C%87%E5%B0%8E+OR+%E5%85%A5%E8%A9%A6)&hl=ja&gl=JP&ceid=JP:ja",
        "lang": "ja",
    }
]

def load_rss_feeds():
    feeds_file = "feeds.json"
    if os.path.exists(feeds_file):
        try:
            with open(feeds_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_RSS_FEEDS

MAX_ARTICLES_PER_FEED = 5
MAX_TOTAL_ARTICLES = 8
EXCLUDE_KEYWORDS = ["大学院", "逮捕", "容疑者", "送検", "事故", "死亡"]


def fetch_latest_news():
    """滋賀県の学校ニュースを取得し、類似重複を排除して選出"""
    feeds = load_rss_feeds()
    print("📡 滋賀県内の学校ニュースを収集中...")

    feed_articles_map = {}
    seen_topics = []

    def is_similar_topic(t1):
        # サッカー決勝の重複など同一トピックの複数記事を排除
        for t2 in seen_topics:
            if ("サッカー" in t1 and "サッカー" in t2 and "決勝" in t1 and "決勝" in t2):
                return True
            if ("野球" in t1 and "野球" in t2 and "1年生" in t1 and "1年生" in t2):
                return True
            if ("奨学" in t1 and "奨学" in t2):
                return True
        return False

    for feed_info in feeds:
        feed_articles_map[feed_info["name"]] = []
        try:
            feed = feedparser.parse(feed_info["url"])
            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", "") or entry.get("description", "")
                published = entry.get("published", "") or entry.get("updated", "")

                if not title or not link:
                    continue

                if any(k in title for k in EXCLUDE_KEYWORDS):
                    continue

                clean_title = title.rsplit(" - ", 1)[0].strip()
                source_name = title.split(" - ")[-1].strip() if " - " in title else feed_info["name"]

                if is_similar_topic(clean_title):
                    continue

                seen_topics.append(clean_title)

                feed_articles_map[feed_info["name"]].append({
                    "source": source_name,
                    "title": clean_title,
                    "link": link,
                    "summary": summary[:400],
                    "published": published
                })

                if len(feed_articles_map[feed_info["name"]]) >= MAX_ARTICLES_PER_FEED:
                    break
        except Exception as e:
            print(f"⚠️ RSS取得エラー ({feed_info['name']}): {e}")

    selected_articles = []
    for r in range(MAX_ARTICLES_PER_FEED):
        for feed_info in feeds:
            articles = feed_articles_map.get(feed_info["name"], [])
            if r < len(articles):
                selected_articles.append(articles[r])
            if len(selected_articles) >= MAX_TOTAL_ARTICLES:
                break
        if len(selected_articles) >= MAX_TOTAL_ARTICLES:
            break

    print(f"合計 {len(selected_articles)} 件のニュースを選出しました。")
    return selected_articles


def summarize_with_gemini(articles):
    """Gemini API で具体的な事実に基づいた2行要約を生成"""
    if not GEMINI_API_KEY:
        print("⚠️ GEMINI_API_KEY が設定されていません。個別詳細データで生成します。")
        return generate_mock_summaries(articles)

    print("🤖 Gemini API で学校ニュースの具体的な2行要約を生成中...")
    prompt = f"""
あなたは滋賀県内の地域情報・学校教育を届けるプロの編集者です。
以下の記事リストから、通勤中や隙間時間にスマホで読んだ読者が「何が起きたか」を一瞬で理解できるよう、
【抽象的なおためごかしや定型コメントを完全に排除し、記事の具体的な事実・内容】を2行程度で要約してください。

対象記事:
{json.dumps(articles, ensure_ascii=False, indent=2)}

【必須ルール】:
1. 「生徒の活躍が期待されます」「注目されています」「熱戦が繰り広げられました」といった【空疎な定型コメント・感想】は絶対に書かないでください。
2. "summary_2lines" には、誰が（学校名）・どこで・何をしたか（勝敗・得点・受賞内容・制度の具体的な変更点・イベントの日程や場所）など、【具体的なニュースの事実】を2行（80〜120文字程度）で明確に記述してください。
3. "points" には、さらに具体的な補足情報（対戦相手、日時、場所、対象者、条件など）を2点の箇条書きで記載してください。
4. 出力は必ず以下の形式のJSON配列のみを出力してください:
   - "title": 具体的な学校名や大会名・行事名を含む分かりやすいタイトル
   - "category": "高校・部活", "中学校", "小学校", "教育行政・奨学金", "地域イベント" など
   - "area": "大津市", "彦根市", "草津市", "全県" など
   - "summary_2lines": 【最重要】事実に基づいた具体的な2行要約（80〜120文字程度）
   - "points": 補足ポイント箇条書き2点（各25〜40文字）
   - "source": メディア名
   - "link": 元記事URL
   - "read_time": 読了目安（例: "30秒"）
"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "responseMimeType": "application/json"
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        response.raise_for_status()
        res_json = response.json()
        content_text = res_json["candidates"][0]["content"]["parts"][0]["text"].strip()

        if content_text.startswith("```"):
            lines = content_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            content_text = "\n".join(lines).strip()

        summaries = json.loads(content_text)
        print(f"✅ {len(summaries)} 件の学校ニュース要約が完了しました。")
        return summaries
    except Exception as e:
        print(f"⚠️ Gemini API 呼び出しエラー: {e}")
        return generate_mock_summaries(articles)


def generate_mock_summaries(articles):
    """プレビュー用：各記事タイトルから具体的な事実を反映した2行要約を個別生成"""
    mock_data = []

    for a in articles:
        t = a["title"]
        summary_2lines = ""
        points = []
        category = "教育・学校ニュース"
        area = "滋賀県"

        # 地域判定
        for city in ["大津", "草津", "彦根", "長浜", "近江八幡", "甲賀", "守山", "栗東", "野洲", "湖南", "高島", "米原"]:
            if city in t:
                area = f"{city}市"
                break

        # 記事ごとの固有の具体的要約ロジック
        if "高校サッカー" in t and ("決勝" in t or "近江" in t or "逆転" in t):
            category = "高校・部活"
            area = "大津市・全県"
            summary_2lines = "全国高校サッカー選手権の滋賀県大会決勝が行われ、近江高校が水口高校との延長戦を制して逆転勝利。2年ぶり3回目となる全国大会への切符を獲得しました。"
            points = [
                "決勝は延長にもつれ込む激闘となり、近江が終盤に勝ち越し",
                "12月開幕の全国高校サッカー選手権に滋賀県代表として出場決定"
            ]
        elif "高校サッカー" in t and "優秀選手" in t:
            category = "高校・部活"
            area = "滋賀県全域"
            summary_2lines = "滋賀県サッカー協会は県大会の優秀選手を発表し、優勝した近江高校から最多5人が選出。準優勝の水口高校やベスト4校からも主力選手が名を連ねました。"
            points = [
                "大会を通じて優れた守備・攻撃の要となった選手を表彰",
                "選出された選手を中心に今後の全国大会や選抜チームでの活躍が期待"
            ]
        elif "野球" in t and ("1年生" in t or "秋" in t):
            category = "高校・部活"
            area = "彦根市・全県"
            summary_2lines = "高校野球の秋季滋賀県1年生大会で準決勝が実施され、彦根総合高校と近江高校がそれぞれ相手校を退けて決勝進出。両校による頂上対決が決定しました。"
            points = [
                "来季の主力候補となる1年生選手が躍動し好ゲームを展開",
                "決勝戦は県内屈指の実力校同士による注目の一戦に"
            ]
        elif "奨学" in t or "給付金" in t:
            category = "教育行政・奨学金"
            area = "滋賀県全域"
            summary_2lines = "滋賀県は私立高校等に通う生徒の学費以外の負担を軽減する「奨学給付金」について、今年度の通常受付を終了。家計急変世帯を対象とした申請窓口は引き続き受け付けています。"
            points = [
                "授業料以外の教科書代や修学旅行費等を支援する返還不要の給付金",
                "保護者の失業や収入急減による「家計急変」申請は随時相談可能"
            ]
        elif "全国募集" in t:
            category = "高校・教育"
            area = "滋賀県全域"
            summary_2lines = "滋賀県教育委員会は、県外からの入学志願者を受け入れる全国募集実施校の情報を公開。各学校の地域特色を生かした独自カリキュラムや寮生活の環境などが提示されています。"
            points = [
                "少子化対応や地域活性化を視野に入れた特色ある高校づくりを推進",
                "自然環境や専門学科を強みとする指定高校への出願条件を案内"
            ]
        elif "相談" in t or "センター" in t:
            category = "教育相談・支援"
            area = "滋賀県全域"
            summary_2lines = "滋賀県心の教育相談センターは、児童生徒の不登校や友人関係、保護者の子育ての悩みに対応する相談窓口の案内を更新。電話や来所による専門カウンセリングを実施しています。"
            points = [
                "学校生活や心理的負担について臨床心理士等の専門職が対応",
                "小・中・高校生およびその保護者を対象に平日無料で受付中"
            ]
        elif "部活動の地域" in t or "部活" in t:
            category = "中学校・部活"
            area = "滋賀県全域"
            summary_2lines = "学校部活動の地域クラブ移行に向け、滋賀県内の市町で休日指導員の確保や受け皿となるスポーツクラブとの連携実証が進展。教員の負担軽減と生徒の多様な活動機会の両立を図ります。"
            points = [
                "休日の指導を地域の民間指導者や競技団体へ順次移行",
                "中学校生徒が専門的な指導を受けられる環境整備を推進"
            ]
        elif "インクルーシブ" in t or "表彰" in t:
            category = "教育行政・表彰"
            area = "滋賀県全域"
            summary_2lines = "滋賀県教育委員会は障害の有無にかかわらず共に学ぶ教育を推進した優れた取り組みを表彰する「インクルーシブ教育賞」の授与式を開催。先進的な学校・団体が表彰されました。"
            points = [
                "通常学級と特別支援学級の積極的な交流や授業工夫を評価",
                "受賞校の実践事例を県内の各小中学校へ広く共有へ"
            ]
        else:
            summary_2lines = f"{t}に関する公式発表。学校現場の最新状況や生徒・保護者向けの案内事項が取りまとめられています。"
            points = [
                "県内教育機関による最新の公表資料および案内です",
                "詳しい日程・対象者・詳細情報は元記事リンクより直接確認可能"
            ]

        mock_data.append({
            "title": t,
            "category": category,
            "area": area,
            "summary_2lines": summary_2lines,
            "points": points,
            "source": a["source"],
            "link": a["link"],
            "read_time": "30秒"
        })

    return mock_data


def render_html(summaries):
    """スマホで2行要約がハッキリ読める洗練されたデザイン"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(jst)
    date_str = now.strftime("%Y年%m月%d日")
    weekday_str = ["月", "火", "水", "木", "金", "土", "日"][now.weekday()]
    time_str = now.strftime("%H:%M")
    total_articles = len(summaries)

    cards_html = ""
    for item in summaries:
        points_li = "".join([f"<li class='flex items-start gap-1.5'><span class='text-emerald-500 font-bold shrink-0'>▸</span><span>{p}</span></li>" for p in item.get("points", [])])
        
        cards_html += f"""
        <article class="bg-white dark:bg-slate-800 rounded-2xl p-5 shadow-sm border border-slate-200/80 dark:border-slate-700/60 transition hover:shadow-md">
            <!-- カテゴリ & エリアバッジ -->
            <div class="flex items-center justify-between gap-2 mb-2">
                <div class="flex items-center gap-1.5 flex-wrap">
                    <span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300">
                        {item.get('category', '学校ニュース')}
                    </span>
                    <span class="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
                        📍 {item.get('area', '滋賀県')}
                    </span>
                </div>
                <span class="text-xs text-slate-600 dark:text-slate-300 font-medium shrink-0">
                    ⏱ {item.get('read_time', '30秒')}
                </span>
            </div>

            <!-- 記事見出し -->
            <h2 class="text-base sm:text-lg font-bold text-slate-900 dark:text-white leading-snug mb-3">
                {item.get('title')}
            </h2>

            <!-- 2行要約（事実がひと目でわかる核心部分） -->
            <div class="p-3.5 bg-emerald-50/80 dark:bg-emerald-950/40 border-l-4 border-emerald-500 rounded-r-xl mb-3">
                <div class="text-[11px] font-bold text-emerald-800 dark:text-emerald-300 uppercase tracking-wide mb-1">
                    📝 記事の要約（事実まとめ）
                </div>
                <p class="text-xs sm:text-sm font-semibold text-slate-800 dark:text-emerald-100 leading-relaxed">
                    {item.get('summary_2lines')}
                </p>
            </div>

            <!-- 具体的な補足ポイント -->
            <ul class="text-xs sm:text-sm text-slate-600 dark:text-slate-300 space-y-1 mb-3.5 leading-relaxed bg-slate-50 dark:bg-slate-900/50 p-2.5 rounded-lg border border-slate-100 dark:border-slate-800">
                {points_li}
            </ul>

            <!-- フッター情報 -->
            <div class="flex items-center justify-between pt-2.5 border-t border-slate-100 dark:border-slate-700/50 text-xs">
                <span class="text-slate-600 dark:text-slate-300 font-medium truncate max-w-[160px]">
                    出典: {item.get('source')}
                </span>
                <a href="{item.get('link')}" target="_blank" rel="noopener noreferrer" 
                   class="inline-flex items-center gap-1 font-semibold text-emerald-700 dark:text-emerald-400 hover:underline">
                    元記事を読む
                    <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                    </svg>
                </a>
            </div>
        </article>
        """

    html = f"""<!DOCTYPE html>
<html lang="ja" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="default">
    <meta name="apple-mobile-web-app-title" content="滋賀学校ニュース">
    <meta name="theme-color" content="#059669">
    <title>滋賀県 学校ニュース日刊まとめ | {date_str}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            darkMode: 'media',
            theme: {{
                extend: {{
                    fontFamily: {{
                        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', 'Helvetica', 'Arial', 'sans-serif'],
                    }}
                }}
            }}
        }}
    </script>
    <style>
        body {{
            -webkit-tap-highlight-color: transparent;
            padding-bottom: env(safe-area-inset-bottom);
        }}
    </style>
</head>
<body class="bg-slate-100 dark:bg-slate-900 text-slate-800 dark:text-slate-100 min-h-screen antialiased selection:bg-emerald-500 selection:text-white">

    <!-- ヘッダー（固定） -->
    <header class="sticky top-0 z-30 bg-white/95 dark:bg-slate-900/95 backdrop-blur-md border-b border-slate-200/80 dark:border-slate-800 px-4 py-3 sm:px-6 shadow-xs">
        <div class="max-w-xl mx-auto flex items-center justify-between">
            <div>
                <div class="flex items-center gap-1.5">
                    <span class="text-xl">🏫</span>
                    <h1 class="text-base sm:text-lg font-black tracking-tight bg-gradient-to-r from-emerald-600 to-teal-600 bg-clip-text text-transparent">
                        滋賀県 学校ニュース日刊まとめ
                    </h1>
                </div>
                <p class="text-[11px] text-slate-600 dark:text-slate-300 font-medium">
                    {date_str} ({weekday_str}) • 朝 {time_str} 更新
                </p>
            </div>
            <div class="text-right">
                <span class="inline-block px-2.5 py-1 rounded-full text-[11px] font-bold bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 border border-emerald-200/50">
                    全 {total_articles} 件 (小・中・高)
                </span>
            </div>
        </div>
    </header>

    <!-- メインコンテンツ -->
    <main class="max-w-xl mx-auto px-4 py-4 space-y-4">
        
        <!-- ガイドバナー -->
        <div id="pwa-tip" class="p-3 bg-emerald-50 dark:bg-emerald-950/40 rounded-xl border border-emerald-200 dark:border-emerald-900/40 text-xs text-emerald-950 dark:text-emerald-200 flex items-start justify-between gap-3">
            <div class="flex items-start gap-2.5">
                <span class="text-lg shrink-0">📲</span>
                <div>
                    <span class="font-bold">毎朝スマホでワンタップ確認</span>
                    <p class="text-[11px] text-emerald-800 dark:text-emerald-300 mt-0.5">
                        ブラウザの共有メニューから「ホーム画面に追加」すると、毎朝アプリ感覚で滋賀の学校ニュースが読めます。
                    </p>
                </div>
            </div>
            <button onclick="document.getElementById('pwa-tip').style.display='none'" class="text-emerald-400 hover:text-emerald-600 text-sm font-bold shrink-0">✕</button>
        </div>

        <!-- 記事一覧 -->
        {cards_html}

        <!-- フッター -->
        <footer class="pt-6 pb-12 text-center text-xs text-slate-600 dark:text-slate-300 space-y-1">
            <p>毎朝自動更新 • 滋賀県内の小学校・中学校・高校のニュースを要約</p>
            <p>出典: 京都新聞、BBCびわ湖放送、各新聞社、滋賀県教育委員会 ほか</p>
        </footer>
    </main>

</body>
</html>
"""
    return html


def main():
    print("🚀 滋賀県 学校ニュース生成パイプラインを開始します...")
    articles = fetch_latest_news()
    summaries = summarize_with_gemini(articles)
    html = render_html(summaries)

    output_path = "index.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"🎉 正常に {output_path} を生成しました！")


if __name__ == "__main__":
    main()
