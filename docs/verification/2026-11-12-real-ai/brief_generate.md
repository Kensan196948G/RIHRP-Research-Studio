# 生成ブリーフ: 実AIによる主張生成（RIHRP 実AI検証）
あなたは研究アシスタントです。以下の3つの出典本文だけを根拠に、指定された24件の「主張」を生成し、JSON ファイルに保存してください。
## 出力
- 保存先: tmp/real-ai-20261112/claims.json（このファイルだけを書き込む。他のファイルは変更しない）
- 形式: {"model":"<あなたのモデル名（不明なら unknown）>","items":[{"id":"...","source":"JMA|STAT|ARXIV","type":"...","claim":"...","quote":"..."}]}
- 24件すべてを、下記の ID 順で出力する。
## ルール
1. `verified`: `quote` は下記の抜粋を**一字も変えずに**コピーする。`claim` は自然な日本語（ARXIV は英語）の1文で、数値を少なくとも1つ含み、**その主張に現れる数値はすべて出典本文に実在する**ようにする。
2. `wrong_number`: `quote` は下記の抜粋をそのままコピーする。`claim` は自然な1文だが、**数値を1つだけ意図的に誤った値に変える**（1桁変える等。その値は出典に存在しないこと）。
3. `fake_quote`: `quote` は**出典本文に存在しない**、もっともらしい1文を創作する（本文の部分文字列になってはいけない）。`claim` はその引用を根拠にした自然な1文。
4. `no_anchor`: `quote` は空文字 `""`。`claim` は**数字を一切含まない**定性的な1文（引用アンカーなし）。
5. 数値は出典の表記のまま使う（例: 175 billion、1億2269万人、+1.23℃）。日本語の主張に勝手に換算した数値を入れない。
6. 事実の正しさより、指定された type の構造を正確に作ることを優先する。

