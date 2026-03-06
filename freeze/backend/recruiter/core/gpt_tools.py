tools = [
        {
            "type": "function",
            "function": {
                "name": "recommend_branch",
                "description": "Recommend the company branch that is closer to the user",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "address": {
                            "type": "string",
                            "description": "Person address, including city",
                        },
                    },
                    "required": ["address"],
                },
            },
        }
    ]