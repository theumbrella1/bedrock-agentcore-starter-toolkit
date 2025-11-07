"""Unit tests for Memory CLI commands."""

import json
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from bedrock_agentcore_starter_toolkit.cli.memory.commands import memory_app
from bedrock_agentcore_starter_toolkit.operations.memory.models import Memory, MemorySummary

runner = CliRunner()


@pytest.fixture
def mock_memory_manager():
    """Fixture to create a mocked MemoryManager."""
    with patch("bedrock_agentcore_starter_toolkit.cli.memory.commands.MemoryManager") as mock_manager_class:
        mock_manager = MagicMock()
        mock_manager_class.return_value = mock_manager
        mock_manager.region_name = "us-west-2"
        yield mock_manager


def test_create_command_basic(mock_memory_manager):
    """Test basic memory create command."""
    # Mock the create response
    mock_memory = Memory({"id": "mem-123", "status": "ACTIVE", "name": "test-memory"})
    mock_memory_manager.create_memory_and_wait.return_value = mock_memory

    result = runner.invoke(memory_app, ["create", "test-memory"])

    assert result.exit_code == 0
    assert "mem-123" in result.stdout
    assert "ACTIVE" in result.stdout
    mock_memory_manager.create_memory_and_wait.assert_called_once()


def test_create_command_with_strategies(mock_memory_manager):
    """Test create command with strategies."""
    mock_memory = Memory({"id": "mem-456", "status": "CREATING", "name": "test-memory"})
    mock_memory_manager.create_memory_and_wait.return_value = mock_memory

    strategies_json = '[{"semanticMemoryStrategy": {"name": "Facts"}}]'
    result = runner.invoke(memory_app, ["create", "test-memory", "--strategies", strategies_json])

    assert result.exit_code == 0
    assert "mem-456" in result.stdout

    # Verify strategies were parsed and passed
    call_args = mock_memory_manager.create_memory_and_wait.call_args
    assert call_args[1]["strategies"] is not None


def test_create_command_with_description(mock_memory_manager):
    """Test create command with description."""
    mock_memory = Memory({"id": "mem-789", "status": "ACTIVE", "name": "test-memory"})
    mock_memory_manager.create_memory_and_wait.return_value = mock_memory

    result = runner.invoke(memory_app, ["create", "test-memory", "--description", "Test description"])

    assert result.exit_code == 0
    call_args = mock_memory_manager.create_memory_and_wait.call_args
    assert call_args[1]["description"] == "Test description"


def test_create_command_no_wait(mock_memory_manager):
    """Test create command with --no-wait flag."""
    mock_memory = Memory({"id": "mem-999", "status": "CREATING", "name": "test-memory"})
    mock_memory_manager._create_memory.return_value = mock_memory

    result = runner.invoke(memory_app, ["create", "test-memory", "--no-wait"])

    assert result.exit_code == 0
    mock_memory_manager._create_memory.assert_called_once()
    mock_memory_manager.create_memory_and_wait.assert_not_called()


def test_create_command_invalid_json(mock_memory_manager):
    """Test create command with invalid JSON strategies."""
    result = runner.invoke(memory_app, ["create", "test-memory", "--strategies", "invalid-json"])

    assert result.exit_code == 1
    assert "Error parsing strategies JSON" in result.stdout


def test_get_command(mock_memory_manager):
    """Test get memory command."""
    mock_memory = Memory(
        {
            "id": "mem-123",
            "name": "test-memory",
            "status": "ACTIVE",
            "description": "Test description",
            "eventExpiryDuration": 90,
            "strategies": [{"name": "Facts", "type": "SEMANTIC"}],
        }
    )
    mock_memory_manager.get_memory.return_value = mock_memory

    result = runner.invoke(memory_app, ["get", "mem-123"])

    assert result.exit_code == 0
    assert "mem-123" in result.stdout
    assert "test-memory" in result.stdout
    assert "ACTIVE" in result.stdout
    mock_memory_manager.get_memory.assert_called_once_with("mem-123")


def test_get_command_with_region(mock_memory_manager):
    """Test get command with custom region."""
    mock_memory = Memory({"id": "mem-123", "name": "test-memory", "status": "ACTIVE"})
    mock_memory_manager.get_memory.return_value = mock_memory

    result = runner.invoke(memory_app, ["get", "mem-123", "--region", "us-east-1"])

    assert result.exit_code == 0
    # Verify MemoryManager was initialized with the correct region
    with patch("bedrock_agentcore_starter_toolkit.cli.memory.commands.MemoryManager") as mock_class:
        runner.invoke(memory_app, ["get", "mem-123", "--region", "us-east-1"])
        mock_class.assert_called_once()
        assert mock_class.call_args[1]["region_name"] == "us-east-1"


