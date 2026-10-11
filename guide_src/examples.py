"""Reviewable examples for the guide; this module never calls AWS or JP1."""
import json
from content import section, row, code

A='111111111111'
B='222222222222'
REGION='ap-northeast-1'
TOPIC=f'arn:aws:sns:{REGION}:{A}:prod-ops-alerts'
QUEUE=f'arn:aws:sqs:{REGION}:{B}:jp1-alert-main'
PROCESS_DLQ=f'arn:aws:sqs:{REGION}:{B}:jp1-alert-processing-dlq'
DELIVERY_DLQ=f'arn:aws:sqs:{REGION}:{B}:jp1-alert-delivery-dlq'
ALARM=f'arn:aws:cloudwatch:{REGION}:{A}:alarm:prod-order-e1001-5m-ge5'
BRIDGE=f'arn:aws:iam::{B}:role/AlertBridgeRole'
ADMIN=f'arn:aws:iam::{B}:role/OpsSubscriptionAdmin'
READER=f'arn:aws:iam::{A}:role/AlertLogReadRole'
EXAMPLE_FILES={}

s=section('30_設定例とコマンド','設定例：JSONとコマンドを対応させる','すべて架空のID・名前を使った設定例。ファイル名は保存する場合の例。AWS CLI v2と適切な認証・権限を事前準備する。自動適用スクリプトではない。')
row(s,'例を使う前の置換','アカウントID、リージョン、ARN、ロググループ、ロール、JP1イベントサーバーを実環境へ置換する。既存ポリシーとはStatementをレビューして統合する。','A：workload-aプロファイル\nB：operations-bプロファイル\naws sts get-caller-identityで利用アカウントを確認','これらのプロファイル名は利用者が作る説明用の名前。秘密情報を資料へ書き込まない。')
row(s,'適用順序と暗号化','DLQ→メインSQS→SNS／ポリシー→Bから購読→受信EC2→Logs／フィルター→Alarm。SQSの最小例はSSE-SQSを明示し、SSE-KMSの追加例は別に示す。','KMSを採用する場合はKey ARNとキーポリシーを先に準備して、SqsManagedSseEnabledとKmsMasterKeyIdを同時に指定しない。','例は接続部分を説明する設定断片。JP1のforwardやIM側の表示定義など、導入版と既存環境に依存する定義は完成済みとは扱わない。','S25 S39')

def jfile(name, title, obj, refs):
    EXAMPLE_FILES[name]=obj
    code(s,f'{name} — {title}',json.dumps(obj,ensure_ascii=False,indent=2),'json',refs)

jfile('metric-filter.json','一致1件を1として数値化',{
 'logGroupName':'/app/prod/order','filterName':'count-order-e1001',
 'filterPattern':'{ $.level = "ERROR" && $.code = "E1001" }',
 'metricTransformations':[{'metricNamespace':'Ops/Order','metricName':'E1001Count',
  'metricValue':'1','defaultValue':0,'unit':'Count'}]},'S04 S05')
jfile('metric-alarm.json','5分合計が5件以上、基本のSlidingWindow',{
 'AlarmName':'prod-order-e1001-5m-ge5','AlarmDescription':'rule=ORDER-E1001; app=order; env=prod; runbook=RB-001',
 'ActionsEnabled':True,'Namespace':'Ops/Order','MetricName':'E1001Count',
 'Statistic':'Sum','Unit':'Count','Period':300,'EvaluationPeriods':1,'DatapointsToAlarm':1,
 'Threshold':5,'ComparisonOperator':'GreaterThanOrEqualToThreshold','TreatMissingData':'notBreaching',
 'AlarmActions':[TOPIC],'OKActions':[TOPIC],'InsufficientDataActions':[TOPIC]},'S12')
jfile('wall-clock-option.json','固定5分窓へ変更する場合にAlarm JSONへ加える断片',
 {'EvaluationWindow':{'WallClockWindow':{'Timezone':'Asia/Tokyo'}}},'S15 S16')
jfile('sns-topic-policy.json','AのTopicへ追加・統合するポリシー',{
 'Version':'2012-10-17','Statement':[
  {'Sid':'AllowSelectedAlarmPublish','Effect':'Allow','Principal':{'Service':'cloudwatch.amazonaws.com'},
   'Action':'sns:Publish','Resource':TOPIC,
   'Condition':{'ArnEquals':{'aws:SourceArn':ALARM},'StringEquals':{'aws:SourceAccount':A}}},
  {'Sid':'AllowBQueueOwnerSubscribe','Effect':'Allow','Principal':{'AWS':ADMIN},
   'Action':'sns:Subscribe','Resource':TOPIC,
   'Condition':{'StringEquals':{'sns:Protocol':'sqs','sns:Endpoint':QUEUE}}}]},'S17 S18 S58')
