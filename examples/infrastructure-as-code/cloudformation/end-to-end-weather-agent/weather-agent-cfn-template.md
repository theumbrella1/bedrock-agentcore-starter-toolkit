````
AWSTemplateFormatVersion: "2010-09-09"
Description: "Complete AgentCore deployment - Single stack with modular organization"

# ============================================================================
# PARAMETERS SECTION
# ============================================================================
Parameters:
  # Agent Configuration
  AgentName:
    Type: String
    Default: "TestAgent"
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
    Default: "agent-cfn-weather"
    Description: "Name of the ECR repository"

  # Memory Configuration
  MemoryName:
    Type: String
    Default: "TestAgentCoreMemoryWeather"
    Description: "Name for the AgentCore memory resource"
    AllowedPattern: "^[a-zA-Z][a-zA-Z0-9_]{0,47}$"
    ConstraintDescription: "Must start with a letter, max 48 characters, alphanumeric and underscores only"

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
      - Label:
          default: "Memory Configuration"
        Parameters:
          - MemoryName
    ParameterLabels:
      AgentName:
        default: "Agent Name"
      NetworkMode:
        default: "Network Mode"
      ECRRepositoryName:
        default: "ECR Repository Name"
      ImageTag:
        default: "Image Tag"
      MemoryName:
        default: "Memory Name"

