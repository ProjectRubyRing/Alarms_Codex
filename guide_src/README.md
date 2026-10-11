# 資料の制作ソースと検証記録

利用する資料は、親フォルダーの `CloudWatch_JP1_アラート連携_詳細ガイド.xlsx` と、同名の `.md` です。両方を共通の構造化データから生成しています。

- `content.py`：解説、設定値、59件の公式出典。
- `examples.py`：JSON、コマンド、受信処理の疑似コード。
- `build_guide.py`：Excel、Markdown、構成図を生成。
- `verify_guide.py`：内容の対応、JSON構文、数式保存値、フォント、リンクなどを検査。
- `render_preview.py`：保存されたセル設定とMeiryo UIの字幅を使った描画と文字切れの推定検査。
- `validation/verification_report.json`：検証結果と未確認事項。
- `validation/preview_*.png`：目視確認用の描画。Excel実機の画面キャプチャーではありません。

再生成はWindowsの資料フォルダーで実行します。Python 3.12、XlsxWriter、openpyxl、Pillow、WindowsのMeiryo UIフォントを使用しています。

```powershell
python -B .\guide_src\build_guide.py
python -B .\guide_src\verify_guide.py
```

この作業ではExcel本体のCOM自動起動がエラー `0x80080005` で失敗しました。通常の検証コマンドはその事実を記録し、保存済み数式値を独立した算数モデルで照合します。Excel本体での再計算を成功扱いにはしていません。別環境での検証を追加する場合は、`verify_guide.py` の `--native-excel` オプションがExcel COMを使用します。Excel、pywin32、PyMuPDFが別途必要です。

AWS・JP1の実環境への設定適用、実接続、受入試験は実施していません。資料の「受入試験」を導入環境で行ってください。JP1の導入版とOSは未定のため、13-10版の参照仕様と設計例を区別しています。

作業フォルダーはGitリポジトリではありません。`git diff --check` の代わりに、制作ソースの構文・行末空白、生成物の整合性、文字化け、意図しないファイルの有無を確認しました。