jfile('subscription-admin-policy.json','Bの構築ロールのIAM許可',{
 'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':'sns:Subscribe','Resource':TOPIC}]},'S18')
queue_policy={'Version':'2012-10-17','Statement':[
 {'Sid':'AllowOnlyWorkloadTopic','Effect':'Allow','Principal':{'Service':'sns.amazonaws.com'},
  'Action':'sqs:SendMessage','Resource':QUEUE,
  'Condition':{'ArnEquals':{'aws:SourceArn':TOPIC},'StringEquals':{'aws:SourceAccount':A}}}]}
jfile('sqs-main-create.json','Bのメインキュー作成入力（Attributesの値は文字列）',{
 'QueueName':'jp1-alert-main','Attributes':{
  'VisibilityTimeout':'120','MessageRetentionPeriod':'345600','ReceiveMessageWaitTimeSeconds':'20',
  'DelaySeconds':'0','MaximumMessageSize':'1048576','SqsManagedSseEnabled':'true',
  'Policy':json.dumps(queue_policy,separators=(',',':')),
  'RedrivePolicy':json.dumps({'deadLetterTargetArn':PROCESS_DLQ,'maxReceiveCount':5},separators=(',',':'))}},'S25 S57 S18')
jfile('sqs-processing-dlq-create.json','EC2処理失敗用DLQを先に作成',{
 'QueueName':'jp1-alert-processing-dlq','Attributes':{
 'MessageRetentionPeriod':'1209600','SqsManagedSseEnabled':'true',
 'RedriveAllowPolicy':json.dumps({'redrivePermission':'byQueue','sourceQueueArns':[QUEUE]},separators=(',',':'))}},'S25 S29')
delivery_policy={'Version':'2012-10-17','Statement':[
 {'Effect':'Allow','Principal':{'Service':'sns.amazonaws.com'},'Action':'sqs:SendMessage','Resource':DELIVERY_DLQ,
  'Condition':{'ArnEquals':{'aws:SourceArn':TOPIC},'StringEquals':{'aws:SourceAccount':A}}}]}
jfile('sns-delivery-dlq-policy.json','B所有の購読に付ける配信失敗DLQの受入許可',delivery_policy,'S24')
jfile('sqs-delivery-dlq-create.json','SNS配信失敗用DLQをBへ作成',{
 'QueueName':'jp1-alert-delivery-dlq','Attributes':{
 'MessageRetentionPeriod':'1209600','SqsManagedSseEnabled':'true',
 'Policy':json.dumps(delivery_policy,separators=(',',':'))}},'S24 S25')
jfile('sns-subscription-attributes.json','購読に設定する属性',{
 'RawMessageDelivery':'false',
 'RedrivePolicy':json.dumps({'deadLetterTargetArn':DELIVERY_DLQ},separators=(',',':'))},'S19 S21 S24')
jfile('ec2-trust-policy.json','Bの受信ロールをEC2から引き受ける信頼設定',{
 'Version':'2012-10-17','Statement':[
 {'Effect':'Allow','Principal':{'Service':'ec2.amazonaws.com'},'Action':'sts:AssumeRole'}]},'S36')
jfile('ec2-consumer-policy.json','Bの受信ロールの実行権限',{
 'Version':'2012-10-17','Statement':[
 {'Sid':'ConsumeAlertQueue','Effect':'Allow',
 'Action':['sqs:ReceiveMessage','sqs:DeleteMessage','sqs:ChangeMessageVisibility','sqs:GetQueueAttributes','sqs:GetQueueUrl'],
 'Resource':QUEUE}]},'S26 S32')
jfile('log-read-trust.json','原文取得を追加するときのA側ロールの信頼設定',{
 'Version':'2012-10-17','Statement':[
 {'Effect':'Allow','Principal':{'AWS':BRIDGE},'Action':'sts:AssumeRole'}]},'S36')
jfile('log-read-permission.json','A側ロールへ付与するログ読取権限',{
 'Version':'2012-10-17','Statement':[
 {'Effect':'Allow','Action':'logs:FilterLogEvents',
 'Resource':f'arn:aws:logs:{REGION}:{A}:log-group:/app/prod/order:*'}]},'S36 S37')
jfile('ec2-assume-log-role.json','原文取得時にB側EC2ロールへ追加する権限',{
 'Version':'2012-10-17','Statement':[{'Effect':'Allow','Action':'sts:AssumeRole','Resource':READER}]},'S36')
jfile('sns-kms-statement.json','SSE-KMS採用時、SNS用キーへ追加するStatement',{
 'Sid':'AllowCloudWatchForThisAlarm','Effect':'Allow','Principal':{'Service':'cloudwatch.amazonaws.com'},
 'Action':['kms:GenerateDataKey*','kms:Decrypt'],'Resource':'*',
 'Condition':{'StringEquals':{'aws:SourceAccount':A},'ArnEquals':{'aws:SourceArn':ALARM}}},'S33')
