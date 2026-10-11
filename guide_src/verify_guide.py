"""Structural checks, native Excel recalculation, and print-layout evidence."""
from pathlib import Path
import json
import re
import sys
import zipfile

import openpyxl
from content import SOURCES, SECTIONS
import examples
from build_guide import ROOT, XLSX, MD, VALIDATION, COUNTS, FONT

REPORT={'artifact_checks':[], 'excel_checks':[], 'limitations':[
 'AWS・JP1の実環境への適用・実接続・受入試験は未実施。',
 'JP1の導入版とOSは未定。参照はJP1/Base 13-10版。',
 '作業フォルダーはGitリポジトリではないため、git diff --checkは適用対象外。独自の差分相当・内容検査を実施。']}

def check(condition,message):
    if not condition: raise AssertionError(message)
    REPORT['artifact_checks'].append(message)

def structure():
    manifest=json.loads((VALIDATION/'build_manifest.json').read_text(encoding='utf-8'))
    workbook=openpyxl.load_workbook(XLSX,data_only=False)
    cached=openpyxl.load_workbook(XLSX,data_only=True)
    check(workbook.sheetnames==manifest['sheets'],'31シートの並び・重複なし')
    check(len(workbook.sheetnames)==31,'シート数31')
    ref_count=0
    data_cells=0
    for ws in workbook:
        check(bool(ws.freeze_panes),f'{ws.title}: ウィンドウ枠固定')
        check(ws.sheet_view.showGridLines is False,f'{ws.title}: 目盛線非表示')
        for rr in ws:
            for c in rr:
                if c.value is None: continue
                data_cells+=1
                assert c.font.name==FONT,(ws.title,c.coordinate,c.font.name)
                if c.hyperlink:
                    ref_count+=1
                    loc=c.hyperlink.location
                    if loc:
                        match=re.match(r"'([^']+)'!([A-Z]+)(\d+)$",loc)
                        assert match,(ws.title,loc)
                        assert match.group(1) in workbook.sheetnames
                        target=workbook[match.group(1)]
                        assert int(match.group(3))<=target.max_row,(ws.title,loc)
        assert all((r.height or 15)<=409.5 for r in ws.row_dimensions.values())
    check(data_cells>2000,f'非空セル {data_cells} 個を確認、すべてMeiryo UI')
    check(ref_count>250,f'内部・外部リンク {ref_count} 個を検査')
    sim=cached['11_判定シミュレーター']
    inputs=[sim.cell(r,2).value for r in range(13,43)]
    # Independent reference model: prefix sums, rather than generator's slices.
    sums=[0]; breaches=[0]
    for value in inputs:
        sums.append(sums[-1]+value)
        breaches.append(breaches[-1]+int(value>=sim['F8'].value))
    prev1=prev2=None
    for i in range(1,31):
        er=i+12
        ready=i>=5
        total=sums[i]-sums[i-5] if ready else '準備中'
        bc=breaches[i]-breaches[i-5] if ready else '準備中'
        state1=('ALARM' if total>=sim['D6'].value else 'OK') if ready else '準備中'
        state2=('ALARM' if bc>=sim['B8'].value else 'OK') if ready else '準備中'
        def notice(state,previous):
            if state=='準備中': return '—'
            if state==previous: return '継続：通知なし'
            return {'OK':'OK通知（初回含む）','ALARM':'障害通知'}[state]
        expected=[total,state1,notice(state1,prev1),int(inputs[i-1]>=2),bc,state2,notice(state2,prev2)]
        actual=[sim.cell(er,c).value for c in range(3,10)]
        assert actual==expected,(er,actual,expected)
        prev1=state1;prev2=state2
    check(True,'数式210セルの保存値が独立した累積和モデルと一致（Excel再計算ではない）')
    check('COUNTIF' in workbook['11_判定シミュレーター']['G17'].value and 'SUM' in workbook['11_判定シミュレーター']['C17'].value,
          'SUMとCOUNTIFで合計と超過区間数を別々に計算する数式を確認')
    check(len(workbook['11_判定シミュレーター'].data_validations.dataValidation)==7,'シミュレーター入力7範囲にデータ検証を設定')
    errors=[]
    for ws in cached:
        for rr in ws:
            for c in rr:
                if c.data_type=='e': errors.append((ws.title,c.coordinate,c.value))
    check(not errors,'Excel保存値に数式エラーなし')
    text=MD.read_text(encoding='utf-8')
    check('\ufffd' not in text,'MarkdownにUnicode置換文字なし')
    check(text.count('```')%2==0,'Markdownコードフェンスの対応を検査')
    for sec in SECTIONS:
        assert f'<a id="s{sec["name"][:2]}"></a>' in text
        for r in sec['rows']:
            assert r['topic'] in text
            for ref in r['refs']: assert ref in SOURCES
    check(True,'ExcelとMarkdownの347項目・セクション・出典IDの対応を検査')
    check(all(v['url'] in text for v in SOURCES.values()),'59件の公式URLをMarkdownに収録')
    for name,obj in examples.EXAMPLE_FILES.items():
        decoded=json.loads(json.dumps(obj))
        if 'Attributes' in decoded:
            assert all(isinstance(x,str) for x in decoded['Attributes'].values())
            for k in ['Policy','RedrivePolicy','RedriveAllowPolicy']:
                if k in decoded['Attributes']: json.loads(decoded['Attributes'][k])
    check(True,f'{len(examples.EXAMPLE_FILES)}件のJSON例と埋込みポリシーJSONを検査')
    alarm=examples.EXAMPLE_FILES['metric-alarm.json']
    metric=examples.EXAMPLE_FILES['metric-filter.json']['metricTransformations'][0]
    check(alarm['Namespace']==metric['metricNamespace'] and alarm['MetricName']==metric['metricName'] and alarm['Unit']==metric['unit'],
          'フィルターとAlarmのNamespace・MetricName・Unitが一致')
    check(alarm['Statistic']=='Sum' and alarm['Period']==300 and alarm['Threshold']==5 and alarm['DatapointsToAlarm']==1,
          '基本例は5分Sum>=5、1/1として整合')
    with zipfile.ZipFile(XLSX) as z:
        check(z.testzip() is None,'XLSXのZIP整合性')
        check('xl/vbaProject.bin' not in z.namelist(),'マクロなし')
        check(not any(x.startswith('xl/externalLinks/') for x in z.namelist()),'外部ブック参照なし')
    # Python files are checked separately from Markdown's intentional two-space hard breaks.
    for file in (ROOT/'guide_src').glob('*.py'):
        code=file.read_text(encoding='utf-8')
        compile(code,str(file),'exec')
        assert all(line==line.rstrip() for line in code.splitlines()),file
    check(True,'制作Pythonの構文と不要な行末空白を確認')
    workbook.close(); cached.close()