def test_list_command(mock_memory_manager):
    """Test list memories command."""
    mock_memories = [
        MemorySummary(
            {
                "id": "mem-1",
                "arn": "arn:aws:bedrock:us-west-2:123456789012:memory/mem-1",
                "status": "ACTIVE",
                "createdAt": "2024-01-01T00:00:00Z",
                "updatedAt": "2024-01-02T00:00:00Z",
            }
        ),
        MemorySummary(
            {
                "id": "mem-2",
                "arn": "arn:aws:bedrock:us-west-2:123456789012:memory/mem-2",
                "status": "ACTIVE",
                "createdAt": "2024-01-03T00:00:00Z",
                "updatedAt": "2024-01-04T00:00:00Z",
            }
        ),
    ]
    mock_memory_manager.list_memories.return_value = mock_memories

    result = runner.invoke(memory_app, ["list"])

    assert result.exit_code == 0
    assert "mem-1" in result.stdout
    assert "mem-2" in result.stdout
    assert "ACTIVE" in result.stdout
    mock_memory_manager.list_memories.assert_called_once()


def test_list_command_empty(mock_memory_manager):
    """Test list command with no memories."""
    mock_memory_manager.list_memories.return_value = []

    result = runner.invoke(memory_app, ["list"])

    assert result.exit_code == 0
    assert "No memories found" in result.stdout


def test_list_command_with_max_results(mock_memory_manager):
    """Test list command with max results."""
    mock_memory_manager.list_memories.return_value = []

    result = runner.invoke(memory_app, ["list", "--max-results", "50"])

    assert result.exit_code == 0
    call_args = mock_memory_manager.list_memories.call_args
    assert call_args[1]["max_results"] == 50


def test_delete_command(mock_memory_manager):
    """Test delete memory command."""
    result = runner.invoke(memory_app, ["delete", "mem-123"])

    assert result.exit_code == 0
    assert "deleted successfully" in result.stdout.lower()
    mock_memory_manager.delete_memory.assert_called_once_with("mem-123")


def test_delete_command_with_wait(mock_memory_manager):
    """Test delete command with --wait flag."""
    result = runner.invoke(memory_app, ["delete", "mem-123", "--wait"])

    assert result.exit_code == 0
    mock_memory_manager.delete_memory_and_wait.assert_called_once()
    mock_memory_manager.delete_memory.assert_not_called()


def test_create_event_command(mock_memory_manager):
    """Test create event command."""
    mock_memory_manager.create_memory_event.return_value = {"eventId": "event-123"}

    payload = '{"conversational": {"content": {"text": "Hello"}, "role": "USER"}}'
    result = runner.invoke(memory_app, ["create-event", "mem-123", "user-456", payload])

    assert result.exit_code == 0
    assert "event-123" in result.stdout
    mock_memory_manager.create_memory_event.assert_called_once()


def test_create_event_command_with_session(mock_memory_manager):
    """Test create event command with session ID."""
    mock_memory_manager.create_memory_event.return_value = {"eventId": "event-456"}

    payload = '{"conversational": {"content": {"text": "Hi"}, "role": "USER"}}'
    result = runner.invoke(memory_app, ["create-event", "mem-123", "user-456", payload, "--session-id", "session-789"])

    assert result.exit_code == 0
    call_args = mock_memory_manager.create_memory_event.call_args
    assert call_args[1]["session_id"] == "session-789"


def test_create_event_command_invalid_json(mock_memory_manager):
    """Test create event command with invalid JSON payload."""
    result = runner.invoke(memory_app, ["create-event", "mem-123", "user-456", "invalid-json"])

    assert result.exit_code == 1
    assert "Error parsing payload JSON" in result.stdout


def test_retrieve_command(mock_memory_manager):
    """Test retrieve memories command."""
    mock_records = [
        {"memoryRecordId": "rec-1", "content": "User likes pizza", "score": 0.95},
        {"memoryRecordId": "rec-2", "content": "User prefers Italian", "score": 0.87},
    ]
    mock_memory_manager.retrieve_memories.return_value = mock_records

    result = runner.invoke(memory_app, ["retrieve", "mem-123", "/namespace", "What does user like?"])

    assert result.exit_code == 0
    assert "rec-1" in result.stdout
    assert "rec-2" in result.stdout
    assert "User likes pizza" in result.stdout
    mock_memory_manager.retrieve_memories.assert_called_once()


