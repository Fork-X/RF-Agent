"""Tests for tool factory pattern consistency."""
from __future__ import annotations


def _assert_tool_registration(tools: list) -> None:
    """Shared assertion: every item is a valid (definition, impl, readonly) tuple."""
    assert isinstance(tools, list)
    assert len(tools) > 0
    for item in tools:
        assert isinstance(item, tuple), f"Expected tuple, got {type(item)}"
        assert len(item) == 3, f"Expected 3-tuple, got {len(item)}-tuple"
        defn, impl, readonly = item
        assert isinstance(defn, dict), "ToolDefinition should be a dict (TypedDict)"
        assert callable(impl), "Implementation should be callable"
        assert isinstance(readonly, bool), "readonly flag should be bool"
        # ToolDefinition structure checks
        assert defn.get("type") == "function", "ToolDefinition.type must be 'function'"
        func_def = defn.get("function")
        assert isinstance(func_def, dict), "ToolDefinition.function must be a dict"
        assert "name" in func_def, "function.name is required"
        assert "description" in func_def, "function.description is required"


class TestToolRegistrationFormat:
    """Verify all create_*_tools return consistent format."""

    def test_filesystem_tools_format(self):
        """Normal: filesystem tools return list of valid 3-tuples."""
        from quangan.tools.filesystem import create_filesystem_tools

        tools = create_filesystem_tools()
        _assert_tool_registration(tools)
        names = [t[0]["function"]["name"] for t in tools]
        assert "read_file" in names
        assert "write_file" in names

    def test_code_tools_format(self):
        """Normal: code tools follow same format."""
        from quangan.tools.code import create_code_tools

        tools = create_code_tools()
        _assert_tool_registration(tools)

    def test_command_tools_format(self):
        """Normal: command tools follow same format."""
        from quangan.tools.command import create_command_tools

        tools = create_command_tools("/tmp")
        _assert_tool_registration(tools)

    def test_shell_tools_format(self):
        """Normal: shell tools follow same format."""
        from quangan.tools.command import create_shell_tools

        tools = create_shell_tools()
        _assert_tool_registration(tools)

    def test_browser_tools_format(self):
        """Normal: browser tools follow same format."""
        from quangan.tools.browser import create_browser_tools

        tools = create_browser_tools()
        _assert_tool_registration(tools)

    def test_system_tools_format(self):
        """Normal: system tools follow same format."""
        from quangan.tools.system import create_system_tools

        tools = create_system_tools()
        _assert_tool_registration(tools)

    def test_search_tools_format(self):
        """Normal: search tools follow same format."""
        from quangan.tools.search import create_search_tools

        tools = create_search_tools()
        _assert_tool_registration(tools)

    def test_all_readonly_flags_are_correct(self):
        """Normal: readonly flags match expected values for known tools."""
        from quangan.tools.filesystem import create_filesystem_tools

        tools = create_filesystem_tools()
        tool_map = {t[0]["function"]["name"]: t[2] for t in tools}
        assert tool_map["read_file"] is True, "read_file should be readonly"
        assert tool_map["write_file"] is False, "write_file should not be readonly"
        assert tool_map["list_directory"] is True, "list_directory should be readonly"


class TestExecuteCommandRefactor:
    """Verify execute_command module-level default implementation is removed."""

    def test_no_default_implementation_in_execute_command(self):
        """Edge: execute_command should not have module-level default 'implementation'."""
        import quangan.tools.command.execute_command as mod

        assert hasattr(mod, "create_implementation"), (
            "create_implementation factory must exist"
        )
        assert not hasattr(mod, "implementation"), (
            "Module-level 'implementation' should be removed "
            "(was depending on os.getcwd())"
        )

    def test_create_implementation_returns_callable(self):
        """Normal: create_implementation returns a callable."""
        from quangan.tools.command.execute_command import create_implementation

        impl = create_implementation("/tmp")
        assert callable(impl)


class TestToolRegistrationType:
    """Verify ToolRegistration type alias is properly defined."""

    def test_tool_registration_type_exists(self):
        """Normal: ToolRegistration type alias is importable."""
        from quangan.tools.types import ToolRegistration

        assert ToolRegistration is not None

    def test_tool_function_types_exist(self):
        """Normal: ToolFunction type aliases are importable."""
        from quangan.tools.types import (
            ToolFunction,
            ToolFunctionAsync,
            ToolFunctionSync,
        )

        assert ToolFunction is not None
        assert ToolFunctionSync is not None
        assert ToolFunctionAsync is not None
