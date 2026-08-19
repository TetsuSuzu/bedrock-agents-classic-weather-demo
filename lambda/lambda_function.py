import json

DEMO_WEATHER = {
    "tokyo": {"condition": "晴れ", "temperature_c": 29},
    "osaka": {"condition": "曇り", "temperature_c": 27},
    "sapporo": {"condition": "雨", "temperature_c": 21},
}

ALIASES = {
    "東京": "tokyo",
    "大阪": "osaka",
    "札幌": "sapporo",
}


def lambda_handler(event, context):
    function = event.get("function")
    parameters = {p["name"]: p["value"] for p in event.get("parameters", [])}
    raw_location = parameters.get("location", "").strip()
    location = ALIASES.get(raw_location, raw_location.lower())

    weather = DEMO_WEATHER.get(location, {"condition": "不明", "temperature_c": None})
    body = json.dumps(
        {"location": location or "unknown", **weather}, ensure_ascii=False
    )

    response_body = {"TEXT": {"body": body}}
    action_response = {
        "actionGroup": event.get("actionGroup"),
        "function": function,
        "functionResponse": {"responseBody": response_body},
    }
    return {
        "messageVersion": "1.0",
        "response": action_response,
    }