def test_retrieve_command_with_top_k(mock_memory_manager):
    """Test retrieve command with custom top-k."""
    mock_memory_manager.retrieve_memories.return_value = []

    result = runner.invoke(memory_app, ["retrieve", "mem-123", "/namespace", "query", "--top-k", "10"])

    assert result.exit_code == 0
    call_args = mock_memory_manager.retrieve_memories.call_args
    assert call_args[1]["top_k"] == 10


def test_retrieve_command_no_results(mock_memory_manager):
    """Test retrieve command with no results."""
    mock_memory_manager.retrieve_memories.return_value = []

    result = runner.invoke(memory_app, ["retrieve", "mem-123", "/namespace", "query"])

    assert result.exit_code == 0
    assert "No memory records found" in result.stdout


def test_list_actors_command(mock_memory_manager):
    """Test list actors command."""
    mock_actors = [
        {"actorId": "user-1", "lastActivityTimestamp": "2024-01-01T00:00:00Z"},
        {"actorId": "user-2", "lastActivityTimestamp": "2024-01-02T00:00:00Z"},
    ]
    mock_memory_manager.list_memory_actors.return_value = mock_actors

    result = runner.invoke(memory_app, ["list-actors", "mem-123"])

    assert result.exit_code == 0
    assert "user-1" in result.stdout
    assert "user-2" in result.stdout
    mock_memory_manager.list_memory_actors.assert_called_once()


def test_list_actors_command_empty(mock_memory_manager):
    """Test list actors command with no actors."""
    mock_memory_manager.list_memory_actors.return_value = []

    result = runner.invoke(memory_app, ["list-actors", "mem-123"])

    assert result.exit_code == 0
    assert "No actors found" in result.stdout


def test_list_sessions_command(mock_memory_manager):
    """Test list sessions command."""
    mock_sessions = [
        {"sessionId": "session-1", "lastActivityTimestamp": "2024-01-01T00:00:00Z"},
        {"sessionId": "session-2", "lastActivityTimestamp": "2024-01-02T00:00:00Z"},
    ]
    mock_memory_manager.list_memory_sessions.return_value = mock_sessions

    result = runner.invoke(memory_app, ["list-sessions", "mem-123", "user-456"])

    assert result.exit_code == 0
    assert "session-1" in result.stdout
    assert "session-2" in result.stdout
    mock_memory_manager.list_memory_sessions.assert_called_once()


def test_list_sessions_command_empty(mock_memory_manager):
    """Test list sessions command with no sessions."""
    mock_memory_manager.list_memory_sessions.return_value = []

    result = runner.invoke(memory_app, ["list-sessions", "mem-123", "user-456"])

    assert result.exit_code == 0
    assert "No sessions found" in result.stdout


def test_status_command(mock_memory_manager):
    """Test status command."""
    mock_memory_manager.get_memory_status.return_value = "ACTIVE"

    result = runner.invoke(memory_app, ["status", "mem-123"])

    assert result.exit_code == 0
    assert "ACTIVE" in result.stdout
    assert "mem-123" in result.stdout
    mock_memory_manager.get_memory_status.assert_called_once_with("mem-123")


def test_command_error_handling(mock_memory_manager):
    """Test error handling in commands."""
    mock_memory_manager.get_memory.side_effect = Exception("Test error")

    result = runner.invoke(memory_app, ["get", "mem-123"])

    assert result.exit_code == 1
    assert "Error" in result.stdout


def test_all_commands_accept_region_option(mock_memory_manager):
    """Test that all commands accept --region option."""
    commands_with_args = [
        (["create", "test-memory", "--region", "us-east-1"], mock_memory_manager.create_memory_and_wait),
        (["get", "mem-123", "--region", "us-east-1"], mock_memory_manager.get_memory),
        (["list", "--region", "us-east-1"], mock_memory_manager.list_memories),
        (["delete", "mem-123", "--region", "us-east-1"], mock_memory_manager.delete_memory),
        (["status", "mem-123", "--region", "us-east-1"], mock_memory_manager.get_memory_status),
    ]

    # Mock return values
    mock_memory_manager.create_memory_and_wait.return_value = Memory({"id": "mem-123", "status": "ACTIVE"})
    mock_memory_manager.get_memory.return_value = Memory({"id": "mem-123", "status": "ACTIVE"})
    mock_memory_manager.list_memories.return_value = []
    mock_memory_manager.get_memory_status.return_value = "ACTIVE"

    for command_args, mock_method in commands_with_args:
        result = runner.invoke(memory_app, command_args)
        # Should not fail due to region option
        assert result.exit_code == 0 or "Error" not in result.stdout
