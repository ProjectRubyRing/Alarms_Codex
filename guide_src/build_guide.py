"""Build the Japanese XLSX and Markdown guide without touching external systems."""
from pathlib import Path
import datetime as dt
import json
import math
import re
import textwrap

from PIL import Image, ImageDraw, ImageFont
import xlsxwriter

from content import CHECKED, TITLE, SOURCES, SECTIONS
import examples  # Registers the configuration examples in SECTIONS.

ROOT = Path(__file__).resolve().parents[1]
VALIDATION = ROOT / 'guide_src' / 'validation'
VALIDATION.mkdir(exist_ok=True)
STEM = 'CloudWatch_JP1_アラート連携_詳細ガイド'
XLSX = ROOT / (STEM + '.xlsx')
MD = ROOT / (STEM + '.md')
FONT = 'Meiryo UI'
FONT_PATH = 'C:/Windows/Fonts/meiryo.ttc'
FONT_BOLD = 'C:/Windows/Fonts/meiryob.ttc'
INK = '#242424'
MID = '#656565'
LIGHT = '#F2F2F2'
WHITE = '#FFFFFF'
COL_WIDTHS = [8, 26, 54, 58, 52, 12]
COUNTS = [0,0,0,0,0,1,0,2,1,1,4,4,0,0,0,0,0,0,0,1,2,2,0,2,0,0,0,0,0,0]

MERMAID = '''flowchart LR
  subgraph A["業務アカウントA・東京リージョン（例）"]
    APP[アプリのログ] --> LOG[CloudWatch Logs]
    LOG --> MF[メトリクスフィルター]
    MF --> MET[CloudWatchメトリクス]
    MET --> AL[事前作成したAlarm]
    AL -->|状態遷移| SNS[SNSトピック]
  end
  subgraph B["共通運用アカウントB"]
    Q[SQSメインキュー] -->|EC2がpollして取得| EC[EC2受信・変換アプリ]
    EC --> BASE[EC2上のJP1/Base]
    DD[SNS配信失敗用DLQ]
    PD[EC2処理失敗用DLQ]
    Q -. 受信回数の上限超過 .-> PD
  end
  SNS -->|確認済みSQS購読| Q
  SNS -. 購読の配信失敗 .-> DD
  BASE -->|JP1イベント転送・代表TCP 20098| IM[JP1/IM側イベントサーバーと運用画面]
  EC -. 任意・AssumeRoleで参考原文取得 .-> LOG
  classDef gray fill:#eeeeee,stroke:#444444,color:#111111;
  classDef dark fill:#333333,stroke:#111111,color:#ffffff;
  class APP,LOG,MF,MET,Q,EC,BASE,DD,PD,IM gray;
  class AL,SNS dark;
'''

def pfont(size=25, bold=False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT_PATH, size, index=2)

def wrapped(text, font, max_width):
    result=[]
    for para in str(text).split('\n'):
        if not para:
            result.append('')
            continue
        line=''
        for ch in para:
            if line and font.getlength(line+ch)>max_width:
                result.append(line)
                line=ch
            else:
                line+=ch
        result.append(line)
    return result or ['']

def draw_text(draw, box, text, size=25, bold=False, color=INK, center=True):
    x1,y1,x2,y2=box
    f=pfont(size,bold)
    lines=wrapped(text,f,x2-x1-24)
    lh=size*1.52
    y=y1+(y2-y1-len(lines)*lh)/2 if center else y1+10
    for line in lines:
        x=(x1+x2-f.getlength(line))/2 if center else x1+12
        draw.text((x,y),line,font=f,fill=color)
        y+=lh