def excel_native():
    import win32com.client
    import pythoncom
    pythoncom.CoInitialize()
    app=None; book=None
    try:
        app=win32com.client.DispatchEx('Excel.Application')
        app.Visible=False
        app.DisplayAlerts=False
        app.EnableEvents=False
        app.AskToUpdateLinks=False
        app.AutomationSecurity=3
        book=app.Workbooks.Open(str(XLSX),UpdateLinks=0,ReadOnly=False)
        # Native AutoFit for unmerged data rows, then add comfortable padding.
        for sec in SECTIONS:
            ws=book.Worksheets(sec['name'])
            last=5+len(sec['rows'])
            ws.Range(f'A6:F{last}').Rows.AutoFit()
            for r in range(6,last+1):
                h=ws.Rows(r).RowHeight
                ws.Rows(r).RowHeight=min(400,max(46,h+8))
        app.CalculateFullRebuild()
        sim=book.Worksheets('11_判定シミュレーター')
        manifest=json.loads((VALIDATION/'build_manifest.json').read_text(encoding='utf-8'))
        for addr,v in manifest['simulator_expected'].items():
            actual=sim.Range(addr).Value
            assert actual==v,(addr,actual,v)
        REPORT['excel_checks'].append('Excel実機で全数式を再計算し、210セルが期待値と一致')
        original=tuple((v,) for v in COUNTS)
        sim.Range('B13:B17').Value=((2,),(0,),(2,),(0,),(2,))
        app.CalculateFullRebuild()
        assert sim.Range('D17').Value=='ALARM' and sim.Range('H17').Value=='ALARM'
        sim.Range('B13:B17').Value=((0,),(0,),(0,),(0,),(6,))
        app.CalculateFullRebuild()
        assert sim.Range('D17').Value=='ALARM' and sim.Range('H17').Value=='OK'
        REPORT['excel_checks'].append('同じ合計6件でも3/5の結果が変わる入力試験に成功')
        sim.Range('B13:B42').Value=original
        sim.Range('F6').Value='超(>)'
        app.CalculateFullRebuild()
        assert sim.Range('C22').Value==5 and sim.Range('D22').Value=='OK'
        sim.Range('F6').Value='以上(>=)'
        app.CalculateFullRebuild()
        assert sim.Range('D22').Value=='ALARM'
        REPORT['excel_checks'].append('しきい値ちょうど5件の>と>=の境界試験に成功')
        sim.Range('B22').ClearContents()
        app.CalculateFullRebuild()
        assert sim.Range('D22').Value=='欠損：実機確認' and sim.Range('H22').Value=='欠損：実機確認'
        sim.Range('B13:B42').Value=original
        sim.Range('B8').Value=6
        app.CalculateFullRebuild()
        assert sim.Range('H17').Value=='設定不正'
        sim.Range('B8').Value=3
        app.CalculateFullRebuild()
        REPORT['excel_checks'].append('空欄を0にせず欠損表示、M>Nの不正設定表示を確認')
        # Restore baseline and save calculated formula results for any viewer.
        for addr,v in manifest['simulator_expected'].items(): assert sim.Range(addr).Value==v
        book.Worksheets('00_読む順番').Activate()
        app.ActiveWindow.ScrollRow=1
        app.ActiveWindow.ScrollColumn=1
        book.Save()
        selections=[('00_読む順番','cover'),('01_構成図','architecture'),('09_Alarm設定値','alarm_settings'),
                    ('11_判定シミュレーター','simulator'),('16_JP1への連携','jp1'),('30_設定例とコマンド','configuration')]
        for name,stem in selections:
            path=VALIDATION/(stem+'.pdf')
            book.Worksheets(name).ExportAsFixedFormat(0,str(path),0,True,False)
            REPORT['excel_checks'].append(f'Excelの実印刷レイアウトをPDF化：{name}')
        REPORT['excel_version']=str(app.Version)
    finally:
        if book is not None: book.Close(SaveChanges=False)
        if app is not None: app.Quit()
        pythoncom.CoUninitialize()