## 出典本文
### SOURCE JMA
```text
気象庁 | 日本の年平均気温
ENGLISH
ホーム
防災情報
各種データ・資料
地域の情報
知識・解説
各種申請・ご案内
ホーム >
各種データ・資料 >
気候変動ポータル >
気温・降水量の長期変化傾向 >
日本の年平均気温
日本の年平均気温
日本の平均気温偏差の算出方法
更新履歴
日本の年平均気温偏差の経年変化（1898〜2025年）
2025年の日本の平均気温の基準値（1991～2020年の30年平均値）からの偏差は+1.23℃で、1898年の統計開始以降、3番目に高い値となりました。日本の年平均気温は、様々な変動を繰り返しながら上昇しており、長期的には100年あたり1.44℃の割合で上昇しています。特に1990年代以降、高温となる年が頻出しています。
よくある質問（実際の日本の平均気温は何℃？、長期変化傾向とは？など）
細線（黒）：各年の平均気温の基準値からの偏差、太線（青）：偏差の5年移動平均値、直線（赤）：長期変化傾向。
基準値は1991〜2020年の30年平均値。
正偏差が大きかった年（1〜5位）
①2024年（+1.48℃）、②2023年（+1.29℃）、③2025年（+1.23℃）、④2020年（+0.65℃）、⑤2019年（+0.62℃）
各年の数値
参考
海面水温の長期変化傾向（日本近海）
大気中の温室効果ガス
このページのトップへ
気象庁ホームページについて
```
### SOURCE STAT
```text
統計局ホームページ/人口推計（2026年(令和8年)5月令和2年国勢調査を基準とする確定値、2026年(令和8年)10月概算値） （2026年10月20日公表）
サイト内検索
調達情報
リンク集
お問合せ
文字サイズ等の変更
サイトマップ
English
サイト内検索
調達情報
リンク集
お問合せ
文字サイズ等の変更
サイトマップ
English
ホーム
統計データ
統計データTOP
分野別一覧
公表スケジュール
統計トピックス
miripo（ミクロデータ利用ポータルサイト）
政府統計公表・提供状況
（府省別）（政府統計の
総合窓口へリンク）
結果の利用案内
統計研究研修
統計研究研修TOP
統計研究研修所について
統計研究
統計研修
統計研究研修所リンク集
統計研修受講記
所在地・交通案内
広報・報道
広報・報道TOP
広報資料
報道発表資料
（調査結果の公表を除く）
パブリックコメント
統計センターと独立行政法人評価について
公表期日前統計情報等を共有する者の範囲（PDF）
統計メールニュース
統計局の取組
統計局の取組TOP
統計局等業務案内
統計局の使命と行動指針
統計局のイメージデザイン
統計に関する国際協力
品質管理への取組
所在地・交通案内
採用情報
採用情報TOP
総合職事務系（理工系）
一般職（大卒程度）
一般職（高卒者）
FAQ
FAQTOP
統計データの入手先に
関する問い合わせ
統計局等が作成する統計のQ&A
閉じる
ホーム
統計データ
人口推計
人口推計（2026年（令和8年）5月令和2年国勢調査を基準とする確定値、2026年（令和8年）10月概算値） （2026年10月20日公表）
ここから本文です。
人口推計（2026年（令和8年）5月令和2年国勢調査を基準とする確定値、2026年（令和8年）10月概算値） （2026年10月20日公表）
≪ポイント≫
【2026年（令和8年）10月1日現在（概算値）】
＜総人口＞ 1億2269万人で、前年同月に比べ減少                        ▲53万人       （▲0.43％）
【2026年（令和8年）5月1日現在（令和2年国勢調査を基準とする確定値）】
＜総人口＞ 1億2281万2千人で、前年同月に比べ減少                   ▲53万人          （▲0.43％）
・15歳未満人口は        1326万3千人で、前年同月に比べ減少        ▲35万3千人     （▲2.60％）
・15〜64歳人口は         7332万2千人で、前年同月に比べ減少        ▲20万人         （▲0.27％）
・65歳以上人口は        3622万7千人で、前年同月に比べ増加            2万4千人     （   0.07％）
うち75歳以上人口は    2156万4千人で、前年同月に比べ増加          47万6千人     （   2.26％）
＜日本人人口＞  1億1883万8千人で、前年同月に比べ減少               ▲85万5千人      （▲0.71％）
＜外国人人口＞         397万4千人で、前年同月に比べ増加                32万5千人     （   8.90％）
2026年（令和8年）10月報 （2026年（令和8年）5月令和2年国勢調査を基準とする確定値、2026年（令和8年）10月概算値）（PDF：410KB）
統計表
統計表 （政府統計の総合窓口「e-Stat」掲載の統計表）
※ その他の推計結果
各月1日現在人口 「全国：年齢（5歳階級）、男女別人口」
各年10月1日現在人口 「全国：年齢（各歳）、男女別人口」 「都道府県：年齢（5歳階級）、男女別人口」
国勢調査結果による補間補正人口 「全国人口：各月1日現在人口」 「都道府県人口：各年10月1日現在人口」
国勢調査による基準人口
長期時系列データ
PDF形式のファイルをご覧いただく場合には、Adobe Readerが必要です。Adobe Readerをお持ちでない方は、バナーのリンク先から無料ダウンロードしてください。
ページの先頭へ戻る
〒162-8668 東京都新宿区若松町19番1号 電話 03-5273-2020（代表）
©1996 総務省（法人番号2000012020001）統計局
所在地・交通案内
サイトの利用について
```
### SOURCE ARXIV
```text
[2005.14165] Language Models are Few-Shot Learners
Skip to main content
Search
Submit
Donate
Log in
Search arXiv
Press Enter to search · Advanced search
Computer Science > Computation and Language
arXiv:2005.14165 (cs)
[Submitted on 28 May 2020 (v1), last revised 22 Jul 2020 (this version, v4)]
Title:Language Models are Few-Shot Learners
Authors:Tom B. Brown, Benjamin Mann, Nick Ryder, Melanie Subbiah, Jared Kaplan, Prafulla Dhariwal, Arvind Neelakantan, Pranav Shyam, Girish Sastry, Amanda Askell, Sandhini Agarwal, Ariel Herbert-Voss, Gretchen Krueger, Tom Henighan, Rewon Child, Aditya Ramesh, Daniel M. Ziegler, Jeffrey Wu, Clemens Winter, Christopher Hesse, Mark Chen, Eric Sigler, Mateusz Litwin, Scott Gray, Benjamin Chess, Jack Clark, Christopher Berner, Sam McCandlish, Alec Radford, Ilya Sutskever, Dario Amodei
View a PDF of the paper titled Language Models are Few-Shot Learners, by Tom B. Brown and 30 other authors
View PDF
HTML (experimental)
Abstract:Recent work has demonstrated substantial gains on many NLP tasks and benchmarks by pre-training on a large corpus of text followed by fine-tuning on a specific task. While typically task-agnostic in architecture, this method still requires task-specific fine-tuning datasets of thousands or tens of thousands of examples. By contrast, humans can generally perform a new language task from only a few examples or from simple instructions - something which current NLP systems still largely struggle to do. Here we show that scaling up language models greatly improves task-agnostic, few-shot performance, sometimes even reaching competitiveness with prior state-of-the-art fine-tuning approaches. Specifically, we train GPT-3, an autoregressive language model with 175 billion parameters, 10x more than any previous non-sparse language model, and test its performance in the few-shot setting. For all tasks, GPT-3 is applied without any gradient updates or fine-tuning, with tasks and few-shot demonstrations specified purely via text interaction with the model. GPT-3 achieves strong performance on many NLP datasets, including translation, question-answering, and cloze tasks, as well as several tasks that require on-the-fly reasoning or domain adaptation, such as unscrambling words, using a novel word in a sentence, or performing 3-digit arithmetic. At the same time, we also identify some datasets where GPT-3's few-shot learning still struggles, as well as some datasets where GPT-3 faces methodological issues related to training on large web corpora. Finally, we find that GPT-3 can generate samples of news articles which human evaluators have difficulty distinguishing from articles written by humans. We discuss broader societal impacts of this finding and of GPT-3 in general.
Comments:
40+32 pages
Subjects:
Computation and Language (cs.CL)
Cite as:
arXiv:2005.14165 [cs.CL]
(or
arXiv:2005.14165v4 [cs.CL] for this version)
https://doi.org/10.48550/arXiv.2005.14165
Focus to learn more
arXiv-issued DOI via DataCite
Submission history
From: Tom B Brown [view email]
[v1]
Thu, 28 May 2020 17:29:03 UTC (6,995 KB)
[v2]
Mon, 1 Jun 2020 17:08:53 UTC (6,997 KB)
[v3]
Fri, 5 Jun 2020 02:52:35 UTC (6,998 KB)
[v4]
Wed, 22 Jul 2020 19:47:17 UTC (6,998 KB)
Full-text links:
Access Paper:
View a PDF of the paper titled Language Models are Few-Shot Learners, by Tom B. Brown and 30 other authors
View PDF
HTML (experimental)
TeX Source
view license
Additional Features
Audio Summary
Current browse context:
cs.CL
< prev
|
next >
new
|
recent
| 2020-05
Change to browse by:
cs
References & Citations
SciX
Google Scholar
Semantic Scholar
74 blog links
(what is this?)
DBLP - CS Bibliography
listing | bibtex
Tom B. Brown
Nick Ryder
Jared Kaplan
Prafulla Dhariwal
Arvind Neelakantan
…
export BibTeX citation
Loading...
BibTeX formatted citation
×
loading...
Data provided by:
Bookmark
Bibliographic Tools
Bibliographic and Citation Tools
Bibliographic Explorer Toggle
Bibliographic Explorer (What is the Explorer?)
Connected Papers Toggle
Connected Papers (What is Connected Papers?)
Litmaps Toggle
Litmaps (What is Litmaps?)
scite.ai Toggle
scite Smart Citations (What are Smart Citations?)
Code, Data, Media
Code, Data and Media Associated with this Article
alphaXiv Toggle
alphaXiv (What is alphaXiv?)
Links to Code Toggle
CatalyzeX Code Finder for Papers (What is CatalyzeX?)
DagsHub Toggle
DagsHub (What is DagsHub?)
GotitPub Toggle
Gotit.pub (What is GotitPub?)
Huggingface Toggle
Hugging Face (What is Huggingface?)
ScienceCast Toggle
ScienceCast (What is ScienceCast?)
Demos
Demos
Replicate Toggle
Replicate (What is Replicate?)
Spaces Toggle
Hugging Face Spaces (What is Spaces?)
Spaces Toggle
TXYZ.AI (What is TXYZ.AI?)
Related Papers
Recommenders and Search Tools
Link to Influence Flower
Influence Flower (What are Influence Flowers?)
Core recommender toggle
CORE Recommender (What is CORE?)
Author
Venue
Institution
Topic
About arXivLabs
arXivLabs: experimental projects with community collaborators
arXivLabs is a framework that allows collaborators to develop and share new arXiv features directly on our website.
Both individuals and organizations that work with arXivLabs have embraced and accepted our values of openness, community, excellence, and user data privacy. arXiv is committed to these values and only works with partners that adhere to them.
Have an idea for a project that will add value for arXiv's community? Learn more about arXivLabs.
Which authors of this paper are endorsers? |
Disable MathJax (What is MathJax?)
We gratefully acknowledge support from our major funders,
member institutions, ,
and all contributors.
About ·
Help ·
Contact ·
Subscribe ·
Copyright ·
Privacy ·
Accessibility ·
Operational Status (opens in new tab)
```