def architecture_png():
    im=Image.new('RGB',(1680,1060),'white')
    d=ImageDraw.Draw(im)
    d.rectangle((0,0,1680,94),fill=INK)
    draw_text(d,(45,8,1625,88),'文章 → 数字 → 状態の知らせ → JP1イベント',36,True,WHITE,False)
    d.rounded_rectangle((42,124,1638,412),radius=15,fill='#F2F2F2',outline='#A0A0A0',width=2)
    draw_text(d,(64,136,1550,198),'業務アカウント A  ｜  ap-northeast-1（東京）の例',25,True,INK,False)
    nodes=[(82,219,332,347,'CloudWatch Logs\n元のログを保存'),
           (390,219,635,347,'メトリクスフィルター\n一致したら「1」'),
           (695,219,940,347,'CloudWatch\nメトリクス（件数）'),
           (999,219,1244,347,'CloudWatch\nAlarm：状態を判定'),
           (1302,219,1595,347,'SNSトピック\n状態変化を配信')]
    for x1,y1,x2,y2,t in nodes:
        dark='Alarm' in t or 'SNS' in t
        d.rounded_rectangle((x1,y1,x2,y2),radius=7,fill=INK if dark else WHITE,outline=INK,width=2)
        draw_text(d,(x1,y1,x2,y2),t,24,True,WHITE if dark else INK)
    def arrow(x1,y1,x2,y2,color=INK,width=4):
        d.line((x1,y1,x2,y2),fill=color,width=width)
        a=math.atan2(y2-y1,x2-x1)
        pts=[(x2,y2),(x2-16*math.cos(a-.4),y2-16*math.sin(a-.4)),(x2-16*math.cos(a+.4),y2-16*math.sin(a+.4))]
        d.polygon(pts,fill=color)
    for left,right in zip(nodes,nodes[1:]): arrow(left[2]+5,283,right[0]-7,283)
    draw_text(d,(68,351,1550,400),'例：1件ずつ加算 → 直近5分の Sum >= 5 → OK から ALARM へ',24,False,INK,False)
    d.rounded_rectangle((454,478,1638,792),radius=15,fill='#F2F2F2',outline='#A0A0A0',width=2)
    draw_text(d,(474,490,1600,541),'共通運用アカウント B  ｜  SQS所有側がSNS購読を作成する例',25,True,INK,False)
    d.rounded_rectangle((484,562,1208,738),radius=9,fill=WHITE,outline='#999999',width=2)
    draw_text(d,(500,565,1180,604),'通知サーバー EC2（Windows／Linuxは導入時に決定）',21,False,INK,False)
    for b,t in [((514,613,782,712),'JP1/Base\n到達確認付き送信'),((852,613,1178,712),'受信・変換アプリ\n検証／重複対策／台帳'),((1302,574,1595,711),'SQSメインキュー\n通知を一時保管')]:
        d.rounded_rectangle(b,radius=6,fill=LIGHT,outline=INK,width=2)
        draw_text(d,b,t,23,True)
    arrow(1450,352,1450,568)
    d.rectangle((1223,424,1620,465),fill=WHITE)
    draw_text(d,(1223,420,1620,469),'購読 ＋ 両側のアクセス許可',20,True)
    arrow(1296,659,1184,659)
    arrow(846,659,789,659)
    draw_text(d,(866,742,1600,784),'EC2がSQSへ取りに行く。JP1到達確認・記録の後に削除。',21,False)
    d.rounded_rectangle((42,478,406,792),radius=15,fill=WHITE,outline='#A0A0A0',width=2)
    draw_text(d,(56,490,390,550),'JP1の運用環境',26,True)
    d.rounded_rectangle((76,596,370,733),radius=7,fill=INK,outline=INK,width=2)
    draw_text(d,(76,596,370,733),'JP1/IM側\nイベントサーバー\n運用担当者の画面',24,True,WHITE)
    arrow(508,659,376,659)
    draw_text(d,(389,564,514,633),'代表\nTCP 20098',16,True)
    for b,t in [((42,830,815,930),'SNS配信失敗用DLQ：メインSQSへ渡せなかった通知'),((853,830,1638,930),'EC2処理失敗用DLQ：受信後、繰り返しても処理できない通知')]:
        d.rounded_rectangle(b,radius=8,fill=LIGHT,outline=INK,width=2)
        draw_text(d,b,t,24,True)
    draw_text(d,(42,947,1638,1035),'元ログ本文は通常のAlarm通知には含まれない。必要ならEC2からAのLogsへ追加検索する。\nJP1への到達、IMの画面表示、人の確認・対処完了は別の確認段階。',24,False,INK,False)
    path=VALIDATION/'architecture.png'
    im.save(path)
    return path

def source_links(keys):
    return ' '.join(f'[{key}]({SOURCES[key]["url"]})' for key in keys)