jfile('sqs-kms-statements.json','SSE-KMS採用時、SQS用キーへ追加するStatement群',{
 'Statement':[
 {'Sid':'AllowSnsTopicUseOfKey','Effect':'Allow','Principal':{'Service':'sns.amazonaws.com'},
  'Action':['kms:GenerateDataKey','kms:Decrypt'],'Resource':'*',
  'Condition':{'ArnEquals':{'aws:SourceArn':TOPIC},'StringEquals':{'aws:SourceAccount':A}}},
 {'Sid':'AllowBridgeDecrypt','Effect':'Allow','Principal':{'AWS':BRIDGE},
  'Action':'kms:Decrypt','Resource':'*'}]},'S32')
jfile('ec2-kms-option.json','SSE-KMS時、BのEC2ロールへ追加するIAM権限（Key IDを置換）',{
 'Version':'2012-10-17','Statement':[
 {'Effect':'Allow','Action':'kms:Decrypt',
 'Resource':f'arn:aws:kms:{REGION}:{B}:key/REPLACE_WITH_KEY_ID'}]},'S32')
jfile('filter-test.json','AWSでフィルターだけを試験する入力',{
 'filterPattern':'{ $.level = "ERROR" && $.code = "E1001" }',
 'logEventMessages':[
  '{"level":"ERROR","code":"E1001","message":"DB failed"}',
  '{"level":"INFO","code":"E1001","message":"OK"}',
  '{"level":"ERROR","code":"E2001","message":"Other failure"}',
  '{"level":"error","code":"E1001","message":"lower case"}']},'S56')
code(s,'AWS CLI v2：主要コマンド（実行していない）',r'''
# JSONはこのシートの同名ブロックをUTF-8で保存する。
# 先に実アカウント・ロール・リージョンへ置換する。
aws sts get-caller-identity --profile workload-a
aws sts get-caller-identity --profile operations-b

# 処理DLQを先に作成。配信DLQも別途作成し受入ポリシーを設定する。
aws sqs create-queue --cli-input-json file://sqs-processing-dlq-create.json --profile operations-b --region ap-northeast-1
aws sqs create-queue --cli-input-json file://sqs-delivery-dlq-create.json --profile operations-b --region ap-northeast-1
aws sqs create-queue --cli-input-json file://sqs-main-create.json --profile operations-b --region ap-northeast-1

# AのSNSを作成し、この資料のTopic Policyを既存設定へ統合する。
aws sns create-topic --name prod-ops-alerts --profile workload-a --region ap-northeast-1
# 次は新規トピックの例。既存トピックでは既存ポリシーへ統合したファイルを使用する。
aws sns set-topic-attributes --topic-arn arn:aws:sns:ap-northeast-1:111111111111:prod-ops-alerts --attribute-name Policy --attribute-value file://sns-topic-policy.json --profile workload-a --region ap-northeast-1

# B（キュー所有者）の認証情報で購読する。
aws sns subscribe --topic-arn arn:aws:sns:ap-northeast-1:111111111111:prod-ops-alerts --protocol sqs --notification-endpoint arn:aws:sqs:ap-northeast-1:222222222222:jp1-alert-main --attributes file://sns-subscription-attributes.json --profile operations-b --region ap-northeast-1

# ロググループと収集設定を先に準備してから試験・フィルター・Alarmを作る。
aws logs test-metric-filter --cli-input-json file://filter-test.json --profile workload-a --region ap-northeast-1
aws logs put-metric-filter --cli-input-json file://metric-filter.json --profile workload-a --region ap-northeast-1
aws cloudwatch put-metric-alarm --cli-input-json file://metric-alarm.json --profile workload-a --region ap-northeast-1

# 読み取り確認。SNS購読のOwnerとARN、Alarmのアクション等を確認する。
aws sns list-subscriptions-by-topic --topic-arn arn:aws:sns:ap-northeast-1:111111111111:prod-ops-alerts --profile workload-a --region ap-northeast-1
aws cloudwatch describe-alarms --alarm-names prod-order-e1001-5m-ge5 --profile workload-a --region ap-northeast-1
''','powershell','S04 S12 S18 S25 S56')

# Add precise payload examples to the message chapter.
from content import SECTIONS
message_section=next(x for x in SECTIONS if x['name']=='18_通知データの中身')
alarm_message={
 'AlarmName':'prod-order-e1001-5m-ge5','AlarmArn':ALARM,
 'AlarmDescription':'rule=ORDER-E1001; app=order; env=prod; runbook=RB-001',
 'AWSAccountId':A,'NewStateValue':'ALARM','OldStateValue':'OK',
 'NewStateReason':'Illustrative reason: the 5-minute Sum meets the threshold >= 5.',
 'StateChangeTime':'2026-10-11T00:05:00.000+0000','Region':'Asia Pacific (Tokyo)',
 'Trigger':{'MetricName':'E1001Count','Namespace':'Ops/Order','StatisticType':'Statistic',
  'Statistic':'SUM','Unit':'Count','Dimensions':[],'Period':300,'EvaluationPeriods':1,
  'DatapointsToAlarm':1,'ComparisonOperator':'GreaterThanOrEqualToThreshold','Threshold':5,
  'TreatMissingData':'notBreaching'}}
