```
AWSTemplateFormatVersion: "2010-09-09"
Description: "MCP Server on AgentCore Runtime - Deploy an MCP server with custom tools (add_numbers, multiply_numbers, greet_user)"

# ============================================================================
# PARAMETERS SECTION
# ============================================================================
Parameters:
  # Agent Configuration
  AgentName:
    Type: String
    Default: "MCPServerAgent"
    Description: "Name for the MCP server runtime"
    AllowedPattern: "^[a-zA-Z][a-zA-Z0-9_]{0,47}$"
    ConstraintDescription: "Must start with a letter, max 48 characters, alphanumeric and underscores only"

  # Container Configuration
  ImageTag:
    Type: String
    Default: "latest"
    Description: "Tag for the Docker image"

  # Network Configuration
  NetworkMode:
    Type: String
    Default: "PUBLIC"
    Description: "Network mode for AgentCore resources"
    AllowedValues:
      - PUBLIC
      - PRIVATE

  # ECR Configuration
  ECRRepositoryName:
    Type: String
    Default: "mcp-server"
    Description: "Name of the ECR repository"

# ============================================================================
# METADATA SECTION
# ============================================================================
Metadata:
  AWS::CloudFormation::Interface:
    ParameterGroups:
      - Label:
          default: "Agent Configuration"
        Parameters:
          - AgentName
          - NetworkMode
      - Label:
          default: "Container Configuration"
        Parameters:
          - ECRRepositoryName
          - ImageTag
    ParameterLabels:
      AgentName:
        default: "Agent Name"
      NetworkMode:
        default: "Network Mode"
      ECRRepositoryName:
        default: "ECR Repository Name"
      ImageTag:
        default: "Image Tag"

# ============================================================================
# RESOURCES SECTION
# ============================================================================
Resources:
  # ========================================================================
  # ECR MODULE - Container Registry
  # ========================================================================

  ECRRepository:
    Type: AWS::ECR::Repository
    DeletionPolicy: Delete
    UpdateReplacePolicy: Delete
    Properties:
      RepositoryName: !Sub "${AWS::StackName}-${ECRRepositoryName}"
      ImageTagMutability: MUTABLE
      EmptyOnDelete: true
      ImageScanningConfiguration:
        ScanOnPush: true
      RepositoryPolicyText:
        Version: "2012-10-17"
        Statement:
          - Sid: AllowPullFromAccount
            Effect: Allow
            Principal:
              AWS: !Sub "arn:aws:iam::${AWS::AccountId}:root"
            Action:
              - ecr:BatchGetImage
              - ecr:GetDownloadUrlForLayer
      Tags:
        - Key: Name
          Value: !Sub "${AWS::StackName}-ecr-repository"
        - Key: StackName
          Value: !Ref AWS::StackName
        - Key: Module
          Value: ECR

  # ========================================================================
  # COGNITO MODULE - Authentication
  # ========================================================================

  CognitoUserPool:
    Type: AWS::Cognito::UserPool
    Properties:
      UserPoolName: !Sub "${AWS::StackName}-user-pool"
      Policies:
        PasswordPolicy:
          MinimumLength: 8
          RequireUppercase: false
          RequireLowercase: false
          RequireNumbers: false
          RequireSymbols: false
      Schema:
        - Name: email
          AttributeDataType: String
          Required: false
          Mutable: true
      UserPoolTags:
        Name: !Sub "${AWS::StackName}-user-pool"
        StackName: !Ref AWS::StackName
        Module: Cognito

  CognitoUserPoolClient:
    Type: AWS::Cognito::UserPoolClient
    Properties:
      ClientName: !Sub "${AWS::StackName}-client"
      UserPoolId: !Ref CognitoUserPool
      GenerateSecret: false
      ExplicitAuthFlows:
        - ALLOW_USER_PASSWORD_AUTH
        - ALLOW_REFRESH_TOKEN_AUTH
      PreventUserExistenceErrors: ENABLED

  CognitoUser:
    Type: AWS::Cognito::UserPoolUser
    Properties:
      UserPoolId: !Ref CognitoUserPool
      Username: testuser
      MessageAction: SUPPRESS

  SetCognitoUserPassword:
    Type: Custom::CognitoSetPassword
    DependsOn: CognitoUser
    Properties:
      ServiceToken: !GetAtt CognitoPasswordSetterFunction.Arn
      UserPoolId: !Ref CognitoUserPool
      Username: testuser
      Password: MyPassword123!

  # ========================================================================
  # IAM MODULE - Security and Permissions
  # ========================================================================

  # Agent Execution Role
  AgentExecutionRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub "${AWS::StackName}-agent-execution-role"
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Sid: AssumeRolePolicy
            Effect: Allow
            Principal:
              Service: bedrock-agentcore.amazonaws.com
            Action: sts:AssumeRole
            Condition:
              StringEquals:
                aws:SourceAccount: !Ref AWS::AccountId
              ArnLike:
                aws:SourceArn: !Sub "arn:aws:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:*"
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/BedrockAgentCoreFullAccess
      Policies:
        - PolicyName: AgentCoreExecutionPolicy
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Sid: ECRImageAccess
                Effect: Allow
                Action:
                  - ecr:BatchGetImage
                  - ecr:GetDownloadUrlForLayer
                  - ecr:BatchCheckLayerAvailability
                Resource: !GetAtt ECRRepository.Arn
              - Sid: ECRTokenAccess
                Effect: Allow
                Action:
                  - ecr:GetAuthorizationToken
                Resource: "*"
              - Sid: CloudWatchLogs
                Effect: Allow
                Action:
                  - logs:DescribeLogStreams
                  - logs:CreateLogGroup
                  - logs:DescribeLogGroups
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                Resource: "*"
              - Sid: XRayTracing
                Effect: Allow
                Action:
                  - xray:PutTraceSegments
                  - xray:PutTelemetryRecords
                  - xray:GetSamplingRules
                  - xray:GetSamplingTargets
                Resource: "*"
              - Sid: CloudWatchMetrics
                Effect: Allow
                Resource: "*"
                Action: cloudwatch:PutMetricData
                Condition:
                  StringEquals:
                    cloudwatch:namespace: bedrock-agentcore
      Tags:
        - Key: Name
          Value: !Sub "${AWS::StackName}-agent-execution-role"
        - Key: StackName
          Value: !Ref AWS::StackName
        - Key: Module
          Value: IAM

  # CodeBuild Service Role
  CodeBuildRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub "${AWS::StackName}-codebuild-role"
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: codebuild.amazonaws.com
            Action: sts:AssumeRole
      Policies:
        - PolicyName: CodeBuildPolicy
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Sid: CloudWatchLogs
                Effect: Allow
                Action:
                  - logs:CreateLogGroup
                  - logs:CreateLogStream
                  - logs:PutLogEvents
                Resource: !Sub "arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/codebuild/*"
              - Sid: ECRAccess
                Effect: Allow
                Action:
                  - ecr:BatchCheckLayerAvailability
                  - ecr:GetDownloadUrlForLayer
                  - ecr:BatchGetImage
                  - ecr:GetAuthorizationToken
                  - ecr:PutImage
                  - ecr:InitiateLayerUpload
                  - ecr:UploadLayerPart
                  - ecr:CompleteLayerUpload
                Resource:
                  - !GetAtt ECRRepository.Arn
                  - "*"
      Tags:
        - Key: Name
          Value: !Sub "${AWS::StackName}-codebuild-role"
        - Key: StackName
          Value: !Ref AWS::StackName
        - Key: Module
          Value: IAM

  # Lambda Custom Resource Role
  CustomResourceRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: !Sub "${AWS::StackName}-custom-resource-role"
      AssumeRolePolicyDocument:
        Version: "2012-10-17"
        Statement:
          - Effect: Allow
            Principal:
              Service: lambda.amazonaws.com
            Action: sts:AssumeRole
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
      Policies:
        - PolicyName: CustomResourcePolicy
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Sid: CodeBuildAccess
                Effect: Allow
                Action:
                  - codebuild:StartBuild
                  - codebuild:BatchGetBuilds
                  - codebuild:BatchGetProjects
                Resource: !GetAtt MCPServerImageBuildProject.Arn
              - Sid: CognitoAccess
                Effect: Allow
                Action:
                  - cognito-idp:AdminSetUserPassword
                Resource: !GetAtt CognitoUserPool.Arn
      Tags:
        - Key: Name
          Value: !Sub "${AWS::StackName}-custom-resource-role"
        - Key: StackName
          Value: !Ref AWS::StackName
        - Key: Module
          Value: IAM

  # ========================================================================
  # LAMBDA MODULE - Custom Resources
  # ========================================================================

  CodeBuildTriggerFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub "${AWS::StackName}-codebuild-trigger"
      Description: "Triggers CodeBuild projects as CloudFormation custom resource"
      Handler: index.handler
      Role: !GetAtt CustomResourceRole.Arn
      Runtime: python3.9
      Timeout: 900
      Code:
        ZipFile: |
          import boto3
          import cfnresponse
          import json
          import logging
          import time

          logger = logging.getLogger()
          logger.setLevel(logging.INFO)

          def handler(event, context):
              logger.info('Received event: %s', json.dumps(event))

              try:
                  if event['RequestType'] == 'Delete':
                      cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
                      return

                  project_name = event['ResourceProperties']['ProjectName']
                  wait_for_completion = event['ResourceProperties'].get('WaitForCompletion', 'true').lower() == 'true'

                  logger.info(f"Attempting to start CodeBuild project: {project_name}")
                  logger.info(f"Wait for completion: {wait_for_completion}")

                  codebuild = boto3.client('codebuild')

                  try:
                      project_info = codebuild.batch_get_projects(names=[project_name])
                      if not project_info['projects']:
                          raise Exception(f"CodeBuild project '{project_name}' not found")
                      logger.info(f"CodeBuild project '{project_name}' found")
                  except Exception as e:
                      logger.error(f"Error checking project existence: {str(e)}")
                      raise

                  response = codebuild.start_build(projectName=project_name)
                  build_id = response['build']['id']

                  logger.info(f"Successfully started build: {build_id}")

                  if not wait_for_completion:
                      cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                          'BuildId': build_id,
                          'Status': 'STARTED'
                      })
                      return

                  max_wait_time = context.get_remaining_time_in_millis() / 1000 - 30
                  start_time = time.time()

                  while True:
                      if time.time() - start_time > max_wait_time:
                          error_message = f"Build {build_id} timed out"
                          logger.error(error_message)
                          cfnresponse.send(event, context, cfnresponse.FAILED, {'Error': error_message})
                          return

                      build_response = codebuild.batch_get_builds(ids=[build_id])
                      build_status = build_response['builds'][0]['buildStatus']

                      if build_status == 'SUCCEEDED':
                          logger.info(f"Build {build_id} succeeded")
                          cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                              'BuildId': build_id,
                              'Status': build_status
                          })
                          return
                      elif build_status in ['FAILED', 'FAULT', 'STOPPED', 'TIMED_OUT']:
                          error_message = f"Build {build_id} failed with status: {build_status}"
                          logger.error(error_message)

                          try:
                              logs_info = build_response['builds'][0].get('logs', {})
                              if logs_info.get('groupName') and logs_info.get('streamName'):
                                  logger.info(f"Build logs available in CloudWatch")
                          except Exception as log_error:
                              logger.warning(f"Could not get log information: {log_error}")

                          cfnresponse.send(event, context, cfnresponse.FAILED, {
                              'Error': error_message,
                              'BuildId': build_id
                          })
                          return

                      logger.info(f"Build {build_id} status: {build_status}")
                      time.sleep(30)

              except Exception as e:
                  logger.error('Error: %s', str(e))
                  cfnresponse.send(event, context, cfnresponse.FAILED, {
                      'Error': str(e)
                  })
      Tags:
        - Key: Name
          Value: !Sub "${AWS::StackName}-codebuild-trigger"
        - Key: StackName
          Value: !Ref AWS::StackName
        - Key: Module
          Value: Lambda

  CognitoPasswordSetterFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub "${AWS::StackName}-cognito-password-setter"
      Description: "Sets Cognito user password"
      Handler: index.handler
      Role: !GetAtt CustomResourceRole.Arn
      Runtime: python3.9
      Timeout: 300
      Code:
        ZipFile: |
          import boto3
          import cfnresponse
          import json
          import logging

          logger = logging.getLogger()
          logger.setLevel(logging.INFO)

          def handler(event, context):
              logger.info('Received event: %s', json.dumps(event))

              try:
                  if event['RequestType'] == 'Delete':
                      cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
                      return

                  user_pool_id = event['ResourceProperties']['UserPoolId']
                  username = event['ResourceProperties']['Username']
                  password = event['ResourceProperties']['Password']

                  cognito = boto3.client('cognito-idp')

                  # Set permanent password
                  cognito.admin_set_user_password(
                      UserPoolId=user_pool_id,
                      Username=username,
                      Password=password,
                      Permanent=True
                  )

                  logger.info(f"Password set successfully for user: {username}")

                  cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                      'Status': 'SUCCESS'
                  })

              except Exception as e:
                  logger.error('Error: %s', str(e))
                  cfnresponse.send(event, context, cfnresponse.FAILED, {
                      'Error': str(e)
                  })
      Tags:
        - Key: Name
          Value: !Sub "${AWS::StackName}-cognito-password-setter"
        - Key: StackName
          Value: !Ref AWS::StackName
        - Key: Module
          Value: Lambda

  # ========================================================================
  # CODEBUILD MODULE - Container Image Building
  # ========================================================================

  MCPServerImageBuildProject:
    Type: AWS::CodeBuild::Project
    Properties:
      Name: !Sub "${AWS::StackName}-mcp-server-build"
      Description: !Sub "Build MCP server Docker image for ${AWS::StackName}"
      ServiceRole: !GetAtt CodeBuildRole.Arn
      Artifacts:
        Type: NO_ARTIFACTS
      Environment:
        Type: ARM_CONTAINER
        ComputeType: BUILD_GENERAL1_LARGE
        Image: aws/codebuild/amazonlinux2-aarch64-standard:3.0
        PrivilegedMode: true
        EnvironmentVariables:
          - Name: AWS_DEFAULT_REGION
            Value: !Ref AWS::Region
          - Name: AWS_ACCOUNT_ID
            Value: !Ref AWS::AccountId
          - Name: IMAGE_REPO_NAME
            Value: !Ref ECRRepository
          - Name: IMAGE_TAG
            Value: !Ref ImageTag
          - Name: STACK_NAME
            Value: !Ref AWS::StackName
      Source:
        Type: NO_SOURCE
        BuildSpec: |
          version: 0.2
          phases:
            pre_build:
              commands:
                - echo Logging in to Amazon ECR...
                - aws ecr get-login-password --region $AWS_DEFAULT_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com
            build:
              commands:
                - echo Build started on `date`
                - echo Building the Docker image for MCP server ARM64...

                # Create requirements.txt
                - |
                  cat > requirements.txt << 'EOF'
                  mcp>=1.10.0
                  boto3
                  bedrock-agentcore
                  EOF

                # Create mcp_server.py
                - |
                  cat > mcp_server.py << 'EOF'
                  from mcp.server.fastmcp import FastMCP
                  from starlette.responses import JSONResponse

                  mcp = FastMCP(host="0.0.0.0", stateless_http=True)

                  @mcp.tool()
                  def add_numbers(a: int, b: int) -> int:
                      """Add two numbers together"""
                      return a + b

                  @mcp.tool()
                  def multiply_numbers(a: int, b: int) -> int:
                      """Multiply two numbers together"""
                      return a * b

                  @mcp.tool()
                  def greet_user(name: str) -> str:
                      """Greet a user by name"""
                      return f"Hello, {name}! Nice to meet you."

                  if __name__ == "__main__":
                      mcp.run(transport="streamable-http")
                  EOF

                # Create Dockerfile
                - |
                  cat > Dockerfile << 'EOF'
                  FROM public.ecr.aws/docker/library/python:3.11-slim
                  WORKDIR /app

                  COPY requirements.txt requirements.txt
                  RUN pip install -r requirements.txt

                  ENV AWS_REGION=us-west-2
                  ENV AWS_DEFAULT_REGION=us-west-2

                  # Create non-root user
                  RUN useradd -m -u 1000 bedrock_agentcore
                  USER bedrock_agentcore

                  EXPOSE 8000

                  COPY . .

                  CMD ["python", "-m", "mcp_server"]
                  EOF

                # Build the image
                - echo Building ARM64 image...
                - docker build -t $IMAGE_REPO_NAME:$IMAGE_TAG .
                - docker tag $IMAGE_REPO_NAME:$IMAGE_TAG $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/$IMAGE_REPO_NAME:$IMAGE_TAG

            post_build:
              commands:
                - echo Build completed on `date`
                - echo Pushing the Docker image...
                - docker push $AWS_ACCOUNT_ID.dkr.ecr.$AWS_DEFAULT_REGION.amazonaws.com/$IMAGE_REPO_NAME:$IMAGE_TAG
                - echo ARM64 Docker image pushed successfully

      Tags:
        - Key: Name
          Value: !Sub "${AWS::StackName}-mcp-server-build"
        - Key: StackName
          Value: !Ref AWS::StackName
        - Key: Module
          Value: CodeBuild

  # CUSTOM RESOURCE - Trigger Image Build
  TriggerImageBuild:
    Type: Custom::CodeBuildTrigger
    DependsOn:
      - ECRRepository
      - MCPServerImageBuildProject
      - CodeBuildTriggerFunction
    Properties:
      ServiceToken: !GetAtt CodeBuildTriggerFunction.Arn
      ProjectName: !Ref MCPServerImageBuildProject
      WaitForCompletion: "true"

  # ========================================================================
  # AGENTCORE MODULE - MCP Server Runtime
  # ========================================================================

  MCPServerRuntime:
    Type: AWS::BedrockAgentCore::Runtime
    DependsOn:
      - TriggerImageBuild
    Properties:
      AgentRuntimeName: !Sub
        - "${StackNameUnderscore}_${AgentName}"
        - StackNameUnderscore: !Join ["_", !Split ["-", !Ref "AWS::StackName"]]
      AgentRuntimeArtifact:
        ContainerConfiguration:
          ContainerUri: !Sub "${ECRRepository.RepositoryUri}:${ImageTag}"
      RoleArn: !GetAtt AgentExecutionRole.Arn
      NetworkConfiguration:
        NetworkMode: !Ref NetworkMode
      ProtocolConfiguration: MCP
      AuthorizerConfiguration:
        CustomJWTAuthorizer:
          AllowedClients:
            - !Ref CognitoUserPoolClient
          DiscoveryUrl: !Sub "https://cognito-idp.${AWS::Region}.amazonaws.com/${CognitoUserPool}/.well-known/openid-configuration"
      Description: !Sub "MCP server runtime for ${AWS::StackName}"

# ============================================================================
# OUTPUTS SECTION
# ============================================================================
Outputs:
  # AGENTCORE MODULE OUTPUTS
  MCPServerRuntimeId:
    Description: "ID of the created MCP server runtime"
    Value: !GetAtt MCPServerRuntime.AgentRuntimeId
    Export:
      Name: !Sub "${AWS::StackName}-MCPServerRuntimeId"

  MCPServerRuntimeArn:
    Description: "ARN of the created MCP server runtime"
    Value: !GetAtt MCPServerRuntime.AgentRuntimeArn
    Export:
      Name: !Sub "${AWS::StackName}-MCPServerRuntimeArn"

  MCPServerInvocationURL:
    Description: "URL to invoke the MCP server"
    Value: !Sub
      - "https://bedrock-agentcore.${AWS::Region}.amazonaws.com/runtimes/${EncodedArn}/invocations?qualifier=DEFAULT"
      - EncodedArn: !Join
          - ""
          - - !Select [0, !Split [":", !GetAtt MCPServerRuntime.AgentRuntimeArn]]
            - "%3A"
            - !Select [1, !Split [":", !GetAtt MCPServerRuntime.AgentRuntimeArn]]
            - "%3A"
            - !Select [2, !Split [":", !GetAtt MCPServerRuntime.AgentRuntimeArn]]
            - "%3A"
            - !Select [3, !Split [":", !GetAtt MCPServerRuntime.AgentRuntimeArn]]
            - "%3A"
            - !Select [4, !Split [":", !GetAtt MCPServerRuntime.AgentRuntimeArn]]
            - "%3A"
            - !Select [5, !Split [":", !GetAtt MCPServerRuntime.AgentRuntimeArn]]
            - "%2F"
            - !Select [1, !Split ["/", !GetAtt MCPServerRuntime.AgentRuntimeArn]]
    Export:
      Name: !Sub "${AWS::StackName}-MCPServerInvocationURL"

  # ECR OUTPUTS
  ECRRepositoryUri:
    Description: "URI of the ECR repository"
    Value: !GetAtt ECRRepository.RepositoryUri
    Export:
      Name: !Sub "${AWS::StackName}-ECRRepositoryUri"

  # IAM OUTPUTS
  AgentExecutionRoleArn:
    Description: "ARN of the agent execution role"
    Value: !GetAtt AgentExecutionRole.Arn
    Export:
      Name: !Sub "${AWS::StackName}-AgentExecutionRoleArn"

  # COGNITO OUTPUTS
  CognitoUserPoolId:
    Description: "ID of the Cognito User Pool"
    Value: !Ref CognitoUserPool
    Export:
      Name: !Sub "${AWS::StackName}-CognitoUserPoolId"

  CognitoUserPoolClientId:
    Description: "ID of the Cognito User Pool Client"
    Value: !Ref CognitoUserPoolClient
    Export:
      Name: !Sub "${AWS::StackName}-CognitoUserPoolClientId"

  CognitoDiscoveryUrl:
    Description: "Cognito OIDC Discovery URL"
    Value: !Sub "https://cognito-idp.${AWS::Region}.amazonaws.com/${CognitoUserPool}/.well-known/openid-configuration"
    Export:
      Name: !Sub "${AWS::StackName}-CognitoDiscoveryUrl"

  # AUTHENTICATION INFO
  TestUsername:
    Description: "Test username for authentication"
    Value: "testuser"

  TestPassword:
    Description: "Test password for authentication"
    Value: "MyPassword123!"

  GetTokenCommand:
    Description: "Command to get authentication token"
    Value: !Sub |
      python get_token.py ${CognitoUserPoolClient} testuser MyPassword123!
```