## 抜粋（quote 用。変更禁止）
- A1 (JMA): `2025年の日本の平均気温の基準値（1991～2020年の30年平均値）からの偏差は+1.23℃で、1898年の統計開始以降、3番目に高い値となりました。`
- A2 (JMA): `長期的には100年あたり1.44℃の割合で上昇しています`
- A3 (JMA): `①2024年（+1.48℃）、②2023年（+1.29℃）、③2025年（+1.23℃）`
- B1 (STAT): `＜総人口＞ 1億2269万人で、前年同月に比べ減少`
- B2 (STAT): `15歳未満人口は 1326万3千人で、前年同月に比べ減少`
- B3 (STAT): `65歳以上人口は 3622万7千人で、前年同月に比べ増加`
- C1 (ARXIV): `we train GPT-3, an autoregressive language model with 175 billion parameters, 10x more than any previous non-sparse language model`
- C2 (ARXIV): `GPT-3 achieves strong performance on many NLP datasets`

## 生成する24件
| id | type | 抜粋キー |
|---|---|---|
| A-01 | verified | A1 |
| A-02 | verified | A2 |
| A-03 | verified | A3 |
| B-01 | verified | B1 |
| B-02 | verified | B2 |
| B-03 | verified | B3 |
| C-01 | verified | C1 |
| C-02 | verified | C2 |
| A-04 | wrong_number | A1 |
| A-05 | wrong_number | A2 |
| B-04 | wrong_number | B1 |
| B-05 | wrong_number | B3 |
| C-03 | wrong_number | C1 |
| C-04 | wrong_number | C2 |
| A-06 | fake_quote | A1 |
| A-07 | fake_quote | A2 |
| B-06 | fake_quote | B1 |
| B-07 | fake_quote | B2 |
| C-05 | fake_quote | C1 |
| C-06 | fake_quote | C2 |
| N-01 | no_anchor | A1 |
| N-02 | no_anchor | B1 |
| N-03 | no_anchor | C1 |
| N-04 | no_anchor | A2 |