def make_markdown():
    out=[f'# {TITLE}', '', f'確認基準日：**{CHECKED}**。Excel版と同じ説明・設定例を収録。', '',
         '業務アカウントのログを数え、CloudWatch Alarmの状態変化をSNSと共通運用SQS経由でJP1へ届ける構成を説明します。JP1のバージョンと通知EC2のOSは未定として、Windows／Linuxの差を併記しています。', '',
         '**資料の区分**：公式仕様には出典を付けています。しきい値、保持期間、ID、ホスト名、処理台帳などは設計例です。AWS・JP1への実接続・設定適用・受入試験は実施していません。', '',
         '最初に押さえる点は、Alarmを事前作成すること、数える単位は一致ログイベントであること、通常のAlarm通知に元ログ本文は含まれないこと、通知は主に状態変化で行われること、SQSは処理成功後に削除することです。', '',
         '## 目次', '', '[構成図](#architecture) ／ [数値シミュレーターの読み方](#simulator) ／ [公式出典](#sources)', '']
    for sec in SECTIONS:
        num=sec['name'].split('_')[0]
        out.append(f'- [{num} {sec["title"]}](#s{num})')
    out += ['', '<a id="architecture"></a>', '## 01 構成図', '', '```mermaid', MERMAID.rstrip(), '```', '',
            '実線は基本の通知経路です。EC2のログ追加検索と2種類のDLQは目的を分けて設計します。SNS配信DLQは購読所有者と同じアカウント・リージョンに置きます。本例はB所有の購読です。 '+source_links(['S18','S24']), '',
            '時刻とIDはすべて説明用です。A=111111111111、B=222222222222、東京リージョンを例にしています。', '']
    for sec in SECTIONS:
        num=sec['name'].split('_')[0]
        out += [f'<a id="s{num}"></a>',f'## {num} {sec["title"]}','',sec['lead'],'']
        for i,r in enumerate(sec['rows'],1):
            out += [f'### {num}-{i:02d} {r["topic"]}','',r['explanation'],'']
            if r['example']:
                out += ['**設定値・具体例**','', *[line+'  ' for line in r['example'].splitlines()], '']
            if r['caution']:
                out += [f'**注意・判断**：{r["caution"]}','']
            if r['refs']: out += ['根拠：'+source_links(r['refs']),'']
        for c in sec['codes']:
            out += [f'### 設定例：{c["title"]}','',f'```{c["lang"]}',c['text'],'```','']
            if c['refs']: out += ['根拠：'+source_links(c['refs']),'']
    out += ['<a id="simulator"></a>','## 11 Excelの数値シミュレーター','',
            'Excelの「11_判定シミュレーター」で、毎分件数・集計幅・合計のしきい値・M/Nを編集できます。数式とグラフで、「5分合計」と「1分区間のM/N判定」の違いを比較します。入力欄は薄いグレーと枠線で示しています。', '',
            '**再現範囲**：等間隔で完全に到着したデータに対する算数と、単純な状態遷移です。CloudWatchの遅延到着、欠損時の追加取得、ウォームアップ、配信再試行は再現しません。空欄を0に置き換えず「欠損：実機確認」と表示します。初期データ不足は準備中です。実際の通知時刻や初期評価はAWSの履歴で確認してください。', '',
            '| 毎分件数（5区間） | 5分合計>=5 | 各分>=2が3/5 |',
            '|---|---|---|','| 1,0,2,1,1 | 5で成立 | 1区間のため未達 |',
            '| 2,0,2,0,2 | 6で成立 | 3区間で成立 |','| 0,0,0,0,6 | 6で成立 | 1区間のため未達 |','',
            '数式による通知表示はALARMまたはOKへの変化を示します。OKActionsを設定した場合、初回OKも通知対象になり得ます。 '+source_links(['S11','S13','S14']), '',
            '<a id="sources"></a>', '## 29 公式出典一覧', '',
            f'全資料の確認日：{CHECKED}。AWSは現行ドキュメント、JP1は参照版を明記した公式マニュアルを使用。提供リージョンや実導入版の保証とは区別します。', '']
    for k,v in SOURCES.items():
        out += [f'- **{k}** [{v["title"]}]({v["url"]}) — {v["scope"]}。']
    out += ['', '## この成果物の検証範囲', '',
            'Excel・Markdownは同じ構造化データから生成しています。参照ID、JSON例の構文、数式の保存値と独立した算数モデルの照合、内部リンク、フォント、セル設定を検査し、セル設定に基づく描画で表示を確認しました。結果は制作ソース配下の検証記録に保存しています。Excel本体の自動起動はCOMエラー0x80080005で失敗したため、Excel本体による再計算・実印刷は未確認です。描画確認はExcel実機の画面ではありません。AWS設定値の実アカウントでの受理、IAM/KMSの実効権限、SNS/SQS配送、JP1送受信・文字コード・表示は、導入環境で受入試験を実施してください。', '']
    # Markdown intentional hard breaks use two spaces; all other lines remain trimmed.
    MD.write_text('\n'.join(out),encoding='utf-8',newline='\n')

