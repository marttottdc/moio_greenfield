from agents.tool import FunctionTool

REGISTRY: dict[str, FunctionTool] = {}


def register(tool: FunctionTool):
    """Save the FunctionTool when the module is imported."""
    REGISTRY[tool.name] = tool
    return tool        # keeps decorator stacking intact
