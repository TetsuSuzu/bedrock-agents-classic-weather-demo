# Phase 6 実行手順(Windows / PowerShell)

[MIGRATION.md](MIGRATION.md) のPhase 6を、実際にこの環境(Windows + PowerShell +
AgentCore CLI `@aws/agentcore`)で実行するための具体的なコマンド集です。
`agentcore` コマンドがPATHに無い場合は、各セッションの先頭で以下を実行してください。

```powershell
$env:Path += ";C:\Users\tsuzuki31\AppData\Roaming\npm"
agentcore --version   # 0.27.1 が表示されればOK
```

## ステップ1: プロジェクトのScaffold

```powershell
Set-Location "$HOME\bedrock-agentcore-migration"
agentcore create --name weather_harness --project-name weathermigrate --defaults --language Python --model-provider Bedrock
```

作成されたプロジェクトディレクトリを確認:

```powershell
Get-ChildItem
```

以降の全コマンドは、生成されたプロジェクトディレクトリ内で実行します。

```powershell
Set-Location .\weathermigrate   # 実際のディレクトリ名に合わせて調整
```

## ステップ2: リージョン修正(重要・既知の罠)

`agentcore create` はデプロイ先リージョンを正しく解決しないことがあります。
`agentcore\aws-targets.json` を開き、デプロイ先リージョンを移行元Agentと同じ
`ap-northeast-1` に手動で修正してから、必ずデプロイ前に確認してください。

```powershell
Get-Content .\agentcore\aws-targets.json
```

`ap-northeast-1` になっていない場合はエディタで修正します。

## ステップ3: Shim Lambdaの作成

`skills/core-skills/amazon-bedrock/assets/lambda_shim.py.tmpl` を元に、
`tools\weather_actions_shim\handler.py` を新規作成します。トークンは以下の値で置換します。

| トークン | 値 |
|---|---|
| `{{ORIGINAL_LAMBDA_ARN}}` | `arn:aws:lambda:ap-northeast-1:691665347318:function:weather_demo_agent_get_weather` |
| `{{SCHEMA_STYLE}}` | `function` |
| `{{OP_ROUTES}}` | `{}`(function-definition型のため未使用) |

冒頭の `# <<< RENDER ... # <<< /RENDER` ブロックはコメントごと削除します。

## ステップ4: `agentcore.json` の手動編集

`agentCoreGateways[0].targets[]` に、以下の形でtargetを1件追加します(値はステップ3・
プロジェクトの実際の構成に合わせて調整):

```json
{
  "name": "weather_actions_shim",
  "targetType": "lambda",
  "toolDefinitions": [
    {
      "name": "get_weather",
      "description": "Gets the current weather (condition and temperature) for a given city.",
      "inputSchema": {
        "type": "object",
        "properties": {
          "location": {
            "type": "string",
            "description": "The city name to look up weather for (e.g. tokyo, osaka, sapporo)"
          }
        },
        "required": ["location"]
      }
    }
  ],
  "compute": {
    "host": "Lambda",
    "implementation": {
      "language": "Python",
      "path": "tools/weather_actions_shim",
      "handler": "handler.lambda_handler"
    },
    "pythonVersion": "PYTHON_3_13",
    "timeout": 30,
    "iamPolicy": {
      "Version": "2012-10-17",
      "Statement": [
        {
          "Effect": "Allow",
          "Action": "lambda:InvokeFunction",
          "Resource": "arn:aws:lambda:ap-northeast-1:691665347318:function:weather_demo_agent_get_weather"
        }
      ]
    }
  }
}
```

## ステップ5: Gatewayの追加

```powershell
agentcore add gateway --name weather_gateway --protocol-type MCP --authorizer-type AWS_IAM
```

## ステップ6: Harnessの追加

```powershell
agentcore add harness --name weather_harness --model-provider bedrock --model-id jp.anthropic.claude-haiku-4-5-20251001-v1:0 --system-prompt "You are a weather assistant. When the user mentions a city, use the get_weather action to fetch that city's weather and reply clearly in the same language the user used." --idle-timeout 600 --authorizer-type AWS_IAM
```

## ステップ7: バリデーション

```powershell
agentcore validate
```

`Valid` と表示されることを確認します。

## ステップ8: 1回目のデプロイ

```powershell
agentcore deploy
```

Gateway・Shim Lambda・Harnessが作成されます。

## ステップ9: 元Lambdaへの権限付与(ビルダー自身が実施)

初回のShim呼び出しは `AccessDeniedException` になる見込みです。デプロイ後に表示される
Shimの実行ロールARNを使い、**移行プロセスではなく利用者自身が**以下を実行します
(元Lambdaを変更する操作は移行スクリプト側では行いません)。

```powershell
aws lambda add-permission --function-name weather_demo_agent_get_weather --statement-id agentcore-shim-invoke --action lambda:InvokeFunction --principal <shim-role-arn> --source-arn <shim-lambda-arn>
```

## ステップ10: Gatewayツールのアタッチ

```powershell
agentcore add tool --harness weather_harness --type agentcore_gateway --name weather_tools --gateway weather_gateway --outbound-auth awsIam
```

## ステップ11: 2回目のデプロイ

```powershell
agentcore deploy
```

## ステップ12: 確認

```powershell
agentcore status
```

Harnessが新しいバージョンで、Gatewayツールが付いた状態になっていれば移行完了です。
