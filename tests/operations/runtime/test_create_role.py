"""Tests for create_role module."""

import json
import logging
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError

from bedrock_agentcore_starter_toolkit.operations.runtime.create_role import (
    _attach_inline_policy,
    get_or_create_runtime_execution_role,
)


class TestCreateRole:
    """Test create_role functionality."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock boto3 session."""
        session = MagicMock(spec=boto3.Session)
        mock_iam = MagicMock()
        session.client.return_value = mock_iam
        return session, mock_iam

    @pytest.fixture
    def mock_logger(self):
        """Create a mock logger."""
        return MagicMock(spec=logging.Logger)

    def test_get_or_create_runtime_execution_role_success(self, mock_session, mock_logger):
        """Test successful role creation."""
        session, mock_iam = mock_session

        # First call (check if exists) - role doesn't exist
        error_response = {"Error": {"Code": "NoSuchEntity"}}
        mock_iam.get_role.side_effect = ClientError(error_response, "GetRole")

        # Second call (create role) - successful creation
        mock_iam.create_role.return_value = {"Role": {"Arn": "arn:aws:iam::123456789012:role/TestRole"}}

        with (
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role.render_trust_policy_template",
                return_value='{"Version": "2012-10-17", "Statement": []}',
            ),
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role.render_execution_policy_template",
                return_value='{"Version": "2012-10-17", "Statement": []}',
            ),
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role.validate_rendered_policy",
                return_value={"Version": "2012-10-17", "Statement": []},
            ),
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role._attach_inline_policy"
            ) as mock_attach,
        ):
            result = get_or_create_runtime_execution_role(
                session=session,
                logger=mock_logger,
                region="us-east-1",
                account_id="123456789012",
                agent_name="test-agent",
            )

            assert result == "arn:aws:iam::123456789012:role/TestRole"
            mock_iam.create_role.assert_called_once()
            mock_attach.assert_called_once()
            mock_logger.info.assert_called()

    def test_get_or_create_runtime_execution_role_with_custom_name(self, mock_session, mock_logger):
        """Test role creation with custom name."""
        session, mock_iam = mock_session

        # First call (check if exists) - role doesn't exist
        error_response = {"Error": {"Code": "NoSuchEntity"}}
        mock_iam.get_role.side_effect = ClientError(error_response, "GetRole")

        # Second call (create role) - successful creation
        mock_iam.create_role.return_value = {"Role": {"Arn": "arn:aws:iam::123456789012:role/CustomRoleName"}}

        with (
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role.render_trust_policy_template",
                return_value='{"Version": "2012-10-17", "Statement": []}',
            ),
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role.render_execution_policy_template",
                return_value='{"Version": "2012-10-17", "Statement": []}',
            ),
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role.validate_rendered_policy",
                return_value={"Version": "2012-10-17", "Statement": []},
            ),
            patch("bedrock_agentcore_starter_toolkit.operations.runtime.create_role._attach_inline_policy"),
        ):
            result = get_or_create_runtime_execution_role(
                session=session,
                logger=mock_logger,
                region="us-east-1",
                account_id="123456789012",
                agent_name="test-agent",
                role_name="CustomRoleName",
            )

            assert result == "arn:aws:iam::123456789012:role/CustomRoleName"
            mock_iam.create_role.assert_called_once_with(
                RoleName="CustomRoleName",
                AssumeRolePolicyDocument=json.dumps({"Version": "2012-10-17", "Statement": []}),
                Description="Execution role for BedrockAgentCore Runtime - test-agent",
            )

    def test_get_or_create_runtime_execution_role_already_exists(self, mock_session, mock_logger):
        """Test getting existing role when role already exists."""
        session, mock_iam = mock_session

        # Mock the get_role response (role exists)
        mock_iam.get_role.return_value = {"Role": {"Arn": "arn:aws:iam::123456789012:role/ExistingRole"}}

        result = get_or_create_runtime_execution_role(
            session=session,
            logger=mock_logger,
            region="us-east-1",
            account_id="123456789012",
            agent_name="test-agent",
            role_name="ExistingRole",
        )

        assert result == "arn:aws:iam::123456789012:role/ExistingRole"
        mock_iam.get_role.assert_called_once_with(RoleName="ExistingRole")
        # create_role should not be called since role already exists
        mock_iam.create_role.assert_not_called()
        mock_logger.info.assert_called()

    def test_get_or_create_runtime_execution_role_check_error(self, mock_session, mock_logger):
        """Test error when checking role existence (other than NoSuchEntity)."""
        session, mock_iam = mock_session

        # Mock the get_role to raise a different error (not NoSuchEntity)
        error_response = {"Error": {"Code": "AccessDenied"}}
        mock_iam.get_role.side_effect = ClientError(error_response, "GetRole")

        with pytest.raises(RuntimeError, match="Failed to check role existence"):
            get_or_create_runtime_execution_role(
                session=session,
                logger=mock_logger,
                region="us-east-1",
                account_id="123456789012",
                agent_name="test-agent",
                role_name="TestRole",
            )

        mock_iam.get_role.assert_called_once_with(RoleName="TestRole")
        mock_iam.create_role.assert_not_called()
        mock_logger.error.assert_called()

    def test_get_or_create_runtime_execution_role_create_error(self, mock_session, mock_logger):
        """Test error during role creation."""
        session, mock_iam = mock_session

        # First call (check if exists) - role doesn't exist
        error_response = {"Error": {"Code": "NoSuchEntity"}}
        mock_iam.get_role.side_effect = ClientError(error_response, "GetRole")

        # Second call (create role) - raise AccessDenied error
        error_response_create = {"Error": {"Code": "AccessDenied"}}
        mock_iam.create_role.side_effect = ClientError(error_response_create, "CreateRole")

        with (
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role.render_trust_policy_template",
                return_value='{"Version": "2012-10-17", "Statement": []}',
            ),
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role.render_execution_policy_template",
                return_value='{"Version": "2012-10-17", "Statement": []}',
            ),
            patch(
                "bedrock_agentcore_starter_toolkit.operations.runtime.create_role.validate_rendered_policy",
                return_value={"Version": "2012-10-17", "Statement": []},
            ),
        ):
            with pytest.raises(RuntimeError, match="Failed to create role"):
                get_or_create_runtime_execution_role(
                    session=session,
                    logger=mock_logger,
                    region="us-east-1",
                    account_id="123456789012",
                    agent_name="test-agent",
                )

            mock_iam.create_role.assert_called_once()
            mock_logger.error.assert_called()

    def test_attach_inline_policy_success(self, mock_session, mock_logger):
        """Test successful policy attachment."""
        _, mock_iam = mock_session

        _attach_inline_policy(
            iam_client=mock_iam,
            role_name="TestRole",
            policy_name="TestPolicy",
            policy_document='{"Version": "2012-10-17", "Statement": []}',
            logger=mock_logger,
        )

        mock_iam.put_role_policy.assert_called_once_with(
            RoleName="TestRole",
            PolicyName="TestPolicy",
            PolicyDocument='{"Version": "2012-10-17", "Statement": []}',
        )

    def test_attach_inline_policy_error(self, mock_session, mock_logger):
        """Test error during policy attachment."""
        _, mock_iam = mock_session

        # Mock the put_role_policy to raise an error
        error_response = {"Error": {"Code": "MalformedPolicyDocument"}}
        mock_iam.put_role_policy.side_effect = ClientError(error_response, "PutRolePolicy")

        with pytest.raises(RuntimeError, match="Failed to attach policy"):
            _attach_inline_policy(
                iam_client=mock_iam,
                role_name="TestRole",
                policy_name="TestPolicy",
                policy_document='{"Version": "2012-10-17", "Statement": []}',
                logger=mock_logger,
            )

        mock_iam.put_role_policy.assert_called_once()
        mock_logger.error.assert_called()
