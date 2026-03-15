"""Tests for system tools input validation."""

from mcp_ssh_multi.errors import create_validation_error
from mcp_ssh_multi.tools.tools_system import _validate_filter_name, _validate_log_path


class TestValidateLogPath:
    def test_valid_path(self):
        assert _validate_log_path("/var/log/syslog") is None

    def test_empty_path(self):
        assert _validate_log_path("") is not None

    def test_relative_path(self):
        assert _validate_log_path("var/log/syslog") is not None

    def test_path_traversal(self):
        assert _validate_log_path("/var/log/../../etc/passwd") is not None

    def test_special_chars(self):
        assert _validate_log_path("/var/log/file;rm -rf /") is not None


class TestValidateFilterName:
    def test_valid_filter(self):
        assert _validate_filter_name("nginx") is None

    def test_empty_filter(self):
        assert _validate_filter_name("") is not None

    def test_injection_attempt(self):
        assert _validate_filter_name("nginx;rm -rf /") is not None

    def test_long_filter(self):
        assert _validate_filter_name("a" * 129) is not None


class TestStructuredErrors:
    def test_validation_error_has_correct_structure(self):
        result = create_validation_error("bad input", parameter="log_path")
        assert result["success"] is False
        assert result["error"]["code"] == "VALIDATION_FAILED"
        assert result["parameter"] == "log_path"