def make_workbook(diagram):
    wb=xlsxwriter.Workbook(XLSX,{'strings_to_urls':False,'strings_to_formulas':False})
    wb.set_properties({'title':TITLE,'subject':'AWSログ監視からJP1統合運用への連携',
                       'author':'Technical Documentation','comments':f'公式情報確認日 {CHECKED}。実環境試験は未実施。'})
    wb.formats[0].set_font_name(FONT)
    wb.formats[0].set_font_size(10.5)
    def fmt(**extra):
        return wb.add_format({'font_name':FONT,'font_size':10.5,'font_color':INK,**extra})
    title=fmt(font_size=19,bold=True,bg_color=INK,font_color=WHITE,valign='vcenter')
    lead=fmt(font_size=11,text_wrap=True,valign='vcenter',bg_color=LIGHT)
    header=fmt(bold=True,bg_color='#444444',font_color=WHITE,text_wrap=True,valign='vcenter',border=1,border_color='#777777')
    meta=fmt(font_size=9,font_color=MID,text_wrap=True,valign='vcenter')
    link=fmt(font_size=9,font_color=INK,underline=1,text_wrap=True,valign='top')
    cell=[fmt(bg_color=color,text_wrap=True,valign='top',bottom=1,bottom_color='#D9D9D9') for color in [WHITE,'#F6F6F6']]
    topic=[fmt(bg_color=color,text_wrap=True,valign='top',bold=True,bottom=1,bottom_color='#D9D9D9') for color in [WHITE,'#F6F6F6']]
    idfmt=[fmt(bg_color=color,font_size=9,font_color=MID,valign='top',bottom=1,bottom_color='#D9D9D9') for color in [WHITE,'#F6F6F6']]
    sourcefmt=[fmt(bg_color=color,font_size=9,font_color=INK,underline=1,valign='top',text_wrap=True,bottom=1,bottom_color='#D9D9D9') for color in [WHITE,'#F6F6F6']]
    codefmt=fmt(font_size=10,text_wrap=True,valign='top',bg_color='#F1F1F1')
    codehead=fmt(bold=True,font_color=WHITE,bg_color='#555555',text_wrap=True,valign='vcenter')
    hfont=pfont(14)
    stats={'sheets':[], 'rows':sum(len(x['rows']) for x in SECTIONS),'sources':len(SOURCES)}
    source_rows={k:i+6 for i,k in enumerate(SOURCES)}
    def common(ws,title_text,lead_text,widths=COL_WIDTHS):
        ws.hide_gridlines(2)
        ws.set_zoom(85)
        ws.set_tab_color('#7A7A7A')
        for i,w in enumerate(widths): ws.set_column(i,i,w)
        last=len(widths)-1
        ws.merge_range(0,0,0,last,title_text,title)
        ws.set_row(0,39)
        ws.merge_range(1,0,1,last,lead_text,lead)
        ws.set_row(1,51)
        ws.write_url(2,0,"internal:'00_読む順番'!A1",link,'目次へ')
        ws.merge_range(2,1,2,last,f'公式情報確認：{CHECKED} ｜ 仕様・例・未決事項を区別 ｜ JP1版・OSは導入時に確定',meta)
        ws.set_row(2,28)
        ws.set_row(3,8)
        ws.set_landscape()
        ws.set_paper(8) # A3: keep long Japanese explanations legible.
        ws.fit_to_pages(1,0)
        ws.set_margins(.25,.25,.4,.4)
        ws.set_header('&L&"Meiryo UI"&9CloudWatch → JP1/IM&R&"Meiryo UI"&9'+CHECKED)
        ws.set_footer('&L&"Meiryo UI"&8設計例。実環境試験は別途実施。&R&"Meiryo UI"&8&P / &N')
        ws.repeat_rows(0,4)
        ws.freeze_panes(5,2)
        stats['sheets'].append(ws.name)
    def body_height(values,widths=COL_WIDTHS):
        maxlines=max(len(wrapped(str(v),hfont,max(25,w*7-14))) for v,w in zip(values,widths))
        return max(46,min(390,maxlines*15+14))
    def table_header(ws,labels):
        for c,t in enumerate(labels): ws.write(4,c,t,header)
        ws.set_row(4,28)

    # Create worksheets in reading order before filling internal links.
    names=['00_読む順番','01_構成図']+[x['name'] for x in SECTIONS if int(x['name'][:2])<11]+['11_判定シミュレーター']+[x['name'] for x in SECTIONS if 11<int(x['name'][:2])<29]+['29_公式出典','30_設定例とコマンド']
    sheets={n:wb.add_worksheet(n) for n in names}
    cover=sheets['00_読む順番']
    common(cover,'AWS のログ監視を、JP1 の運用につなぐ',
           'CloudWatch Logs → メトリクスフィルター → CloudWatch Alarm → SNS → 共通運用SQS → EC2 → JP1/IM\n動作原理、設定可能値、具体例、歴史、障害対応、受入試験を一冊に。')
    cover.merge_range('A5:F5',f'31シート  ／  {stats["rows"]}項目  ／  {len(SOURCES)}件の公式資料  ／  確認日 {CHECKED}',header)
    cover.set_row(4,31)
    intro=[
      ('最初に押さえること','Alarmは事前に作成する。しきい値を満たすと、既存Alarmの状態が変わる。'),
      ('数えるもの','metricValue=1なら、一致したログイベントを数える。同じ文中のERRORの出現回数ではない。'),
      ('本文を届けるには','通常のAlarm通知に元ログ本文は含まれない。参考原文の取得処理か、原文転送の別経路を追加する。'),
      ('通知と受領','SNSは配り、SQSは預かる。EC2が取得・変換し、決めた成功地点を確認してからSQSを削除する。'),
      ('この資料の前提','業務A・運用B、東京の同一リージョンが基本例。JP1版・OSは未定。JP1/Baseの説明は13-10版を参照。'),
      ('例と検証の区別','値・ID・時刻は説明用。AWS／JP1への設定反映や実接続試験は未実施。実環境の受入項目を別に用意した。')]
    for r,(t,desc) in enumerate(intro,6):
        cover.merge_range(r,0,r,1,t,topic[r%2])
        cover.merge_range(r,2,r,5,desc,cell[r%2])
        cover.set_row(r,42)
    cover.merge_range('A14:F14','読む順番  ｜  下線のタイトルをクリックすると移動できます',header)
    cover.set_row(13,29)
    descriptions={x['name']:(x['title'],x['lead']) for x in SECTIONS}
    descriptions.update({'01_構成図':('全体構成と責任の境界','アカウントの境界、データの変換点、2種類の退避先を確認。'),
                         '11_判定シミュレーター':('件数を変えて判定を試す','入力欄と数式で5分合計とM/Nの違いを体験。実AWS評価の完全な再現ではない。'),
                         '29_公式出典':('公式資料の一覧','参照番号から仕様の根拠へ移動。JP1の参照版も明記。')})
    for r,n in enumerate(names[1:],14):
        t,desc=descriptions[n]
        cover.write(r,0,n[:2],idfmt[r%2])
        cover.merge_range(r,1,r,2,t,sourcefmt[r%2])
        cover.write_url(r,1,f"internal:'{n}'!A1",sourcefmt[r%2],t)
        cover.merge_range(r,3,r,5,desc,cell[r%2])
        cover.set_row(r,42)
    cover.print_area(0,0,44,5)
    cover.freeze_panes(14,0)

    ws=sheets['01_構成図']
    common(ws,'全体構成：どの時点で何に変わるか','本文を含むログ → 集計した数値 → 状態変化のJSON → JP1イベント。各矢印の意味と責任を分ける。')
    ws.merge_range('A5:F5','基本構成  ｜  矢印は通知データの流れ。EC2はSQSへpollして取得する。',header)
    for r in range(5,35): ws.set_row(r,22)
    ws.insert_image('A6',str(diagram),{'x_scale':.82,'y_scale':.82,'object_position':1})
    notes=[('アカウントA','ログ、フィルター、メトリクス、Alarm、SNSを業務側で管理。'),
           ('アカウントB','SQS、購読、受信EC2、送信台帳、JP1連携を共通運用側で管理。'),
           ('JP1運用環境','IM側イベントサーバーへの登録と、画面表示・自動アクション・人の対応を管理。'),
           ('任意の追加経路','EC2からAのLogsへAssumeRole等で参考原文を取得。標準Alarm通知からは原文を復元できない。'),
           ('SNS配信DLQの所有者','本例はBが購読を作成しOwner=B。SNS配信DLQもB・同一リージョン。Topic ARNの見た目だけで決めない。'),
           ('成功の境界','SQSに入った、EC2が受信した、JP1に登録された、画面に表示された、人が読んだ、は別の証跡。')]
    for r,(t,v) in enumerate(notes,36):
        ws.merge_range(r,0,r,1,t,topic[r%2]); ws.merge_range(r,2,r,5,v,cell[r%2]); ws.set_row(r,42)
    ws.print_area(0,0,41,5)
    ws.set_h_pagebreaks([36])

    for sec in SECTIONS:
        ws=sheets[sec['name']]
        common(ws,sec['title'],sec['lead'])
        table_header(ws,['ID','項目・問い','やさしい説明／動作原理','設定可能値・具体例','注意点／設計判断','公式出典'])
        r=5
        for i,entry in enumerate(sec['rows'],1):
            vals=[f'{sec["name"][:2]}-{i:02d}',entry['topic'],entry['explanation'],entry['example'],entry['caution'],'\n'.join(entry['refs'])]
            for c,val in enumerate(vals):
                f=idfmt[i%2] if c==0 else topic[i%2] if c==1 else cell[i%2]
                if c==5 and entry['refs']:
                    key=entry['refs'][0]
                    ws.write_url(r,c,f"internal:'29_公式出典'!A{source_rows[key]}",sourcefmt[i%2],val)
                else: ws.write_string(r,c,str(val),f)
            ws.set_row(r,body_height(vals))
            r+=1
        ws.autofilter(4,0,r-1,5)
        for c in sec['codes']:
            r+=1
            ws.merge_range(r,0,r,5,c['title'],codehead); ws.set_row(r,31); r+=1
            for line in c['text'].split('\n'):
                ws.merge_range(r,0,r,5,line or ' ',codefmt)
                height=max(18,len(wrapped(line,pfont(13),1400))*14+7)
                ws.set_row(r,min(390,height)); r+=1
            refs='根拠：'+' / '.join(c['refs'])+'  ｜  架空のID・名前を使った学習／設計例。実環境で未実行。'
            ws.merge_range(r,0,r,5,refs,meta); ws.set_row(r,26); r+=1
        ws.print_area(0,0,r,5)

    ws=sheets['29_公式出典']
    common(ws,'公式出典：仕様を確認できるページ',f'確認日 {CHECKED}。出典IDは本文と共通。Webドキュメントは更新されるため、導入時にも対象版を確認する。')
    table_header(ws,['出典ID','提供元・参照版','資料名','確認した仕様','URL','開く'])
    for r,(key,v) in enumerate(SOURCES.items(),5):
        provider='日立／JP1' if 'hitachi' in v['url'] else 'AWS'
        vals=[key,provider,v['title'],v['scope'],v['url'],'公式ページ']
        for c,t in enumerate(vals):
            if c==5: ws.write_url(r,c,v['url'],sourcefmt[r%2],t)
            else: ws.write_string(r,c,t,cell[r%2])
        ws.set_row(r,body_height(vals))
    ws.autofilter(4,0,4+len(SOURCES),5)
    ws.print_area(0,0,5+len(SOURCES),5)

    # Editable educational simulator, with cached results for non-calculating viewers.
    ws=sheets['11_判定シミュレーター']
    common(ws,'件数を変える：5分合計と M / N を比べる',
           '薄いグレーの入力セルを編集。完全な毎分データを使った学習用モデル。欠損の追加取得・配送遅延・初期評価は実AWSと異なる。',
           [13,14,17,18,27,16,17,20,29])
    ws.freeze_panes(12,2)
    inputfmt=fmt(bg_color='#DDDDDD',bold=True,border=1,border_color='#444444',align='center',num_format='0')
    label=fmt(bold=True,text_wrap=True,valign='vcenter')
    simcell=fmt(text_wrap=True,valign='vcenter',border=1,border_color='#D4D4D4',align='center')
    for r in [4,6,8,9,10]: ws.set_row(r,22)
    for r in [5,7]: ws.set_row(r,32)
    ws.write('A6','集計幅（分）',label); ws.write('B6',5,inputfmt)
    ws.write('C6','合計しきい値',label); ws.write('D6',5,inputfmt)
    ws.write('E6','合計の比較方法',label); ws.write('F6','以上(>=)',inputfmt)
    ws.merge_range('G6:I6','入力：1分ずつの対象ログ件数',meta)
    ws.write('A8','M（異常区間数）',label); ws.write('B8',3,inputfmt)
    ws.write('C8','N（評価区間数）',label); ws.write('D8',5,inputfmt)
    ws.write('E8','各1分のしきい値（>=）',label); ws.write('F8',2,inputfmt)
    ws.merge_range('G8:I8','MはN以下。N=5は合計5件という意味ではない。',meta)
    ws.merge_range('A10:I10','空欄は0ではないため「欠損：実機確認」。初期のデータ不足は「準備中」。OK通知は初回も対象になり得る。',meta)
    ws.merge_range('A11:I11','下の時刻は各1分区間の開始時刻。集計は各区間の終了後を想定した算数であり、実際の通知時刻ではない。',meta)
    labels=['区間開始','件数（入力）','指定幅の合計','合計の判定','合計の通知表示','各分の条件','超過区間数','M/Nの判定','M/Nの通知表示']
    for c,t in enumerate(labels): ws.write(11,c,t,header)
    ws.set_row(11,38)
    ws.data_validation('B6',{'validate':'integer','criteria':'between','minimum':1,'maximum':10,'input_title':'集計幅','input_message':'1〜10分の整数'})
    ws.data_validation('D6',{'validate':'integer','criteria':'between','minimum':0,'maximum':1000000})
    ws.data_validation('F6',{'validate':'list','source':['以上(>=)','超(>)']})
    ws.data_validation('B8',{'validate':'integer','criteria':'between','minimum':1,'maximum':'=$D$8'})
    ws.data_validation('D8',{'validate':'integer','criteria':'between','minimum':1,'maximum':10})
    ws.data_validation('F8',{'validate':'integer','criteria':'between','minimum':0,'maximum':1000000})
    ws.data_validation('B13:B42',{'validate':'integer','criteria':'between','minimum':0,'maximum':1000000,'ignore_blank':True})
    expected={}
    prev_sum='準備中'; prev_mn='準備中'
    for i,value in enumerate(COUNTS):
        er=i+13; r=er-1
        ws.write(r,0,f'09:{i:02d}',simcell)
        ws.write_number(r,1,value,inputfmt)
        rng=f'INDEX($B:$B,MAX(13,ROW()-$B$6+1)):B{er}'
        mnrng=f'INDEX($B:$B,MAX(13,ROW()-$D$8+1)):B{er}'
        complete=i>=4
        total=sum(COUNTS[i-4:i+1]) if complete else '準備中'
        sumstate=('ALARM' if total>=5 else 'OK') if complete else '準備中'
        exceed=sum(x>=2 for x in COUNTS[i-4:i+1]) if complete else '準備中'
        mnstate=('ALARM' if exceed>=3 else 'OK') if complete else '準備中'
        def notice(state,prev):
            if state not in ['OK','ALARM']: return '—'
            if state==prev: return '継続：通知なし'
            return '障害通知' if state=='ALARM' else 'OK通知（初回含む）'
        forms=[
          (2,f'=IF(ROWS($B$13:B{er})<$B$6,"準備中",IF(COUNT({rng})<$B$6,"欠損：実機確認",SUM({rng})))',total),
          (3,f'=IF(ISNUMBER(C{er}),IF(IF($F$6="以上(>=)",C{er}>=$D$6,C{er}>$D$6),"ALARM","OK"),C{er})',sumstate),
          (4,f'=IF(OR(D{er}="ALARM",D{er}="OK"),IF(D{er}<>D{er-1},IF(D{er}="ALARM","障害通知","OK通知（初回含む）"),"継続：通知なし"),"—")',notice(sumstate,prev_sum)),
          (5,f'=IF(B{er}="","欠損",IF(B{er}>=$F$8,1,0))',int(value>=2)),
          (6,f'=IF(OR($B$8>$D$8,$B$8<1),"設定不正",IF(ROWS($B$13:B{er})<$D$8,"準備中",IF(COUNT({mnrng})<$D$8,"欠損：実機確認",COUNTIF({mnrng},">="&$F$8))))',exceed),
          (7,f'=IF(ISNUMBER(G{er}),IF(G{er}>=$B$8,"ALARM","OK"),G{er})',mnstate),
          (8,f'=IF(OR(H{er}="ALARM",H{er}="OK"),IF(H{er}<>H{er-1},IF(H{er}="ALARM","障害通知","OK通知（初回含む）"),"継続：通知なし"),"—")',notice(mnstate,prev_mn))]
        for c,f,v in forms:
            ws.write_formula(r,c,f,simcell,v)
            expected[xlsxwriter.utility.xl_rowcol_to_cell(r,c)]=v
        prev_sum=sumstate; prev_mn=mnstate
        ws.set_row(r,31)
    ws.conditional_format('D13:D42',{'type':'text','criteria':'containing','value':'ALARM','format':fmt(bg_color='#444444',font_color=WHITE,bold=True)})
    ws.conditional_format('H13:H42',{'type':'text','criteria':'containing','value':'ALARM','format':fmt(bg_color='#444444',font_color=WHITE,bold=True)})
    chart=wb.add_chart({'type':'line'})
    chart.add_series({'name':'毎分件数','categories':"='11_判定シミュレーター'!$A$13:$A$42",'values':"='11_判定シミュレーター'!$B$13:$B$42",'line':{'color':'#888888','width':1.5}})
    chart.add_series({'name':'直近の合計','categories':"='11_判定シミュレーター'!$A$13:$A$42",'values':"='11_判定シミュレーター'!$C$13:$C$42",'line':{'color':'#222222','width':2.25}})
    chart.set_title({'name':'毎分の件数と直近の合計','name_font':{'name':FONT,'size':14,'color':INK}})
    chart.set_x_axis({'name':'区間開始時刻','num_font':{'name':FONT,'size':9},'name_font':{'name':FONT,'size':10},'label_interval':3})
    chart.set_y_axis({'name':'件数','min':0,'num_font':{'name':FONT,'size':9},'name_font':{'name':FONT,'size':10},'major_gridlines':{'visible':True,'line':{'color':'#DDDDDD'}}})
    chart.set_legend({'position':'bottom','font':{'name':FONT,'size':10}})
    chart.set_chartarea({'border':{'none':True},'fill':{'color':WHITE}})
    chart.set_plotarea({'border':{'none':True},'fill':{'color':WHITE}})
    chart.set_size({'width':1180,'height':360})
    ws.insert_chart('A45',chart)
    ws.merge_range('A64:I65','判定式の原理：合計はSUM、異常区間数はCOUNTIF、状態が変わったときだけ通知表示。実AWSの欠損補完・到着遅延は対象外。',meta)
    ws.print_area(0,0,64,8)
    ws.repeat_rows(0,11)
    ws.set_h_pagebreaks([43])
    wb.close()
    stats['sheets']=names
    stats['sheet_count']=len(names)
    stats['simulator_expected']=expected
    (VALIDATION/'build_manifest.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')

def main():
    for sec in SECTIONS:
        for item in sec['rows']+sec['codes']:
            for ref in item['refs']:
                assert ref in SOURCES,(sec['name'],ref)
    make_markdown()
    make_workbook(architecture_png())
    print(json.dumps({'xlsx':str(XLSX),'markdown':str(MD),'sheets':31,
                      'topics':sum(len(x['rows']) for x in SECTIONS),'sources':len(SOURCES)},ensure_ascii=False))

if __name__=='__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    main()
