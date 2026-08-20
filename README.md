# Bedrock Agents (Classic) Weather Demo

**Amazon Bedrock Agents(クラシック)** で、ダミーの天気APIとして動作するLambdaを
バックエンドに持つ function-definition 型の **Action Group** を使ったAgentを
作成する、最小構成のエンドツーエンドのサンプルです。
[aws/agent-toolkit-for-aws](https://github.com/aws/agent-toolkit-for-aws) の
`amazon-bedrock` スキルを学習しながら構築しました。

> **注意:** Bedrock Agents クラシックはメンテナンスモードに入っており、新規顧客には
> 提供終了しています。新規のエージェントワークロードには
> [Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
> を使用してください。このリポジトリは、すでにクラシックAgentsへのアクセス権を持つ
> アカウントでの学習・参考目的のものです。
> 詳細は[メンテナンスモードのアナウンス](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html)を参照してください。

## できること

「東京の天気を教えて」という質問に対して、Agentが `get_weather` アクションを
呼び出します。このアクションはLambda関数を実行し、東京・大阪・札幌の
ダミーの天気データ(英語・日本語どちらの都市名にも対応)を返します。

## 前提条件

- AWS CLI v2(Bedrock Agentsクラシックへのアクセス権を持つ認証情報で設定済み。
  上記の通り新規顧客には提供終了しています)
- Python 3.10+ と `boto3`
- 使用するリージョンで、選択した基盤モデルへのモデルアクセスが有効になっていること

## セットアップ

以下のコマンドを実行する前に、`iam/*.json` 内の `<ACCOUNT_ID>`、`<REGION>`、
`<INFERENCE_PROFILE_ID>`、`<MODEL_ID>` をご自身の値に置き換えてください。

### 1. Lambda関数

```bash
zip -j lambda_function.zip lambda/lambda_function.py

aws iam create-role \
  --role-name weather_demo_agent_lambda_role \
  --assume-role-policy-document file://iam/lambda-trust-policy.json

aws iam attach-role-policy \
  --role-name weather_demo_agent_lambda_role \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

aws lambda create-function \
  --function-name weather_demo_agent_get_weather \
  --runtime python3.13 \
  --role arn:aws:iam::<ACCOUNT_ID>:role/weather_demo_agent_lambda_role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda_function.zip
```

### 2. Bedrock Agent用IAMロール

```bash
aws iam create-role \
  --role-name weather_demo_agent_bedrock_role \
  --assume-role-policy-document file://iam/agent-trust-policy.json

aws iam put-role-policy \
  --role-name weather_demo_agent_bedrock_role \
  --policy-name InvokeModelPolicy \
  --policy-document file://iam/agent-model-policy.json
```

### 3. Agentの作成

基盤モデルには**推論プロファイルID**を使用してください — Bedrock上の最近の
Claudeモデルの多くは、オンデマンド(ベースモデルID)での呼び出しに対応していません。
以下で確認できます。

```bash
aws bedrock list-inference-profiles --region <REGION>
```

```bash
aws bedrock-agent create-agent \
  --agent-name weather_demo_agent \
  --foundation-model <INFERENCE_PROFILE_ID> \
  --instruction "You are a weather assistant. When the user mentions a city, use the get_weather action to fetch that city's weather and reply clearly in the same language the user used." \
  --agent-resource-role-arn arn:aws:iam::<ACCOUNT_ID>:role/weather_demo_agent_bedrock_role
```

### 4. Action Group + Lambda権限

```bash
aws lambda add-permission \
  --function-name weather_demo_agent_get_weather \
  --statement-id AllowBedrockAgentInvoke \
  --action lambda:InvokeFunction \
  --principal bedrock.amazonaws.com \
  --source-account <ACCOUNT_ID> \
  --source-arn arn:aws:bedrock:<REGION>:<ACCOUNT_ID>:agent/<AGENT_ID>

aws bedrock-agent create-agent-action-group \
  --agent-id <AGENT_ID> \
  --agent-version DRAFT \
  --action-group-name weather_actions \
  --action-group-executor lambda=arn:aws:lambda:<REGION>:<ACCOUNT_ID>:function:weather_demo_agent_get_weather \
  --function-schema file://schema/function-schema.json
```

### 5. Prepare + Alias

```bash
aws bedrock-agent prepare-agent --agent-id <AGENT_ID>
# agentStatus が PREPARED になるまでポーリング
aws bedrock-agent get-agent --agent-id <AGENT_ID> --query agent.agentStatus

aws bedrock-agent create-agent-alias \
  --agent-id <AGENT_ID> \
  --agent-alias-name demo
```

### 6. テスト

`InvokeAgent` APIはストリーミング専用のため、AWS CLIからは呼び出せません。
同梱のスクリプトを使用してください。

```bash
pip install boto3
python scripts/test_agent.py --agent-id <AGENT_ID> --agent-alias-id <ALIAS_ID>
```

## 構築中にハマったポイント

- **Agentの IAM ロールには `bedrock:GetInferenceProfile` と
  `bedrock:GetFoundationModel` の権限も必要です**(`InvokeModel` /
  `InvokeModelWithResponseStream` に加えて)。これらがないと、ロールが
  すでにモデルを呼び出せる状態であっても、`CreateAgent`/`UpdateAgent` が
  `AccessDeniedException: Access denied while trying to create/update an
  agent using InferenceProfile ...` で失敗します。
- **ベース(オンデマンド)モデルIDは新しめのClaudeモデルでは動作しないことが
  多いです。** `InvokeAgent` 実行時に *"Invocation of model ID ... with
  on-demand throughput isn't supported"* というエラーになります。
  クロスリージョンまたは地理的な推論プロファイルIDを使用してください
  (`aws bedrock list-inference-profiles` で確認)。
- **Aliasは作成した時点のAgentバージョンに固定されます。** Agentのモデルや
  設定を変更して `prepare-agent` を再実行すると `DRAFT` は更新されますが、
  既存のAliasは古いバージョンを指したままです。新しいバージョンを反映させるには
  Aliasを削除・再作成するか(あるいは `update-agent-alias` で明示的に
  ルーティングを指定)してください。
- **設定変更のたびに `prepare-agent` の実行が必須です** — 実行を忘れると、
  Agentは気づかないまま古い設定で動作し続けます。
- Lambdaには `bedrock.amazonaws.com` からの呼び出しを許可するリソースベース
  ポリシーが必要で、`aws:SourceAccount` + `aws:SourceArn` でスコープを
  絞る必要があります(confused deputy対策)。

## クリーンアップ

```bash
aws bedrock-agent delete-agent --agent-id <AGENT_ID> --skip-resource-in-use-check
aws lambda delete-function --function-name weather_demo_agent_get_weather
aws iam delete-role-policy --role-name weather_demo_agent_bedrock_role --policy-name InvokeModelPolicy
aws iam delete-role --role-name weather_demo_agent_bedrock_role
aws iam detach-role-policy --role-name weather_demo_agent_lambda_role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name weather_demo_agent_lambda_role
```
