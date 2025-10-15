```
AWSTemplateFormatVersion: "2010-09-09"
Description: "Basic AgentCore deployment - Simple agent runtime without memory, code interpreter, or browser"

# ============================================================================
# PARAMETERS SECTION
# ============================================================================
Parameters:
  # Agent Configuration
  AgentName:
    Type: String
    Default: "BasicAgent"
    Description: "Name for the agent runtime"
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
    Default: "basic-agent"
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
              - Sid: GetAgentAccessToken
                Effect: Allow
                Action:
                  - bedrock-agentcore:GetWorkloadAccessToken
                  - bedrock-agentcore:GetWorkloadAccessTokenForJWT
                  - bedrock-agentcore:GetWorkloadAccessTokenForUserId
                Resource:
                  - !Sub "arn:aws:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:workload-identity-directory/default"
                  - !Sub "arn:aws:bedrock-agentcore:${AWS::Region}:${AWS::AccountId}:workload-identity-directory/default/workload-identity/*"
              - Sid: BedrockModelInvocation
                Effect: Allow
                Action:
                  - bedrock:InvokeModel
                  - bedrock:InvokeModelWithResponseStream
                Resource: "*"
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
              - Sid: ECRAccess
                Effect: Allow
                Action:
                  - ecr:ListImages
                  - ecr:BatchDeleteImage
                  - ecr:GetAuthorizationToken
                  - ecr:BatchGetImage
                  - ecr:GetDownloadUrlForLayer
                  - ecr:PutImage
                  - ecr:InitiateLayerUpload
                  - ecr:UploadLayerPart
                  - ecr:CompleteLayerUpload
                Resource: !GetAtt ECRRepository.Arn
              - Sid: CodeBuildAccess
                Effect: Allow
                Action:
                  - codebuild:StartBuild
                  - codebuild:BatchGetBuilds
                  - codebuild:BatchGetProjects
                Resource: !GetAtt AgentImageBuildProject.Arn
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

                  # Start the CodeBuild project
                  codebuild = boto3.client('codebuild')

                  # First, verify the project exists
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

                  # Wait for the build to complete
                  max_wait_time = context.get_remaining_time_in_millis() / 1000 - 30  # Leave 30s buffer
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

                          # Get build logs for debugging
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
                      time.sleep(30)  # Check every 30 seconds

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

  # ========================================================================
  # CODEBUILD MODULE - Container Image Building
  # ========================================================================

  AgentImageBuildProject:
    Type: AWS::CodeBuild::Project
    Properties:
      Name: !Sub "${AWS::StackName}-basic-agent-build"
      Description: !Sub "Build basic agent Docker image for ${AWS::StackName}"
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
                - echo Building the Docker image for basic agent ARM64...

                # Step 1.1: Create requirements.txt
                - |
                  cat > requirements.txt << 'EOF'
                  strands-agents
                  boto3
                  bedrock-agentcore
                  EOF

                # Step 1.2: Create my_agent.py (simplified basic version)
                - |
                  cat > my_agent.py << 'EOF'
                  from strands import Agent
                  import os
                  from bedrock_agentcore.runtime import BedrockAgentCoreApp

                  app = BedrockAgentCoreApp()

                  def create_basic_agent() -> Agent:
                      """Create a basic agent with simple functionality"""
                      system_prompt = """You are a helpful assistant. Answer questions clearly and concisely."""

                      return Agent(
                          system_prompt=system_prompt,
                          name="BasicAgent"
                      )

                  @app.entrypoint
                  async def invoke(payload=None):
                      """Main entrypoint for the agent"""
                      try:
                          # Get the query from payload
                          query = payload.get("prompt", "Hello, how are you?") if payload else "Hello, how are you?"

                          # Create and use the agent
                          agent = create_basic_agent()
                          response = agent(query)

                          return {
                              "status": "success",
                              "response": response.message['content'][0]['text']
                          }

                      except Exception as e:
                          return {
                              "status": "error",
                              "error": str(e)
                          }

                  if __name__ == "__main__":
                      app.run()
                  EOF

                # Step 1.3: Create Dockerfile
                - |
                  cat > Dockerfile << 'EOF'
                  FROM public.ecr.aws/docker/library/python:3.11-slim
                  WORKDIR /app

                  COPY requirements.txt requirements.txt
                  RUN pip install -r requirements.txt
                  RUN pip install aws-opentelemetry-distro>=0.10.1

                  ENV AWS_REGION=us-west-2
                  ENV AWS_DEFAULT_REGION=us-west-2

                  # Create non-root user
                  RUN useradd -m -u 1000 bedrock_agentcore
                  USER bedrock_agentcore

                  EXPOSE 8080
                  EXPOSE 8000

                  COPY . .

                  CMD ["opentelemetry-instrument", "python", "-m", "my_agent"]
                  EOF

                # Step 1.4: Build the image
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
          Value: !Sub "${AWS::StackName}-basic-build"
        - Key: StackName
          Value: !Ref AWS::StackName
        - Key: Module
          Value: CodeBuild

  # CUSTOM RESOURCE - Trigger Image Build
  TriggerImageBuild:
    Type: Custom::CodeBuildTrigger
    DependsOn:
      - ECRRepository
      - AgentImageBuildProject
      - CodeBuildTriggerFunction
    Properties:
      ServiceToken: !GetAtt CodeBuildTriggerFunction.Arn
      ProjectName: !Ref AgentImageBuildProject
      WaitForCompletion: "true"

  # ========================================================================
  # AGENTCORE MODULE - Runtime Only (No Tools)
  # ========================================================================

  # AgentCore Runtime
  AgentRuntime:
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
      Description: !Sub "Basic agent runtime for ${AWS::StackName}"

# ============================================================================
# OUTPUTS SECTION
# ============================================================================
Outputs:
  # AGENTCORE MODULE OUTPUTS
  AgentRuntimeId:
    Description: "ID of the created agent runtime"
    Value: !GetAtt AgentRuntime.AgentRuntimeId
    Export:
      Name: !Sub "${AWS::StackName}-AgentRuntimeId"

  ECRRepositoryUri:
    Description: "URI of the ECR repository"
    Value: !GetAtt ECRRepository.RepositoryUri
    Export:
      Name: !Sub "${AWS::StackName}-ECRRepositoryUri"

  AgentExecutionRoleArn:
    Description: "ARN of the agent execution role"
    Value: !GetAtt AgentExecutionRole.Arn
    Export:
      Name: !Sub "${AWS::StackName}-AgentExecutionRoleArn"
```