code(message_section,'Alarm本文の学習用サンプル（AWS実受信データではない）',json.dumps(alarm_message,ensure_ascii=False,indent=2),'json','S17')
envelope={'Type':'Notification','MessageId':'SNS-MESSAGE-ID-EXAMPLE','TopicArn':TOPIC,
 'Timestamp':'2026-10-11T00:05:01.000Z','Message':json.dumps(alarm_message,ensure_ascii=False)}
code(message_section,'Raw=falseのSQS Body内に入るSNSの包み（署名等を省略）',json.dumps(envelope,ensure_ascii=False,indent=2),'json','S19')
code(message_section,'Raw=falseの解析手順（概念例）',r'''
sqs_body = received_message["Body"]
sns_envelope = json.loads(sqs_body)
# Type、TopicArn、型・長さなどを検証してから次へ進む。
alarm = json.loads(sns_envelope["Message"])
# AlarmArn、AWSAccountId、NewStateValue、StateChangeTimeを検証する。
''','python','S19 S26')

jp1_section=next(x for x in SECTIONS if x['name']=='16_JP1への連携')
code(jp1_section,'Windows PowerShellの送信例（実パスと宛先へ置換する）',r'''
$Jp1BaseDir = '実際のJP1Baseインストール先'
$Jp1Command = Join-Path $Jp1BaseDir 'bin\jevsendd.exe'
$Jp1Args = @(
    '-d', 'jp1-im-01',
    '-i', '1001',
    '-m', '[障害] 注文 E1001 直近5分の件数が5件以上',
    '-e', 'SEVERITY=Error',
    '-e', 'AWS_ACCOUNT=111111111111',
    '-e', 'AWS_REGION=ap-northeast-1',
    '-e', 'RULE_ID=ORDER-E1001',
    '-e', 'CORRELATION_ID=EXAMPLE-STATE-CHANGE-001',
    '-f', '3', '-p', '10', '-t', '6'
)
& $Jp1Command @Jp1Args
$Jp1ExitCode = $LASTEXITCODE
# 0、1、2、3、255を分類する。非0でSQSを無条件に削除しない。
''','powershell','S41 S59')
code(jp1_section,'Linuxの送信例（対応文字コードと宛先を確認する）',r'''
/opt/jp1base/bin/jevsendd \
  -d jp1-im-01 \
  -i 1001 \
  -m '[障害] 注文 E1001 直近5分の件数が5件以上' \
  -e SEVERITY=Error \
  -e AWS_ACCOUNT=111111111111 \
  -e RULE_ID=ORDER-E1001 \
  -e CORRELATION_ID=EXAMPLE-STATE-CHANGE-001 \
  -f 3 -p 10 -t 6
# 終了コードを保存・分類する。LANGは実製品の対応設定に合わせる。
''','bash','S41 S59')

consumer=next(x for x in SECTIONS if x['name']=='15_EC2の受信処理')
code(consumer,'処理フローの疑似コード（実装済みプログラムではない）','''
繰り返す:
  処理枠が空いていれば SQS ReceiveMessage(wait=20, max=1)
  メッセージがなければ次の受信へ
  SNS包み・Alarm本文・発行元・時刻・型を検証
  通知キー = AlarmArn + StateChangeTime + NewStateValue
  共有台帳で処理権を条件付き取得
  すでに到達確認済みなら SQS削除だけ再試行
  他ワーカーが処理中なら再送せず待つ
  未確定送信なら JP1の相関IDを照合する手順へ
  必要時、ルール台帳の権限で参考ログを検索
  文字コード・本文バイト数・属性を検証してJP1形式に変換
  台帳をSENDINGへ。必要に応じてSQS可視性を延長
  固定のjevsenddを引数配列で起動（外側タイムアウトあり）
  到達確認0:
    台帳をSENT_CONFIRMEDへ永続化
    最新ReceiptHandleでSQSを削除
  到達不明2／外側タイムアウト:
    UNCERTAINを永続化。無条件の即時再発行はしない
  恒久エラー:
    原因を記録。隔離成功後に削除、または規定回数で処理DLQ
  再試行可能エラー:
    間隔と上限を設ける。未成功のSQSを消さない
  各結果・処理時間・最終成功時刻を監視へ出す
''','text','S26 S27 S28 S41')
