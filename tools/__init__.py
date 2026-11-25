"""
VAX Tool Registry & Decorator Framework.
Provides the @tool decorator and central registry for all built-in and plugin tools.
"""

import inspect
import asyncio
import functools
import logging
from typing import Callable, Dict, Any, List, Optional
from vax.providers.base import ToolDefinition
from vax.safety import safety_engine, RiskLevel, TOOL_RISK_MAP
from vax.action_log import action_logger

logger = logging.getLogger("VAX.Tools")


class ToolEntry:
    def __init__(
        self,
        name: str,
        func: Callable,
        description: str,
        parameters: Dict[str, Any],
        risk_level: Optional[RiskLevel] = None,
    ):
        self.name = name
        self.func = func
        self.description = description
        self.parameters = parameters
        self.risk_level = risk_level or TOOL_RISK_MAP.get(name, RiskLevel.MEDIUM)

    def to_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.parameters,
        )


class ToolRegistry:
    """Central registry of executable agent tools."""

    def __init__(self):
        self._tools: Dict[str, ToolEntry] = {}

    def register(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        risk_level: Optional[RiskLevel] = None,
    ) -> Callable:
        tool_name = name or func.__name__
        doc = description or (func.__doc__ or "").strip() or f"Executes {tool_name}"

        # If parameters not explicitly provided, infer from type hints
        if parameters is None:
            parameters = self._infer_parameters(func)

        entry = ToolEntry(
            name=tool_name,
            func=func,
            description=doc,
            parameters=parameters,
            risk_level=risk_level,
        )
        self._tools[tool_name] = entry
        logger.debug("Registered tool: '%s' (Risk: %s)", tool_name, entry.risk_level)
        return func

    def _infer_parameters(self, func: Callable) -> Dict[str, Any]:
        sig = inspect.signature(func)
        properties = {}
        required = []

        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
        }

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = "string"
            if param.annotation != inspect.Parameter.empty:
                param_type = type_map.get(param.annotation, "string")

            properties[param_name] = {
                "type": param_type,
                "description": f"Parameter {param_name}",
            }

            if param.default == inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def get_tool(self, name: str) -> Optional[ToolEntry]:
        return self._tools.get(name)

    def get_all_definitions(self) -> List[ToolDefinition]:
        return [entry.to_definition() for entry in self._tools.values()]

    def list_tool_names(self) -> List[str]:
        return list(self._tools.keys())

    async def execute(
        self,
        name: str,
        arguments: Dict[str, Any],
        confirmed_dangerous: bool = False,
    ) -> Dict[str, Any]:
        """
        Executes a registered tool by name with arguments.
        Returns a dict: {"success": bool, "result": Any, "risk_level": str, "message": str}
        """
        entry = self.get_tool(name)
        if not entry:
            msg = f"Tool '{name}' is not registered."
            action_logger.log_action(name, RiskLevel.BLOCKED.value, arguments, "failed", msg)
            return {"success": False, "result": None, "risk_level": RiskLevel.BLOCKED.value, "message": msg}

        # Safety evaluation
        risk_level, reason = safety_engine.evaluate(name, arguments)
        if risk_level == RiskLevel.BLOCKED:
            msg = f"Action blocked by safety policy: {reason}"
            action_logger.log_action(name, risk_level.value, arguments, "blocked", msg)
            return {"success": False, "result": None, "risk_level": risk_level.value, "message": msg}

        if risk_level == RiskLevel.DANGEROUS and not confirmed_dangerous:
            msg = f"Dangerous action requires confirmation: {reason}"
            return {
                "success": False,
                "result": None,
                "risk_level": risk_level.value,
                "requires_confirmation": True,
                "message": msg,
            }

        # Execute
        try:
            if inspect.iscoroutinefunction(entry.func):
                result = await entry.func(**arguments)
            else:
                # Run sync functions in thread pool to prevent blocking asyncio loop
                loop = asyncio.get_running_loop()
                result = await loop.run_in_executor(None, functools.partial(entry.func, **arguments))

            summary = str(result)
            action_logger.log_action(name, risk_level.value, arguments, "success", summary)
            return {
                "success": True,
                "result": result,
                "risk_level": risk_level.value,
                "message": summary,
            }
        except Exception as e:
            error_msg = f"Execution error in '{name}': {e}"
            logger.exception(error_msg)
            action_logger.log_action(name, risk_level.value, arguments, "failed", error_msg)
            return {
                "success": False,
                "result": None,
                "risk_level": risk_level.value,
                "message": error_msg,
            }


registry = ToolRegistry()


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
    risk_level: Optional[RiskLevel] = None,
):
    """
    Decorator for registering tools.
    Can be used with or without arguments:
        @tool
        def my_func(): ...
        @tool(name="custom_name", description="custom desc")
        def my_func(): ...
    """
    def decorator(fn: Callable) -> Callable:
        registry.register(
            func=fn,
            name=name,
            description=description,
            parameters=parameters,
            risk_level=risk_level,
        )
        return fn

    if callable(name):
        func = name
        name = None
        return decorator(func)
    return decorator
