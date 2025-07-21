"""Creates an execution role to use in the Bedrock AgentCore Runtime module."""

import json
import logging
from typing import Optional

from boto3 import Session
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from ...utils.runtime.policy_template import (
    render_execution_policy_template,
    render_trust_policy_template,
    validate_rendered_policy,
)


def create_runtime_execution_role(
    session: Session,
    logger: logging.Logger,
    region: str,
    account_id: str,
    agent_name: str,
    role_name: Optional[str] = None,
) -> str:
    """Create the Runtime execution role.

    Args:
        session: Boto3 session
        logger: Logger instance
        region: AWS region
        account_id: AWS account ID
        agent_name: Agent name for resource scoping
        role_name: Optional custom role name

    Returns:
        Role ARN

    Raises:
        RuntimeError: If role creation fails
    """
    if not role_name:
        role_name = f"BedrockAgentCoreRuntimeExecutionRole-{agent_name}"

    logger.info("Starting execution role creation process for agent: %s", agent_name)
    logger.info("Using AWS region: %s, account ID: %s", region, account_id)
    logger.info("Role name will be: %s", role_name)

    iam = session.client("iam")

    try:
        # Render the trust policy template
        logger.debug("Rendering trust policy template...")
        trust_policy_json = render_trust_policy_template(region, account_id)
        trust_policy = validate_rendered_policy(trust_policy_json)
        logger.debug("Trust policy validated successfully")

        # Render the execution policy template
        logger.debug("Rendering execution policy template...")
        execution_policy_json = render_execution_policy_template(region, account_id, agent_name)
        execution_policy = validate_rendered_policy(execution_policy_json)
        logger.debug("Execution policy validated successfully")

        logger.info("Creating IAM role: %s", role_name)
        logger.debug("Role will trust bedrock-agentcore.amazonaws.com service")

        # Create the role with the trust policy
        role = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description=f"Execution role for BedrockAgentCore Runtime - {agent_name}",
        )

        role_arn = role["Role"]["Arn"]
        logger.info("✓ Role created: %s", role_arn)
        logger.debug("Role ID: %s", role["Role"].get("RoleId", "Unknown"))
        logger.debug("Role Path: %s", role["Role"].get("Path", "/"))
        logger.debug("Creation Date: %s", role["Role"].get("CreateDate", "Unknown"))

        # Create and attach the inline execution policy
        policy_name = f"BedrockAgentCoreRuntimeExecutionPolicy-{agent_name}"
        logger.info("Attaching inline policy: %s to role: %s", policy_name, role_name)
        logger.debug("Policy grants permissions for ECR, CloudWatch Logs, X-Ray, and Bedrock")

        _attach_inline_policy(
            iam_client=iam,
            role_name=role_name,
            policy_name=policy_name,
            policy_document=json.dumps(execution_policy),
            logger=logger,
        )

        logger.info("✓ Execution policy attached: %s", policy_name)
        logger.info("Role creation complete and ready for use with Bedrock AgentCore")

        return role_arn

    except ClientError as e:
        if e.response["Error"]["Code"] == "EntityAlreadyExists":
            try:
                logger.info("Role %s already exists, retrieving existing role...", role_name)
                role = iam.get_role(RoleName=role_name)
                logger.info("✓ Role already exists: %s", role["Role"]["Arn"])
                logger.debug("Creation Date: %s", role["Role"].get("CreateDate", "Unknown"))
                return role["Role"]["Arn"]
            except ClientError as get_error:
                logger.error("Error getting existing role: %s", get_error)
                raise RuntimeError(f"Failed to get existing role: {get_error}") from get_error
        else:
            logger.error("Error creating role: %s", e)
            if e.response["Error"]["Code"] == "AccessDenied":
                logger.error(
                    "Access denied. Ensure your AWS credentials have sufficient IAM permissions "
                    "to create roles and policies."
                )
            elif e.response["Error"]["Code"] == "LimitExceeded":
                logger.error(
                    "AWS limit exceeded. You may have reached the maximum number of IAM roles allowed in your account."
                )
            raise RuntimeError(f"Failed to create role: {e}") from e


def _attach_inline_policy(
    iam_client: BaseClient,
    role_name: str,
    policy_name: str,
    policy_document: str,
    logger: logging.Logger,
) -> None:
    """Attach an inline policy to an IAM role.

    Args:
        iam_client: IAM client instance
        role_name: Name of the role
        policy_name: Name of the policy
        policy_document: Policy document JSON string
        logger: Logger instance

    Raises:
        RuntimeError: If policy attachment fails
    """
    try:
        logger.debug("Attaching inline policy %s to role %s", policy_name, role_name)
        logger.debug("Policy document size: %d bytes", len(policy_document))

        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=policy_document,
        )

        logger.debug("Successfully attached policy %s to role %s", policy_name, role_name)
    except ClientError as e:
        logger.error("Error attaching policy %s to role %s: %s", policy_name, role_name, e)
        if e.response["Error"]["Code"] == "MalformedPolicyDocument":
            logger.error("Policy document is malformed. Check the JSON syntax.")
        elif e.response["Error"]["Code"] == "LimitExceeded":
            logger.error("Policy size limit exceeded or too many policies attached to the role.")
        raise RuntimeError(f"Failed to attach policy {policy_name}: {e}") from e