# ============================================================================
# RESOURCES SECTION - ORGANIZED BY MODULE
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
  # S3 MODULE - Results Storage
  # ========================================================================

  ResultsBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub "${AWS::StackName}-results-${AWS::AccountId}"
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      VersioningConfiguration:
        Status: Enabled
      Tags:
        - Key: Name
          Value: !Sub "${AWS::StackName}-results-bucket"
        - Key: StackName
          Value: !Ref AWS::StackName
        - Key: Module
          Value: S3

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
              - Sid: S3ResultsAccess
                Effect: Allow
                Action:
                  - s3:PutObject
                  - s3:GetObject
                  - s3:DeleteObject
                Resource: !Sub "${ResultsBucket.Arn}/*"
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
              - Sid: BedrockAgentCoreMemoryAccess
                Effect: Allow
                Action:
                  - bedrock-agentcore:CreateEvent
                  - bedrock-agentcore:ListEvents
                  - bedrock-agentcore:GetMemory
                Resource: "*"
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

  MemoryInitializerFunction:
    Type: AWS::Lambda::Function
    Properties:
      FunctionName: !Sub "${AWS::StackName}-memory-initializer"
      Description: "Initializes AgentCore Memory with default entries after memory creation"
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
          import time
          from datetime import datetime

          logger = logging.getLogger()
          logger.setLevel(logging.INFO)

          def handler(event, context):
              logger.info('Received event: %s', json.dumps(event))

              try:
                  if event['RequestType'] == 'Delete':
                      # No cleanup needed for memory entries
                      cfnresponse.send(event, context, cfnresponse.SUCCESS, {})
                      return

                  memory_id = event['ResourceProperties']['MemoryId']
                  region = event['ResourceProperties'].get('Region', 'us-west-2')
                  timestamp = datetime.utcnow().isoformat() + 'Z'

                  logger.info(f"Initializing memory entries for Memory ID: {memory_id}")

                  activity_preferences = {
                      "good_weather": ["hiking", "beach volleyball", "outdoor picnic", "farmers market", "gardening", "photography", "bird watching"],
                      "ok_weather": ["walking tours", "outdoor dining", "park visits", "museums"],
                      "poor_weather": ["indoor museums", "shopping", "restaurants", "movies"]
                  }

                  # Convert the dictionary to a JSON string for storage in the blob
                  activity_preferences_json = json.dumps(activity_preferences)

                  # Initialize the bedrock-agentcore client
                  client = boto3.client('bedrock-agentcore', region_name=region)

                  response = client.create_event(
                      memoryId=memory_id,
                      actorId="user123",
                      sessionId="session456",
                      eventTimestamp=timestamp,
                      payload=[
                          {
                              'blob': activity_preferences_json,
                          }
                      ]
                  )
                  logger.info(f"Successfully created memory event: {response}")

                  cfnresponse.send(event, context, cfnresponse.SUCCESS, {
                      'MemoryId': memory_id,
                      'Status': 'INITIALIZED'
                  })

              except Exception as e:
                  logger.error('Error initializing memory: %s', str(e))
                  cfnresponse.send(event, context, cfnresponse.FAILED, {
                      'Error': str(e)
                  })
      Tags:
        - Key: Name
          Value: !Sub "${AWS::StackName}-memory-initializer"
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
      Name: !Sub "${AWS::StackName}-strands-agent-build"
      Description: !Sub "Build Strands agent Docker image for ${AWS::StackName}"
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
                - echo Building the Docker image for default agent ARM64...

                # Step 1.1: Create requirements.txt
                - |
                  cat > requirements.txt << 'EOF'
                  strands-agents
                  strands-agents-tools
                  uv
                  boto3
                  bedrock-agentcore
                  bedrock-agentcore-starter-toolkit
                  browser-use==0.3.2
                  langchain-aws>=0.1.0
                  rich
                  EOF

                # Step 1.2: Create my_agent.py
                - |
                  cat > my_agent.py << 'EOF'
                  from strands import Agent, tool
                  from strands_tools import use_aws
                  from typing import Dict, Any
                  import json
                  import os
                  import asyncio
                  from contextlib import suppress

                  from bedrock_agentcore.tools.browser_client import BrowserClient
                  from browser_use import Agent as BrowserAgent
                  from browser_use.browser.session import BrowserSession
                  from browser_use.browser import BrowserProfile
                  from langchain_aws import ChatBedrockConverse
                  from bedrock_agentcore.tools.code_interpreter_client import CodeInterpreter
                  from bedrock_agentcore.memory import MemoryClient
                  from rich.console import Console
                  import re

                  from bedrock_agentcore.runtime import BedrockAgentCoreApp
                  app = BedrockAgentCoreApp()

                  console = Console()

                  # Configuration
                  BROWSER_ID = os.getenv('BROWSER_ID', "agentcore_dev_browser-Df3lyxkbjo")
                  CODE_INTERPRETER_ID = os.getenv('CODE_INTERPRETER_ID', "agentcore_dev_code_interpreter-IqIg8bqnKn")
                  MEMORY_ID = os.getenv('MEMORY_ID', "agentcore_dev_TestAgentCoreMemory-N7LCAH8ZCK")
                  RESULTS_BUCKET = os.getenv('RESULTS_BUCKET', "default-results-bucket")
                  region = 'us-west-2'

                  # Async helper functions
                  async def run_browser_task(browser_session, bedrock_chat, task: str) -> str:
                      """Run a browser automation task using browser_use"""
                      try:
                          console.print(f"[blue]🤖 Executing browser task:[/blue] {task[:100]}...")

                          agent = BrowserAgent(
                              task=task,
                              llm=bedrock_chat,
                              browser=browser_session
                          )

                          result = await agent.run()
                          console.print("[green]✅ Browser task completed successfully![/green]")

                          if 'done' in result.last_action() and 'text' in result.last_action()['done']:
                              return result.last_action()['done']['text'] 
                          else:
                              raise ValueError("NO Data")

                      except Exception as e:
                          console.print(f"[red]❌ Browser task error: {e}[/red]")
                          raise

                  async def initialize_browser_session():
                      """Initialize Browser-use session with AgentCore WebSocket connection"""
                      try:
                          client = BrowserClient(region)
                          client.start(identifier=BROWSER_ID)

                          ws_url, headers = client.generate_ws_headers()
                          console.print(f"[cyan]🔗 Browser WebSocket URL: {ws_url[:50]}...[/cyan]")

                          browser_profile = BrowserProfile(
                              headers=headers,
                              timeout=150000,
                          )

                          browser_session = BrowserSession(
                              cdp_url=ws_url,
                              browser_profile=browser_profile,
                              keep_alive=True
                          )

                          console.print("[cyan]🔄 Initializing browser session...[/cyan]")
                          await browser_session.start()

                          bedrock_chat = ChatBedrockConverse(
                              model_id="us.anthropic.claude-3-7-sonnet-20250219-v1:0",
                              region_name="us-west-2"
                          )

                          console.print("[green]✅ Browser session initialized and ready[/green]")
                          return browser_session, bedrock_chat, client 

                      except Exception as e:
                          console.print(f"[red]❌ Failed to initialize browser session: {e}[/red]")
                          raise

                  # Tools for Strands Agent
                  @tool
                  async def get_weather_data(city: str) -> Dict[str, Any]:
                      """Get weather data for a city using browser automation"""
                      browser_session = None

                      try:
                          console.print(f"[cyan]🌐 Getting weather data for {city}[/cyan]")

                          browser_session, bedrock_chat, browser_client = await initialize_browser_session()

                          task = f"""Instruction: Extract 8-Day Weather Forecast for {city} from weather.gov
                              Steps:
                                  - Go to https://weather.gov.
                                  - Enter “{city}” into the search box and Click on `GO` to execute the search.
                                  - On the local forecast page, click the "Printable Forecast" link.
                                  - Wait for the printable forecast page to load completely.
                                  - For each day in the forecast, extract these fields:
                                      - date (format YYYY-MM-DD) 
                                      - high (highest temperature)
                                      - low (lowest temperature)
                                      - conditions (short weather summary, e.g., "Clear")
                                      - wind (wind speed as an integer; use mph or km/h as consistent)
                                      - precip (precipitation chance or amount, zero if none)
                                  - Format the extracted data as a JSON array of daily forecast objects, e.g.:
                                      ```json
                                      [
                                      {{
                                          "date": "2025-09-17",
                                          "high": 78,
                                          "low": 62,
                                          "conditions": "Clear",
                                          "wind": 10,
                                          "precip": 80
                                      }},
                                      {{
                                          "date": "2025-09-18",
                                          "high": 82,
                                          "low": 65,
                                          "conditions": "Partly Cloudy",
                                          "wind": 10,
                                          "precip": 80

                                      }}
                                      // ... Repeat for each day ...
                                      ]```

                                  - Return only this JSON array as the final output.

                              Additional Notes:
                                  Use null or 0 if any numeric value is missing.
                                  Avoid scraping ads, navigation, or unrelated page elements.
                                  If "Printable Forecast" is missing, fallback to the main forecast page.
                                  Include error handling (e.g., return an empty array if forecast data isn't found).
                                  Confirm the city name matches the requested location before returning results. 
                          """

                          result = await run_browser_task(browser_session, bedrock_chat, task)

                          if browser_client :
                              browser_client.stop()

                          return {
                              "status": "success",
                              "content": [{"text": result}]
                          }

                      except Exception as e:
                          console.print(f"[red]❌ Error getting weather data: {e}[/red]")
                          return {
                              "status": "error",
                              "content": [{"text": f"Error getting weather data: {str(e)}"}]
                          }

                      finally:
                          if browser_session:
                              console.print("[yellow]🔌 Closing browser session...[/yellow]")
                              with suppress(Exception):
                                  await browser_session.close()
                              console.print("[green]✅ Browser session closed[/green]")

                  @tool
                  def generate_analysis_code(weather_data: str) -> Dict[str, Any]:
                      """Generate Python code for weather classification"""
                      try:
                          query = f"""Create Python code to classify weather days as GOOD/OK/POOR:

                          Rules: 
                          - GOOD: 65-80°F, clear conditions, no rain
                          - OK: 55-85°F, partly cloudy, slight rain chance  
                          - POOR: <55°F or >85°F, cloudy/rainy

                          Weather data: 
                          {weather_data} 

                          Store weather data stored in python variable for using it in python code 

                          Return code that outputs list of tuples: [('2025-09-16', 'GOOD'), ('2025-09-17', 'OK'), ...]"""

                          agent = Agent()
                          result = agent(query)

                          pattern = r'```(?:json|python)\n(.*?)\n```'
                          match = re.search(pattern, result.message['content'][0]['text'], re.DOTALL)
                          python_code = match.group(1).strip() if match else result.message['content'][0]['text']

                          return {"status": "success", "content": [{"text": python_code}]}
                      except Exception as e:
                          return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}

                  @tool 
                  def execute_code(python_code: str) -> Dict[str, Any]:
                      """Execute Python code using AgentCore Code Interpreter"""
                      try:
                          code_client = CodeInterpreter('us-west-2')
                          code_client.start(identifier=CODE_INTERPRETER_ID)

                          response = code_client.invoke("executeCode", {
                              "code": python_code,
                              "language": "python",
                              "clearContext": True
                          })

                          for event in response["stream"]:
                              code_execute_result = json.dumps(event["result"])

                          analysis_results = json.loads(code_execute_result)
                          console.print("Analysis results:", analysis_results)

                          return {"status": "success", "content": [{"text": str(analysis_results)}]}

                      except Exception as e:
                          return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}

                  @tool
                  def get_activity_preferences() -> Dict[str, Any]:
                      """Get activity preferences from memory"""
                      try:
                          client = MemoryClient(region_name='us-west-2')
                          response = client.list_events(
                              memory_id=MEMORY_ID,
                              actor_id="user123",
                              session_id="session456",
                              max_results=50,
                              include_payload=True
                          )

                          preferences = response[0]["payload"][0]['blob'] if response else "No preferences found"
                          return {"status": "success", "content": [{"text": preferences}]}
                      except Exception as e:
                          return {"status": "error", "content": [{"text": f"Error: {str(e)}"}]}

                  def create_weather_agent() -> Agent:
                      """Create the weather agent with all tools"""
                      system_prompt = f"""You are a Weather-Based Activity Planning Assistant.

                      When a user asks about activities for a location, follow below stepes Sequentially:
                      1. Extract city from user query
                      2. Call get_weather_data(city) to get weather information
                      3. Call generate_analysis_code(weather_data) to create classification code
                      4. Call execute_code(python_code) to get Day Type ( GOOD, OK , POOR ) for forecasting dates. 
                      5. Call get_activity_preferences() to get user preferences
                      6. Generate Activity Recommendations based on weather and preferences that you have recieved from previous steps
                      7. Generate the comprehensive Markdown file (results.md) and store it in S3 Bucket :  {RESULTS_BUCKET} through use_aws tool. 

                      IMPORTANT: Provide complete recommendations and end your response. Do NOT ask follow-up questions or wait for additional input."""

                      return Agent(
                          tools=[get_weather_data, generate_analysis_code, execute_code, get_activity_preferences, use_aws],
                          system_prompt=system_prompt,
                          name="WeatherActivityPlanner"
                      )

                  @app.async_task
                  async def async_main(query=None):
                      """Async main function"""
                      console.print("🌤️ Weather-Based Activity Planner - Async Version")
                      console.print("=" * 30)

                      agent = create_weather_agent()

                      query = query or "What should I do this weekend in Richmond VA?"
                      console.print(f"\n[bold blue]🔍 Query:[/bold blue] {query}")
                      console.print("-" * 50)

                      try:
                          os.environ["BYPASS_TOOL_CONSENT"] = "True"
                          result = agent(query)

                          return {
                            "status": "completed",
                            "result": result.message['content'][0]['text']
                          }

                      except Exception as e:
                          console.print(f"[red]❌ Error: {e}[/red]")
                          import traceback
                          traceback.print_exc()
                          return {
                            "status": "error",
                            "error": str(e)
                          }

                  @app.entrypoint
                  async def invoke(payload=None):
                      try:
                          # change
                          query = payload.get("prompt")

                          asyncio.create_task(async_main(query))

                          msg = (
                               "Processing started ... "
                              f"You can monitor status in CloudWatch logs at /aws/bedrock-agentcore/runtimes/<agent-runtime-id> ....."
                              f"You can see the result at {RESULTS_BUCKET} ...."
                          )

                          return {
                              "status": "Started",
                              "message": msg
                          }

                      except Exception as e:
                          return {"error": str(e)}

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

                # Step 1.5: Build the image
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
          Value: !Sub "${AWS::StackName}-strands-build"
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
  # AGENTCORE MODULE - Runtime and Tools
  # ========================================================================

  # AgentCore Runtime
  AgentRuntime:
    Type: AWS::BedrockAgentCore::Runtime
    DependsOn: 
      - TriggerImageBuild
      - BrowserTool
      - CodeInterpreterTool
      - BasicMemory
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
      Description: !Sub "Strands agent runtime for ${AWS::StackName}"
      EnvironmentVariables:
        BROWSER_ID: !GetAtt BrowserTool.BrowserId
        CODE_INTERPRETER_ID: !GetAtt CodeInterpreterTool.CodeInterpreterId
        MEMORY_ID: !GetAtt BasicMemory.MemoryId
        RESULTS_BUCKET: !Ref ResultsBucket


  # Browser Tool
  BrowserTool:
    Type: AWS::BedrockAgentCore::BrowserCustom
    Properties:
      Name: !Sub 
        - "${StackNameUnderscore}_browser"
        - StackNameUnderscore: !Join ["_", !Split ["-", !Ref "AWS::StackName"]]
      Description: !Sub "Browser tool for ${AWS::StackName} web automation"
      NetworkConfiguration:
        NetworkMode: !Ref NetworkMode
      RecordingConfig:
        Enabled: false

  # Code Interpreter Tool
  CodeInterpreterTool:
    Type: AWS::BedrockAgentCore::CodeInterpreterCustom
    Properties:
      Name: !Sub 
        - "${StackNameUnderscore}_code_interpreter"
        - StackNameUnderscore: !Join ["_", !Split ["-", !Ref "AWS::StackName"]]
      Description: !Sub "Code interpreter tool for ${AWS::StackName} code execution"
      NetworkConfiguration:
        NetworkMode: !Ref NetworkMode

  # Basic Memory
  BasicMemory:
    Type: AWS::BedrockAgentCore::Memory
    Properties:
      Name: !Sub 
        - "${StackNameUnderscore}_${MemoryName}"
        - StackNameUnderscore: !Join ["_", !Split ["-", !Ref "AWS::StackName"]]
      Description: !Sub "Memory created for ${AWS::StackName} integration testing"
      EventExpiryDuration: 30

  # ========================================================================
  # CUSTOM RESOURCE - Initialize Memory with Default Entries
  # ========================================================================

  InitializeMemoryEntries:
    Type: Custom::MemoryInitializer
    DependsOn:
      - BasicMemory
      - MemoryInitializerFunction
    Properties:
      ServiceToken: !GetAtt MemoryInitializerFunction.Arn
      MemoryId: !GetAtt BasicMemory.MemoryId
      Region: !Ref AWS::Region

# ============================================================================
# OUTPUTS SECTION - ORGANIZED BY MODULE
# ============================================================================
Outputs:
  # AGENTCORE MODULE OUTPUTS
  AgentRuntimeId:
    Description: "ID of the created agent runtime"
    Value: !GetAtt AgentRuntime.AgentRuntimeId
    Export:
      Name: !Sub "${AWS::StackName}-AgentRuntimeId"

  BrowserId:
    Description: ID of the created browser
    Value: !GetAtt BrowserTool.BrowserId
    Export:
      Name: !Sub "${AWS::StackName}-BrowserId"

  CodeInterpreterId:
    Description: ID of the created code interpreter
    Value: !GetAtt CodeInterpreterTool.CodeInterpreterId
    Export:
      Name: !Sub "${AWS::StackName}-CodeInterpreterId"

  MemoryId:
    Description: "ID of the created memory"
    Value: !GetAtt BasicMemory.MemoryId
    Export:
      Name: !Sub "${AWS::StackName}-MemoryId"

  ResultsBucket:
    Description: "S3 bucket for storing agent results"
    Value: !Ref ResultsBucket
    Export:
      Name: !Sub "${AWS::StackName}-ResultsBucket"
````
