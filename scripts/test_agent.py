import argparse
import uuid

import boto3


def main():
    parser = argparse.ArgumentParser(description="Invoke a Bedrock Agent (classic)")
    parser.add_argument("--agent-id", required=True)
    parser.add_argument("--agent-alias-id", required=True)
    parser.add_argument("--region", default="ap-northeast-1")
    parser.add_argument("--input", default="東京の天気を教えて")
    args = parser.parse_args()

    client = boto3.client("bedrock-agent-runtime", region_name=args.region)

    response = client.invoke_agent(
        agentId=args.agent_id,
        agentAliasId=args.agent_alias_id,
        sessionId=str(uuid.uuid4()),
        inputText=args.input,
    )

    for event in response["completion"]:
        if "chunk" in event:
            print(event["chunk"]["bytes"].decode("utf-8"))


if __name__ == "__main__":
    main()
