# Bedrock Agents (Classic) Weather Demo

A minimal, end-to-end example of creating an **Amazon Bedrock Agents (classic)**
agent with a function-definition **action group** backed by a dummy Lambda
"weather API". Built while learning [aws/agent-toolkit-for-aws](https://github.com/aws/agent-toolkit-for-aws)'s
`amazon-bedrock` skill.

> **Note:** Bedrock Agents classic is in maintenance mode and closed to new
> customers. For new agent workloads, use
> [Bedrock AgentCore](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/what-is-bedrock-agentcore.html)
> instead. This repo is for learning/reference purposes on an account that
> already has classic Agents access.
> See the [maintenance mode announcement](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-classic-maintenance-mode.html).

## What it does

The agent answers "What's the weather in Tokyo?" by calling a `get_weather`
action, which invokes a Lambda function that returns canned demo weather
data for Tokyo, Osaka, and Sapporo (in English or Japanese city names).

## Prerequisites

- AWS CLI v2, configured with credentials that have Bedrock Agents classic
  access (it's closed to new customers — see note above)
- Python 3.10+ with `boto3`
- Model access enabled for the foundation model you choose, in your target
  region(s)

## Setup

Replace `<ACCOUNT_ID>`, `<REGION>`, `<INFERENCE_PROFILE_ID>`, and `<MODEL_ID>`
in the `iam/*.json` files with your own values before running these commands.

### 1. Lambda function

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

### 2. Bedrock Agent IAM role

```bash
aws iam create-role \
  --role-name weather_demo_agent_bedrock_role \
  --assume-role-policy-document file://iam/agent-trust-policy.json

aws iam put-role-policy \
  --role-name weather_demo_agent_bedrock_role \
  --policy-name InvokeModelPolicy \
  --policy-document file://iam/agent-model-policy.json
```

### 3. Create the agent

Use an **inference profile ID** as the foundation model — most current
Claude models on Bedrock don't support on-demand (base model ID)
invocation. Find one with:

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

### 4. Action group + Lambda permission

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

### 5. Prepare + alias

```bash
aws bedrock-agent prepare-agent --agent-id <AGENT_ID>
# poll until agentStatus == PREPARED
aws bedrock-agent get-agent --agent-id <AGENT_ID> --query agent.agentStatus

aws bedrock-agent create-agent-alias \
  --agent-id <AGENT_ID> \
  --agent-alias-name demo
```

### 6. Test

The `InvokeAgent` API is streaming-only — the AWS CLI can't call it, so use
the provided script:

```bash
pip install boto3
python scripts/test_agent.py --agent-id <AGENT_ID> --agent-alias-id <ALIAS_ID>
```

## Gotchas learned building this

- **`bedrock:GetInferenceProfile` and `bedrock:GetFoundationModel` are
  required on the agent's IAM role**, in addition to `InvokeModel` /
  `InvokeModelWithResponseStream`. Without them, `CreateAgent`/`UpdateAgent`
  fails with `AccessDeniedException: Access denied while trying to
  create/update an agent using InferenceProfile ...` even though the role
  can already invoke the model.
- **Base (on-demand) model IDs often don't work for newer Claude models.**
  `InvokeAgent` fails with *"Invocation of model ID ... with on-demand
  throughput isn't supported"*. Use a cross-region or geographic inference
  profile ID instead (`aws bedrock list-inference-profiles`).
- **Aliases pin to a specific agent version at creation time.** Changing the
  agent's model/config and re-running `prepare-agent` updates `DRAFT`, but
  an existing alias keeps pointing at its old version. Delete and recreate
  the alias (or use `update-agent-alias` with explicit routing) to pick up
  the new version.
- **`prepare-agent` is mandatory after every config change** — skipped
  agents silently keep serving stale behavior.
- Lambda needs a resource-based policy allowing `bedrock.amazonaws.com` to
  invoke it, scoped with `aws:SourceAccount` + `aws:SourceArn` (confused
  deputy protection).

## Cleanup

```bash
aws bedrock-agent delete-agent --agent-id <AGENT_ID> --skip-resource-in-use-check
aws lambda delete-function --function-name weather_demo_agent_get_weather
aws iam delete-role-policy --role-name weather_demo_agent_bedrock_role --policy-name InvokeModelPolicy
aws iam delete-role --role-name weather_demo_agent_bedrock_role
aws iam detach-role-policy --role-name weather_demo_agent_lambda_role --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
aws iam delete-role --role-name weather_demo_agent_lambda_role
```