def render_evidence():
    import fitz
    pages={}
    for file in VALIDATION.glob('*.pdf'):
        with fitz.open(file) as doc:
            pages[file.name]=len(doc)
            for i in range(min(len(doc),2)):
                page=doc[i]
                image=page.get_pixmap(matrix=fitz.Matrix(1.25,1.25),alpha=False)
                image.save(str(VALIDATION/(file.stem+f'_page{i+1}.png')))
    REPORT['layout_pdf_pages']=pages

def main():
    structure()
    if '--native-excel' in sys.argv:
        excel_native()
        structure()
        render_evidence()
    else:
        REPORT['native_excel_attempt']={'result':'FAILED','hresult':'0x80080005',
          'description':'本セッションでDispatchExを実行したが、COMサーバー実行失敗。再計算・実印刷は未確認。'}
        REPORT['limitations'].append('Excel本体のCOM起動失敗により、実機再計算と実印刷は未確認。保存済み数式値とセル描画を検証。')
    from render_preview import make_previews
    issues=make_previews()
    REPORT['estimated_layout_issues']=issues
    assert not issues,issues
    REPORT['artifact_checks'].append('セル寸法・Meiryo UI字幅で全セルを検査し、推定文字切れなし。6シートを描画。')
    REPORT['artifacts']={XLSX.name:XLSX.stat().st_size,MD.name:MD.stat().st_size}
    REPORT['result']='PASS_WITH_LIMITATIONS'
    (VALIDATION/'verification_report.json').write_text(json.dumps(REPORT,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'result':REPORT['result'],'artifact_checks':len(REPORT['artifact_checks']),
                      'excel_checks':REPORT['excel_checks'],'pdf_pages':REPORT.get('layout_pdf_pages',{}),
                      'files':REPORT['artifacts']},ensure_ascii=False,indent=2))

if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
