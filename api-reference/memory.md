# Memory

Memory management for Bedrock AgentCore SDK.

## `bedrock_agentcore.memory`

Bedrock AgentCore Memory module for agent memory management capabilities.

### `Actor`

Bases: `DictWrapper`

Represents an actor within a session.

Source code in `bedrock_agentcore/memory/session.py`

```
class Actor(DictWrapper):
    """Represents an actor within a session."""

    def __init__(self, actor_id: str, session_manager: MemorySessionManager):
        """Represents an actor within a session.

        :param actor_id: id of the actor
        :param session_manager: Behaviour manager for the operations
        """
        self._id = actor_id
        self._session_manager = session_manager
        super().__init__(self._construct_session_dict())

    def _construct_session_dict(self) -> Dict[str, Any]:
        """Constructs a dictionary representing the actor."""
        return {
            "actorId": self._id,
        }

    def list_sessions(self) -> List[SessionSummary]:
        """Delegates to _session_manager.list_actor_sessions."""
        return self._session_manager.list_actor_sessions(self._id)
```

#### `__init__(actor_id, session_manager)`

Represents an actor within a session.

:param actor_id: id of the actor :param session_manager: Behaviour manager for the operations

Source code in `bedrock_agentcore/memory/session.py`

```
def __init__(self, actor_id: str, session_manager: MemorySessionManager):
    """Represents an actor within a session.

    :param actor_id: id of the actor
    :param session_manager: Behaviour manager for the operations
    """
    self._id = actor_id
    self._session_manager = session_manager
    super().__init__(self._construct_session_dict())
```

#### `list_sessions()`

Delegates to \_session_manager.list_actor_sessions.

Source code in `bedrock_agentcore/memory/session.py`

```
def list_sessions(self) -> List[SessionSummary]:
    """Delegates to _session_manager.list_actor_sessions."""
    return self._session_manager.list_actor_sessions(self._id)
```

### `MemoryClient`

High-level Bedrock AgentCore Memory client with essential operations.

Source code in `bedrock_agentcore/memory/client.py`

```
class MemoryClient:
    """High-level Bedrock AgentCore Memory client with essential operations."""

    # AgentCore Memory data plane methods
    _ALLOWED_GMDP_METHODS = {
        "retrieve_memory_records",
        "get_memory_record",
        "delete_memory_record",
        "list_memory_records",
        "create_event",
        "get_event",
        "delete_event",
        "list_events",
    }

    # AgentCore Memory control plane methods
    _ALLOWED_GMCP_METHODS = {
        "create_memory",
        "get_memory",
        "list_memories",
        "update_memory",
        "delete_memory",
        "list_memory_strategies",
    }

    def __init__(self, region_name: Optional[str] = None):
        """Initialize the Memory client."""
        self.region_name = region_name or boto3.Session().region_name or "us-west-2"

        self.gmcp_client = boto3.client("bedrock-agentcore-control", region_name=self.region_name)
        self.gmdp_client = boto3.client("bedrock-agentcore", region_name=self.region_name)

        logger.info(
            "Initialized MemoryClient for control plane: %s, data plane: %s",
            self.gmcp_client.meta.region_name,
            self.gmdp_client.meta.region_name,
        )

    def __getattr__(self, name: str):
        """Dynamically forward method calls to the appropriate boto3 client.

        This method enables access to all boto3 client methods without explicitly
        defining them. Methods are looked up in the following order:
        1. gmdp_client (bedrock-agentcore) - for data plane operations
        2. gmcp_client (bedrock-agentcore-control) - for control plane operations

        Args:
            name: The method name being accessed

        Returns:
            A callable method from the appropriate boto3 client

        Raises:
            AttributeError: If the method doesn't exist on either client

        Example:
            # Access any boto3 method directly
            client = MemoryClient()

            # These calls are forwarded to the appropriate boto3 client
            response = client.list_memory_records(memoryId="mem-123", namespace="test")
            metadata = client.get_memory_metadata(memoryId="mem-123")
        """
        if name in self._ALLOWED_GMDP_METHODS and hasattr(self.gmdp_client, name):
            method = getattr(self.gmdp_client, name)
            logger.debug("Forwarding method '%s' to gmdp_client", name)
            return method

        if name in self._ALLOWED_GMCP_METHODS and hasattr(self.gmcp_client, name):
            method = getattr(self.gmcp_client, name)
            logger.debug("Forwarding method '%s' to gmcp_client", name)
            return method

        # Method not found on either client
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'. "
            f"Method not found on gmdp_client or gmcp_client. "
            f"Available methods can be found in the boto3 documentation for "
            f"'bedrock-agentcore' and 'bedrock-agentcore-control' services."
        )

    def create_memory(
        self,
        name: str,
        strategies: Optional[List[Dict[str, Any]]] = None,
        description: Optional[str] = None,
        event_expiry_days: int = 90,
        memory_execution_role_arn: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a memory with simplified configuration."""
        if strategies is None:
            strategies = []

        try:
            processed_strategies = self._add_default_namespaces(strategies)

            params = {
                "name": name,
                "eventExpiryDuration": event_expiry_days,
                "memoryStrategies": processed_strategies,  # Using old field name for input
                "clientToken": str(uuid.uuid4()),
            }

            if description is not None:
                params["description"] = description

            if memory_execution_role_arn is not None:
                params["memoryExecutionRoleArn"] = memory_execution_role_arn

            response = self.gmcp_client.create_memory(**params)

            memory = response["memory"]
            # Normalize response to handle new field names
            memory = self._normalize_memory_response(memory)

            logger.info("Created memory: %s", memory["memoryId"])
            return memory

        except ClientError as e:
            logger.error("Failed to create memory: %s", e)
            raise

    def create_or_get_memory(
        self,
        name: str,
        strategies: Optional[List[Dict[str, Any]]] = None,
        description: Optional[str] = None,
        event_expiry_days: int = 90,
        memory_execution_role_arn: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a memory resource or fetch the existing memory details if it already exists.

        Returns:
            Memory object, either newly created or existing
        """
        try:
            memory = self.create_memory_and_wait(
                name=name,
                strategies=strategies,
                description=description,
                event_expiry_days=event_expiry_days,
                memory_execution_role_arn=memory_execution_role_arn,
            )
            return memory
        except ClientError as e:
            if e.response["Error"]["Code"] == "ValidationException" and "already exists" in str(e):
                memories = self.list_memories()
                memory = next((m for m in memories if m["id"].startswith(name)), None)
                logger.info("Memory already exists. Using existing memory ID: %s", memory["id"])
                return memory
            else:
                logger.error("ClientError: Failed to create or get memory: %s", e)
                raise
        except Exception:
            raise

    def create_memory_and_wait(
        self,
        name: str,
        strategies: List[Dict[str, Any]],
        description: Optional[str] = None,
        event_expiry_days: int = 90,
        memory_execution_role_arn: Optional[str] = None,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Create a memory and wait for it to become ACTIVE.

        This method creates a memory and polls until it reaches ACTIVE status,
        providing a convenient way to ensure the memory is ready for use.

        Args:
            name: Name for the memory resource
            strategies: List of strategy configurations
            description: Optional description
            event_expiry_days: How long to retain events (default: 90 days)
            memory_execution_role_arn: IAM role ARN for memory execution
            max_wait: Maximum seconds to wait (default: 300)
            poll_interval: Seconds between status checks (default: 10)

        Returns:
            Created memory object in ACTIVE status

        Raises:
            TimeoutError: If memory doesn't become ACTIVE within max_wait
            RuntimeError: If memory creation fails
        """
        # Create the memory
        memory = self.create_memory(
            name=name,
            strategies=strategies,
            description=description,
            event_expiry_days=event_expiry_days,
            memory_execution_role_arn=memory_execution_role_arn,
        )

        memory_id = memory.get("memoryId", memory.get("id"))  # Handle both field names
        if memory_id is None:
            memory_id = ""
        logger.info("Created memory %s, waiting for ACTIVE status...", memory_id)

        start_time = time.time()
        while time.time() - start_time < max_wait:
            elapsed = int(time.time() - start_time)

            try:
                status = self.get_memory_status(memory_id)

                if status == MemoryStatus.ACTIVE.value:
                    logger.info("Memory %s is now ACTIVE (took %d seconds)", memory_id, elapsed)
                    # Get fresh memory details
                    response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
                    memory = self._normalize_memory_response(response["memory"])
                    return memory
                elif status == MemoryStatus.FAILED.value:
                    # Get failure reason if available
                    response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
                    failure_reason = response["memory"].get("failureReason", "Unknown")
                    raise RuntimeError("Memory creation failed: %s" % failure_reason)
                else:
                    logger.debug("Memory status: %s (%d seconds elapsed)", status, elapsed)

            except ClientError as e:
                logger.error("Error checking memory status: %s", e)
                raise

            time.sleep(poll_interval)

        raise TimeoutError("Memory %s did not become ACTIVE within %d seconds" % (memory_id, max_wait))

    def retrieve_memories(
        self, memory_id: str, namespace: str, query: str, actor_id: Optional[str] = None, top_k: int = 3
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant memories from a namespace.

        Note: Wildcards (*) are NOT supported in namespaces. You must provide the
        exact namespace path with all variables resolved.

        Args:
            memory_id: Memory resource ID
            namespace: Exact namespace path (no wildcards)
            query: Search query
            actor_id: Optional actor ID (deprecated, use namespace)
            top_k: Number of results to return

        Returns:
            List of memory records

        Example:
            # Correct - exact namespace
            memories = client.retrieve_memories(
                memory_id="mem-123",
                namespace="support/facts/session-456",
                query="customer preferences"
            )

            # Incorrect - wildcards not supported
            # memories = client.retrieve_memories(..., namespace="support/facts/*", ...)
        """
        if "*" in namespace:
            logger.error("Wildcards are not supported in namespaces. Please provide exact namespace.")
            return []

        try:
            # Let service handle all namespace validation
            response = self.gmdp_client.retrieve_memory_records(
                memoryId=memory_id, namespace=namespace, searchCriteria={"searchQuery": query, "topK": top_k}
            )

            memories = response.get("memoryRecordSummaries", [])
            logger.info("Retrieved %d memories from namespace: %s", len(memories), namespace)
            return memories

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = e.response["Error"]["Message"]

            if error_code == "ResourceNotFoundException":
                logger.warning(
                    "Memory or namespace not found. Ensure memory %s exists and namespace '%s' is configured",
                    memory_id,
                    namespace,
                )
            elif error_code == "ValidationException":
                logger.warning("Invalid search parameters: %s", error_msg)
            elif error_code == "ServiceException":
                logger.warning("Service error: %s. This may be temporary - try again later", error_msg)
            else:
                logger.warning("Memory retrieval failed (%s): %s", error_code, error_msg)

            return []

    def create_event(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        messages: List[Tuple[str, str]],
        event_timestamp: Optional[datetime] = None,
        branch: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Save an event of an agent interaction or conversation with a user.

        This is the basis of short-term memory. If you configured your Memory resource
        to have MemoryStrategies, then events that are saved in short-term memory via
        create_event will be used to extract long-term memory records.

        Args:
            memory_id: Memory resource ID
            actor_id: Actor identifier (could be id of your user or an agent)
            session_id: Session identifier (meant to logically group a series of events)
            messages: List of (text, role) tuples. Role can be USER, ASSISTANT, TOOL, etc.
            event_timestamp: timestamp for the entire event (not per message)
            branch: Optional branch info. For new branches: {"rootEventId": "...", "name": "..."}
                   For continuing existing branch: {"name": "..."} or {"name": "...", "rootEventId": "..."}
                   A branch is used when you want to have a different history of events.

        Returns:
            Created event

        Example:
            event = client.create_event(
                memory_id=memory.get("id"),
                actor_id="weatherWorrier",
                session_id="WeatherSession",
                messages=[
                    ("What's the weather?", "USER"),
                    ("Today is sunny", "ASSISTANT")
                ]
            )
            root_event_id = event.get("eventId")
            print(event)

            # Continue the conversation
            event = client.create_event(
                memory_id=memory.get("id"),
                actor_id="weatherWorrier",
                session_id="WeatherSession",
                messages=[
                    ("How about the weather tomorrow", "USER"),
                    ("Tomorrow is cold!", "ASSISTANT")
                ]
            )
            print(event)

            # branch the conversation so that the previous message is not part of the history
            # (suppose you did not mean to ask about the weather tomorrow and want to undo
            # that, and replace with a new message)
            event = client.create_event(
                memory_id=memory.get("id"),
                actor_id="weatherWorrier",
                session_id="WeatherSession",
                branch={"name": "differentWeatherQuestion", "rootEventId": root_event_id},
                messages=[
                    ("How about the weather a year from now", "USER"),
                    ("I can't predict that far into the future!", "ASSISTANT")
                ]
            )
            print(event)
        """
        try:
            if not messages:
                raise ValueError("At least one message is required")

            payload = []
            for msg in messages:
                if len(msg) != 2:
                    raise ValueError("Each message must be (text, role)")

                text, role = msg

                try:
                    role_enum = MessageRole(role.upper())
                except ValueError as err:
                    raise ValueError(
                        "Invalid role '%s'. Must be one of: %s" % (role, ", ".join([r.value for r in MessageRole]))
                    ) from err

                payload.append({"conversational": {"content": {"text": text}, "role": role_enum.value}})

            # Use provided timestamp or current time
            if event_timestamp is None:
                event_timestamp = datetime.utcnow()

            params = {
                "memoryId": memory_id,
                "actorId": actor_id,
                "sessionId": session_id,
                "eventTimestamp": event_timestamp,
                "payload": payload,
            }

            if branch:
                params["branch"] = branch

            response = self.gmdp_client.create_event(**params)

            event = response["event"]
            logger.info("Created event: %s", event["eventId"])

            return event

        except ClientError as e:
            logger.error("Failed to create event: %s", e)
            raise

    def create_blob_event(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        blob_data: Any,
        event_timestamp: Optional[datetime] = None,
        branch: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Save a blob event to AgentCore Memory.

        Args:
            memory_id: Memory resource ID
            actor_id: Actor identifier
            session_id: Session identifier
            blob_data: Binary or structured data to store
            event_timestamp: Optional timestamp for the event
            branch: Optional branch info

        Returns:
            Created event

        Example:
            # Store binary data
            event = client.create_blob_event(
                memory_id="mem-xyz",
                actor_id="user-123",
                session_id="session-456",
                blob_data={"file_content": "base64_encoded_data", "metadata": {"type": "image"}}
            )
        """
        try:
            payload = [{"blob": blob_data}]

            if event_timestamp is None:
                event_timestamp = datetime.utcnow()

            params = {
                "memoryId": memory_id,
                "actorId": actor_id,
                "sessionId": session_id,
                "eventTimestamp": event_timestamp,
                "payload": payload,
            }

            if branch:
                params["branch"] = branch

            response = self.gmdp_client.create_event(**params)

            event = response["event"]
            logger.info("Created blob event: %s", event["eventId"])

            return event

        except ClientError as e:
            logger.error("Failed to create blob event: %s", e)
            raise

    def save_conversation(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        messages: List[Tuple[str, str]],
        event_timestamp: Optional[datetime] = None,
        branch: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """DEPRECATED: Use create_event() instead.

        Args:
            memory_id: Memory resource ID
            actor_id: Actor identifier
            session_id: Session identifier
            messages: List of (text, role) tuples. Role can be USER, ASSISTANT, TOOL, etc.
            event_timestamp: Optional timestamp for the entire event (not per message)
            branch: Optional branch info. For new branches: {"rootEventId": "...", "name": "..."}
                   For continuing existing branch: {"name": "..."} or {"name": "...", "rootEventId": "..."}

        Returns:
            Created event

        Example:
            # Save multi-turn conversation
            event = client.save_conversation(
                memory_id="mem-xyz",
                actor_id="user-123",
                session_id="session-456",
                messages=[
                    ("What's the weather?", "USER"),
                    ("And tomorrow?", "USER"),
                    ("Checking weather...", "TOOL"),
                    ("Today sunny, tomorrow rain", "ASSISTANT")
                ]
            )

            # Continue existing branch (only name required)
            event = client.save_conversation(
                memory_id="mem-xyz",
                actor_id="user-123",
                session_id="session-456",
                messages=[("Continue conversation", "USER")],
                branch={"name": "existing-branch"}
            )
        """
        try:
            if not messages:
                raise ValueError("At least one message is required")

            # Build payload
            payload = []

            for msg in messages:
                if len(msg) != 2:
                    raise ValueError("Each message must be (text, role)")

                text, role = msg

                # Validate role
                try:
                    role_enum = MessageRole(role.upper())
                except ValueError as err:
                    raise ValueError(
                        "Invalid role '%s'. Must be one of: %s" % (role, ", ".join([r.value for r in MessageRole]))
                    ) from err

                payload.append({"conversational": {"content": {"text": text}, "role": role_enum.value}})

            # Use provided timestamp or current time
            if event_timestamp is None:
                event_timestamp = datetime.utcnow()

            params = {
                "memoryId": memory_id,
                "actorId": actor_id,
                "sessionId": session_id,
                "eventTimestamp": event_timestamp,
                "payload": payload,
                "clientToken": str(uuid.uuid4()),
            }

            if branch:
                params["branch"] = branch

            response = self.gmdp_client.create_event(**params)

            event = response["event"]
            logger.info("Created event: %s", event["eventId"])

            return event

        except ClientError as e:
            logger.error("Failed to create event: %s", e)
            raise

    def save_turn(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        user_input: str,
        agent_response: str,
        event_timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """DEPRECATED: Use save_conversation() for more flexibility.

        This method will be removed in v1.0.0.
        """
        warnings.warn(
            "save_turn() is deprecated and will be removed in v1.0.0. "
            "Use save_conversation() for flexible message handling.",
            DeprecationWarning,
            stacklevel=2,
        )

        messages = [(user_input, "USER"), (agent_response, "ASSISTANT")]

        return self.create_event(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            messages=messages,
            event_timestamp=event_timestamp,
        )

    def process_turn(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        user_input: str,
        agent_response: str,
        event_timestamp: Optional[datetime] = None,
        retrieval_namespace: Optional[str] = None,
        retrieval_query: Optional[str] = None,
        top_k: int = 3,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """DEPRECATED: Use retrieve_memories() and save_conversation() separately.

        This method will be removed in v1.0.0.
        """
        warnings.warn(
            "process_turn() is deprecated and will be removed in v1.0.0. "
            "Use retrieve_memories() and save_conversation() separately, or use process_turn_with_llm().",
            DeprecationWarning,
            stacklevel=2,
        )

        retrieved_memories = []

        if retrieval_namespace:
            search_query = retrieval_query or user_input
            retrieved_memories = self.retrieve_memories(
                memory_id=memory_id, namespace=retrieval_namespace, query=search_query, top_k=top_k
            )

        event = self.save_turn(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            user_input=user_input,
            agent_response=agent_response,
            event_timestamp=event_timestamp,
        )

        return retrieved_memories, event

    def process_turn_with_llm(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        user_input: str,
        llm_callback: Callable[[str, List[Dict[str, Any]]], str],
        retrieval_namespace: Optional[str] = None,
        retrieval_query: Optional[str] = None,
        top_k: int = 3,
        event_timestamp: Optional[datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        r"""Complete conversation turn with LLM callback integration.

        This method combines memory retrieval, LLM invocation, and response storage
        in a single call using a callback pattern.

        Args:
            memory_id: Memory resource ID
            actor_id: Actor identifier (e.g., "user-123")
            session_id: Session identifier
            user_input: The user's message
            llm_callback: Function that takes (user_input, memories) and returns agent_response
                         The callback receives the user input and retrieved memories,
                         and should return the agent's response string
            retrieval_namespace: Namespace to search for memories (optional)
            retrieval_query: Custom search query (defaults to user_input)
            top_k: Number of memories to retrieve
            event_timestamp: Optional timestamp for the event

        Returns:
            Tuple of (retrieved_memories, agent_response, created_event)

        Example:
            def my_llm(user_input: str, memories: List[Dict]) -> str:
                # Format context from memories
                context = "\\n".join([m['content']['text'] for m in memories])

                # Call your LLM (Bedrock, OpenAI, etc.)
                response = bedrock.invoke_model(
                    messages=[
                        {"role": "system", "content": f"Context: {context}"},
                        {"role": "user", "content": user_input}
                    ]
                )
                return response['content']

            memories, response, event = client.process_turn_with_llm(
                memory_id="mem-xyz",
                actor_id="user-123",
                session_id="session-456",
                user_input="What did we discuss yesterday?",
                llm_callback=my_llm,
                retrieval_namespace="support/facts/{sessionId}"
            )
        """
        # Step 1: Retrieve relevant memories
        retrieved_memories = []
        if retrieval_namespace:
            search_query = retrieval_query or user_input
            retrieved_memories = self.retrieve_memories(
                memory_id=memory_id, namespace=retrieval_namespace, query=search_query, top_k=top_k
            )
            logger.info("Retrieved %d memories for LLM context", len(retrieved_memories))

        # Step 2: Invoke LLM callback
        try:
            agent_response = llm_callback(user_input, retrieved_memories)
            if not isinstance(agent_response, str):
                raise ValueError("LLM callback must return a string response")
            logger.info("LLM callback generated response")
        except Exception as e:
            logger.error("LLM callback failed: %s", e)
            raise

        # Step 3: Save the conversation turn
        event = self.create_event(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            messages=[(user_input, "USER"), (agent_response, "ASSISTANT")],
            event_timestamp=event_timestamp,
        )

        logger.info("Completed full conversation turn with LLM")
        return retrieved_memories, agent_response, event

    def list_events(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        branch_name: Optional[str] = None,
        include_parent_branches: bool = False,
        max_results: int = 100,
        include_payload: bool = True,
    ) -> List[Dict[str, Any]]:
        """List all events in a session with pagination support.

        This method provides direct access to the raw events API, allowing developers
        to retrieve all events without the turn grouping logic of get_last_k_turns.

        Args:
            memory_id: Memory resource ID
            actor_id: Actor identifier
            session_id: Session identifier
            branch_name: Optional branch name to filter events (None for all branches)
            include_parent_branches: Whether to include parent branch events (only applies with branch_name)
            max_results: Maximum number of events to return
            include_payload: Whether to include event payloads in response

        Returns:
            List of event dictionaries in chronological order

        Example:
            # Get all events
            events = client.list_events(memory_id, actor_id, session_id)

            # Get only main branch events
            main_events = client.list_events(memory_id, actor_id, session_id, branch_name="main")

            # Get events from a specific branch
            branch_events = client.list_events(memory_id, actor_id, session_id, branch_name="test-branch")
        """
        try:
            all_events = []
            next_token = None

            while len(all_events) < max_results:
                params = {
                    "memoryId": memory_id,
                    "actorId": actor_id,
                    "sessionId": session_id,
                    "maxResults": min(100, max_results - len(all_events)),
                    "includePayloads": include_payload,
                }

                if next_token:
                    params["nextToken"] = next_token

                # Add branch filter if specified (but not for "main")
                if branch_name and branch_name != "main":
                    params["filter"] = {
                        "branch": {"name": branch_name, "includeParentBranches": include_parent_branches}
                    }

                response = self.gmdp_client.list_events(**params)

                events = response.get("events", [])
                all_events.extend(events)

                next_token = response.get("nextToken")
                if not next_token or len(all_events) >= max_results:
                    break

            logger.info("Retrieved total of %d events", len(all_events))
            return all_events[:max_results]

        except ClientError as e:
            logger.error("Failed to list events: %s", e)
            raise

    def list_branches(self, memory_id: str, actor_id: str, session_id: str) -> List[Dict[str, Any]]:
        """List all branches in a session.

        This method handles pagination automatically and provides a structured view
        of all conversation branches, which would require complex pagination and
        grouping logic if done with raw boto3 calls.

        Returns:
            List of branch information including name and root event
        """
        try:
            # Get all events - need to handle pagination for complete list
            all_events = []
            next_token = None

            while True:
                params = {"memoryId": memory_id, "actorId": actor_id, "sessionId": session_id, "maxResults": 100}

                if next_token:
                    params["nextToken"] = next_token

                response = self.gmdp_client.list_events(**params)
                all_events.extend(response.get("events", []))

                next_token = response.get("nextToken")
                if not next_token:
                    break

            branches = {}
            main_branch_events = []

            for event in all_events:
                branch_info = event.get("branch")
                if branch_info:
                    branch_name = branch_info["name"]
                    if branch_name not in branches:
                        branches[branch_name] = {
                            "name": branch_name,
                            "rootEventId": branch_info.get("rootEventId"),
                            "firstEventId": event["eventId"],
                            "eventCount": 1,
                            "created": event["eventTimestamp"],
                        }
                    else:
                        branches[branch_name]["eventCount"] += 1
                else:
                    main_branch_events.append(event)

            # Build result list
            result = []

            # Only add main branch if there are actual events
            if main_branch_events:
                result.append(
                    {
                        "name": "main",
                        "rootEventId": None,
                        "firstEventId": main_branch_events[0]["eventId"],
                        "eventCount": len(main_branch_events),
                        "created": main_branch_events[0]["eventTimestamp"],
                    }
                )

            # Add other branches
            result.extend(list(branches.values()))

            logger.info("Found %d branches in session %s", len(result), session_id)
            return result

        except ClientError as e:
            logger.error("Failed to list branches: %s", e)
            raise

    def list_branch_events(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        branch_name: Optional[str] = None,
        include_parent_branches: bool = False,
        max_results: int = 100,
    ) -> List[Dict[str, Any]]:
        """List events in a specific branch.

        This method provides complex filtering and pagination that would require
        significant boilerplate code with raw boto3. It handles:
        - Automatic pagination across multiple API calls
        - Branch filtering with parent event inclusion logic
        - Main branch isolation (events without branch info)

        Args:
            memory_id: Memory resource ID
            actor_id: Actor identifier
            session_id: Session identifier
            branch_name: Branch name (None for main branch)
            include_parent_branches: Whether to include events from parent branches
            max_results: Maximum events to return

        Returns:
            List of events in the branch
        """
        try:
            params = {
                "memoryId": memory_id,
                "actorId": actor_id,
                "sessionId": session_id,
                "maxResults": min(100, max_results),
            }

            # Only add filter when we have a specific branch name
            if branch_name:
                params["filter"] = {"branch": {"name": branch_name, "includeParentBranches": include_parent_branches}}

            response = self.gmdp_client.list_events(**params)
            events = response.get("events", [])

            # Handle pagination
            next_token = response.get("nextToken")
            while next_token and len(events) < max_results:
                params["nextToken"] = next_token
                params["maxResults"] = min(100, max_results - len(events))
                response = self.gmdp_client.list_events(**params)
                events.extend(response.get("events", []))
                next_token = response.get("nextToken")

            # Filter for main branch if no branch specified
            if not branch_name:
                events = [e for e in events if not e.get("branch")]

            logger.info("Retrieved %d events from branch '%s'", len(events), branch_name or "main")
            return events

        except ClientError as e:
            logger.error("Failed to list branch events: %s", e)
            raise

    def get_conversation_tree(self, memory_id: str, actor_id: str, session_id: str) -> Dict[str, Any]:
        """Get a tree structure of the conversation with all branches.

        This method transforms a flat list of events into a hierarchical tree structure,
        providing visualization-ready data that would be complex to build from raw events.
        It handles:
        - Full pagination to get all events
        - Grouping by branches
        - Message summarization
        - Tree structure building

        Returns:
            Dictionary representing the conversation tree structure
        """
        try:
            # Get all events - need to handle pagination for complete list
            all_events = []
            next_token = None

            while True:
                params = {"memoryId": memory_id, "actorId": actor_id, "sessionId": session_id, "maxResults": 100}

                if next_token:
                    params["nextToken"] = next_token

                response = self.gmdp_client.list_events(**params)
                all_events.extend(response.get("events", []))

                next_token = response.get("nextToken")
                if not next_token:
                    break

            # Build tree structure
            tree = {"session_id": session_id, "actor_id": actor_id, "main_branch": {"events": [], "branches": {}}}

            # Group events by branch
            for event in all_events:
                event_summary = {"eventId": event["eventId"], "timestamp": event["eventTimestamp"], "messages": []}

                # Extract message summaries
                if "payload" in event:
                    for payload_item in event.get("payload", []):
                        if "conversational" in payload_item:
                            conv = payload_item["conversational"]
                            event_summary["messages"].append(
                                {"role": conv.get("role"), "text": conv.get("content", {}).get("text", "")[:50] + "..."}
                            )

                branch_info = event.get("branch")
                if branch_info:
                    branch_name = branch_info["name"]
                    root_event = branch_info.get("rootEventId")  # Use .get() to handle missing field

                    if branch_name not in tree["main_branch"]["branches"]:
                        tree["main_branch"]["branches"][branch_name] = {"root_event_id": root_event, "events": []}

                    tree["main_branch"]["branches"][branch_name]["events"].append(event_summary)
                else:
                    tree["main_branch"]["events"].append(event_summary)

            logger.info("Built conversation tree with %d branches", len(tree["main_branch"]["branches"]))
            return tree

        except ClientError as e:
            logger.error("Failed to build conversation tree: %s", e)
            raise

    def merge_branch_context(
        self, memory_id: str, actor_id: str, session_id: str, branch_name: str, include_parent: bool = True
    ) -> List[Dict[str, Any]]:
        """Get all messages from a branch for context building.

        Args:
            memory_id: Memory resource ID
            actor_id: Actor identifier
            session_id: Session identifier
            branch_name: Branch to get context from
            include_parent: Whether to include parent branch events

        Returns:
            List of all messages in chronological order
        """
        events = self.list_branch_events(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            branch_name=branch_name,
            include_parent_branches=include_parent,
            max_results=100,
        )

        messages = []
        for event in events:
            if "payload" in event:
                for payload_item in event.get("payload", []):
                    if "conversational" in payload_item:
                        conv = payload_item["conversational"]
                        messages.append(
                            {
                                "timestamp": event["eventTimestamp"],
                                "eventId": event["eventId"],
                                "branch": event.get("branch", {}).get("name", "main"),
                                "role": conv.get("role"),
                                "content": conv.get("content", {}).get("text", ""),
                            }
                        )

        # Sort by timestamp
        messages.sort(key=lambda x: x["timestamp"])

        logger.info("Retrieved %d messages from branch '%s'", len(messages), branch_name)
        return messages

    def get_last_k_turns(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        k: int = 5,
        branch_name: Optional[str] = None,
        include_branches: bool = False,
        max_results: int = 100,
    ) -> List[List[Dict[str, Any]]]:
        """Get the last K conversation turns.

        A "turn" typically consists of a user message followed by assistant response(s).
        This method groups messages into logical turns for easier processing.

        Returns:
            List of turns, where each turn is a list of message dictionaries
        """
        try:
            # Use the new list_events method
            events = self.list_events(
                memory_id=memory_id,
                actor_id=actor_id,
                session_id=session_id,
                branch_name=branch_name,
                include_parent_branches=False,
                max_results=max_results,
            )

            if not events:
                return []

            # Process events to group into turns
            turns = []
            current_turn = []

            for event in events:
                if len(turns) >= k:
                    break  # Only need last K turns
                for payload_item in event.get("payload", []):
                    if "conversational" in payload_item:
                        role = payload_item["conversational"].get("role")

                        # Start new turn on USER message
                        if role == Role.USER.value and current_turn:
                            turns.append(current_turn)
                            current_turn = []

                        current_turn.append(payload_item["conversational"])

            # Don't forget the last turn
            if current_turn:
                turns.append(current_turn)

            # Return the last k turns
            return turns[:k] if len(turns) > k else turns

        except ClientError as e:
            logger.error("Failed to get last K turns: %s", e)
            raise

    def fork_conversation(
        self,
        memory_id: str,
        actor_id: str,
        session_id: str,
        root_event_id: str,
        branch_name: str,
        new_messages: List[Tuple[str, str]],
        event_timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Fork a conversation from a specific event to create a new branch."""
        try:
            branch = {"rootEventId": root_event_id, "name": branch_name}

            event = self.create_event(
                memory_id=memory_id,
                actor_id=actor_id,
                session_id=session_id,
                messages=new_messages,
                branch=branch,
                event_timestamp=event_timestamp,
            )

            logger.info("Created branch '%s' from event %s", branch_name, root_event_id)
            return event

        except ClientError as e:
            logger.error("Failed to fork conversation: %s", e)
            raise

    def get_memory_strategies(self, memory_id: str) -> List[Dict[str, Any]]:
        """Get all strategies for a memory."""
        try:
            response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
            memory = response["memory"]

            # Handle both old and new field names in response
            strategies = memory.get("strategies", memory.get("memoryStrategies", []))

            # Normalize strategy fields
            normalized_strategies = []
            for strategy in strategies:
                # Create normalized version with both old and new field names
                normalized = strategy.copy()

                # Ensure both field name versions exist
                if "strategyId" in strategy and "memoryStrategyId" not in normalized:
                    normalized["memoryStrategyId"] = strategy["strategyId"]
                elif "memoryStrategyId" in strategy and "strategyId" not in normalized:
                    normalized["strategyId"] = strategy["memoryStrategyId"]

                if "type" in strategy and "memoryStrategyType" not in normalized:
                    normalized["memoryStrategyType"] = strategy["type"]
                elif "memoryStrategyType" in strategy and "type" not in normalized:
                    normalized["type"] = strategy["memoryStrategyType"]

                normalized_strategies.append(normalized)

            return normalized_strategies
        except ClientError as e:
            logger.error("Failed to get memory strategies: %s", e)
            raise

    def get_memory_status(self, memory_id: str) -> str:
        """Get current memory status."""
        try:
            response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
            return response["memory"]["status"]
        except ClientError as e:
            logger.error("Failed to get memory status: %s", e)
            raise

    def list_memories(self, max_results: int = 100) -> List[Dict[str, Any]]:
        """List all memories for the account."""
        try:
            # Ensure max_results doesn't exceed API limit per request
            results_per_request = min(max_results, 100)

            response = self.gmcp_client.list_memories(maxResults=results_per_request)
            memories = response.get("memories", [])

            next_token = response.get("nextToken")
            while next_token and len(memories) < max_results:
                remaining = max_results - len(memories)
                results_per_request = min(remaining, 100)

                response = self.gmcp_client.list_memories(maxResults=results_per_request, nextToken=next_token)
                memories.extend(response.get("memories", []))
                next_token = response.get("nextToken")

            # Normalize memory summaries if they contain new field names
            normalized_memories = []
            for memory in memories[:max_results]:
                normalized = memory.copy()
                # Ensure both field name versions exist
                if "id" in memory and "memoryId" not in normalized:
                    normalized["memoryId"] = memory["id"]
                elif "memoryId" in memory and "id" not in normalized:
                    normalized["id"] = memory["memoryId"]
                normalized_memories.append(normalized)

            return normalized_memories

        except ClientError as e:
            logger.error("Failed to list memories: %s", e)
            raise

    def delete_memory(self, memory_id: str) -> Dict[str, Any]:
        """Delete a memory resource."""
        try:
            response = self.gmcp_client.delete_memory(
                memoryId=memory_id, clientToken=str(uuid.uuid4())
            )  # Input uses old field name
            logger.info("Deleted memory: %s", memory_id)
            return response
        except ClientError as e:
            logger.error("Failed to delete memory: %s", e)
            raise

    def delete_memory_and_wait(self, memory_id: str, max_wait: int = 300, poll_interval: int = 10) -> Dict[str, Any]:
        """Delete a memory and wait for deletion to complete.

        This method deletes a memory and polls until it's fully deleted,
        ensuring clean resource cleanup.

        Args:
            memory_id: Memory resource ID to delete
            max_wait: Maximum seconds to wait (default: 300)
            poll_interval: Seconds between checks (default: 10)

        Returns:
            Final deletion response

        Raises:
            TimeoutError: If deletion doesn't complete within max_wait
        """
        # Initiate deletion
        response = self.delete_memory(memory_id)
        logger.info("Initiated deletion of memory %s", memory_id)

        start_time = time.time()
        while time.time() - start_time < max_wait:
            elapsed = int(time.time() - start_time)

            try:
                # Try to get the memory - if it doesn't exist, deletion is complete
                self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
                logger.debug("Memory still exists, waiting... (%d seconds elapsed)", elapsed)

            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    logger.info("Memory %s successfully deleted (took %d seconds)", memory_id, elapsed)
                    return response
                else:
                    logger.error("Error checking memory status: %s", e)
                    raise

            time.sleep(poll_interval)

        raise TimeoutError("Memory %s was not deleted within %d seconds" % (memory_id, max_wait))

    def add_semantic_strategy(
        self,
        memory_id: str,
        name: str,
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add a semantic memory strategy.

        Note: Configuration is no longer provided for built-in strategies as per API changes.
        """
        strategy: Dict = {
            StrategyType.SEMANTIC.value: {
                "name": name,
            }
        }

        if description:
            strategy[StrategyType.SEMANTIC.value]["description"] = description
        if namespaces:
            strategy[StrategyType.SEMANTIC.value]["namespaces"] = namespaces

        return self._add_strategy(memory_id, strategy)

    def add_semantic_strategy_and_wait(
        self,
        memory_id: str,
        name: str,
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Add a semantic strategy and wait for memory to return to ACTIVE state.

        This addresses the issue where adding a strategy puts the memory into
        CREATING state temporarily, preventing subsequent operations.
        """
        # Add the strategy
        self.add_semantic_strategy(memory_id, name, description, namespaces)

        # Wait for memory to return to ACTIVE
        return self._wait_for_memory_active(memory_id, max_wait, poll_interval)

    def add_summary_strategy(
        self,
        memory_id: str,
        name: str,
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add a summary memory strategy.

        Note: Configuration is no longer provided for built-in strategies as per API changes.
        """
        strategy: Dict = {
            StrategyType.SUMMARY.value: {
                "name": name,
            }
        }

        if description:
            strategy[StrategyType.SUMMARY.value]["description"] = description
        if namespaces:
            strategy[StrategyType.SUMMARY.value]["namespaces"] = namespaces

        return self._add_strategy(memory_id, strategy)

    def add_summary_strategy_and_wait(
        self,
        memory_id: str,
        name: str,
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Add a summary strategy and wait for memory to return to ACTIVE state."""
        self.add_summary_strategy(memory_id, name, description, namespaces)
        return self._wait_for_memory_active(memory_id, max_wait, poll_interval)

    def add_user_preference_strategy(
        self,
        memory_id: str,
        name: str,
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add a user preference memory strategy.

        Note: Configuration is no longer provided for built-in strategies as per API changes.
        """
        strategy: Dict = {
            StrategyType.USER_PREFERENCE.value: {
                "name": name,
            }
        }

        if description:
            strategy[StrategyType.USER_PREFERENCE.value]["description"] = description
        if namespaces:
            strategy[StrategyType.USER_PREFERENCE.value]["namespaces"] = namespaces

        return self._add_strategy(memory_id, strategy)

    def add_user_preference_strategy_and_wait(
        self,
        memory_id: str,
        name: str,
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Add a user preference strategy and wait for memory to return to ACTIVE state."""
        self.add_user_preference_strategy(memory_id, name, description, namespaces)
        return self._wait_for_memory_active(memory_id, max_wait, poll_interval)

    def add_custom_semantic_strategy(
        self,
        memory_id: str,
        name: str,
        extraction_config: Dict[str, Any],
        consolidation_config: Dict[str, Any],
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Add a custom semantic strategy with prompts.

        Args:
            memory_id: Memory resource ID
            name: Strategy name
            extraction_config: Extraction configuration with prompt and model:
                {"prompt": "...", "modelId": "..."}
            consolidation_config: Consolidation configuration with prompt and model:
                {"prompt": "...", "modelId": "..."}
            description: Optional description
            namespaces: Optional namespaces list
        """
        strategy = {
            StrategyType.CUSTOM.value: {
                "name": name,
                "configuration": {
                    "semanticOverride": {
                        "extraction": {
                            "appendToPrompt": extraction_config["prompt"],
                            "modelId": extraction_config["modelId"],
                        },
                        "consolidation": {
                            "appendToPrompt": consolidation_config["prompt"],
                            "modelId": consolidation_config["modelId"],
                        },
                    }
                },
            }
        }

        if description:
            strategy[StrategyType.CUSTOM.value]["description"] = description
        if namespaces:
            strategy[StrategyType.CUSTOM.value]["namespaces"] = namespaces

        return self._add_strategy(memory_id, strategy)

    def add_custom_semantic_strategy_and_wait(
        self,
        memory_id: str,
        name: str,
        extraction_config: Dict[str, Any],
        consolidation_config: Dict[str, Any],
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Add a custom semantic strategy and wait for memory to return to ACTIVE state."""
        self.add_custom_semantic_strategy(
            memory_id, name, extraction_config, consolidation_config, description, namespaces
        )
        return self._wait_for_memory_active(memory_id, max_wait, poll_interval)

    def modify_strategy(
        self,
        memory_id: str,
        strategy_id: str,
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
        configuration: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Modify a strategy with full control over configuration."""
        modify_config: Dict = {"memoryStrategyId": strategy_id}  # Using old field name for input

        if description is not None:
            modify_config["description"] = description
        if namespaces is not None:
            modify_config["namespaces"] = namespaces
        if configuration is not None:
            modify_config["configuration"] = configuration

        return self.update_memory_strategies(memory_id=memory_id, modify_strategies=[modify_config])

    def delete_strategy(self, memory_id: str, strategy_id: str) -> Dict[str, Any]:
        """Delete a strategy from a memory."""
        return self.update_memory_strategies(memory_id=memory_id, delete_strategy_ids=[strategy_id])

    def update_memory_strategies(
        self,
        memory_id: str,
        add_strategies: Optional[List[Dict[str, Any]]] = None,
        modify_strategies: Optional[List[Dict[str, Any]]] = None,
        delete_strategy_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Update memory strategies - add, modify, or delete."""
        try:
            memory_strategies = {}

            if add_strategies:
                processed_add = self._add_default_namespaces(add_strategies)
                memory_strategies["addMemoryStrategies"] = processed_add  # Using old field name for input

            if modify_strategies:
                current_strategies = self.get_memory_strategies(memory_id)
                strategy_map = {s["memoryStrategyId"]: s for s in current_strategies}  # Using normalized field

                modify_list = []
                for strategy in modify_strategies:
                    if "memoryStrategyId" not in strategy:  # Using old field name
                        raise ValueError("Each modify strategy must include memoryStrategyId")

                    strategy_id = strategy["memoryStrategyId"]  # Using old field name
                    strategy_info = strategy_map.get(strategy_id)

                    if not strategy_info:
                        raise ValueError("Strategy %s not found in memory %s" % (strategy_id, memory_id))

                    strategy_type = strategy_info["memoryStrategyType"]  # Using normalized field
                    override_type = strategy_info.get("configuration", {}).get("type")

                    strategy_copy = copy.deepcopy(strategy)

                    if "configuration" in strategy_copy:
                        wrapped_config = self._wrap_configuration(
                            strategy_copy["configuration"], strategy_type, override_type
                        )
                        strategy_copy["configuration"] = wrapped_config

                    modify_list.append(strategy_copy)

                memory_strategies["modifyMemoryStrategies"] = modify_list  # Using old field name for input

            if delete_strategy_ids:
                delete_list = [{"memoryStrategyId": sid} for sid in delete_strategy_ids]  # Using old field name
                memory_strategies["deleteMemoryStrategies"] = delete_list  # Using old field name for input

            if not memory_strategies:
                raise ValueError("No strategy operations provided")

            response = self.gmcp_client.update_memory(
                memoryId=memory_id,
                memoryStrategies=memory_strategies,
                clientToken=str(uuid.uuid4()),  # Using old field names for input
            )

            logger.info("Updated memory strategies for: %s", memory_id)
            memory = self._normalize_memory_response(response["memory"])
            return memory

        except ClientError as e:
            logger.error("Failed to update memory strategies: %s", e)
            raise

    def update_memory_strategies_and_wait(
        self,
        memory_id: str,
        add_strategies: Optional[List[Dict[str, Any]]] = None,
        modify_strategies: Optional[List[Dict[str, Any]]] = None,
        delete_strategy_ids: Optional[List[str]] = None,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Update memory strategies and wait for memory to return to ACTIVE state.

        This method handles the temporary CREATING state that occurs when
        updating strategies, preventing subsequent update errors.
        """
        # Update strategies
        self.update_memory_strategies(memory_id, add_strategies, modify_strategies, delete_strategy_ids)

        # Wait for memory to return to ACTIVE
        return self._wait_for_memory_active(memory_id, max_wait, poll_interval)

    def wait_for_memories(
        self, memory_id: str, namespace: str, test_query: str = "test", max_wait: int = 180, poll_interval: int = 15
    ) -> bool:
        """Wait for memory extraction to complete by polling.

        IMPORTANT LIMITATIONS:
        1. This method only works reliably on empty namespaces. If there are already
           existing memories in the namespace, this method may return True immediately
           even if new extractions haven't completed.
        2. Wildcards (*) are NOT supported in namespaces. You must provide the exact
           namespace path with all variables resolved (e.g., "support/facts/session-123"
           not "support/facts/*").

        For subsequent extractions in populated namespaces, use a fixed wait time:
            time.sleep(150)  # Wait 2.5 minutes for extraction

        Args:
            memory_id: Memory resource ID
            namespace: Exact namespace to check (no wildcards)
            test_query: Query to test with (default: "test")
            max_wait: Maximum seconds to wait (default: 180)
            poll_interval: Seconds between checks (default: 15)

        Returns:
            True if memories found, False if timeout

        Note:
            This method will be deprecated in future versions once the API
            provides extraction status or timestamps.
        """
        if "*" in namespace:
            logger.error("Wildcards are not supported in namespaces. Please provide exact namespace.")
            return False

        logger.warning(
            "wait_for_memories() only works reliably on empty namespaces. "
            "For populated namespaces, consider using a fixed wait time instead."
        )

        logger.info("Waiting for memory extraction in namespace: %s", namespace)
        start_time = time.time()
        service_errors = 0

        while time.time() - start_time < max_wait:
            elapsed = int(time.time() - start_time)

            try:
                memories = self.retrieve_memories(memory_id=memory_id, namespace=namespace, query=test_query, top_k=1)

                if memories:
                    logger.info("Memory extraction complete after %d seconds", elapsed)
                    return True

                # Reset service error count on successful call
                service_errors = 0

            except Exception as e:
                if "ServiceException" in str(e):
                    service_errors += 1
                    if service_errors >= 3:
                        logger.warning("Multiple service errors - the service may be experiencing issues")
                logger.debug("Retrieval attempt failed: %s", e)

            if time.time() - start_time < max_wait:
                time.sleep(poll_interval)

        logger.warning("No memories found after %d seconds", max_wait)
        if service_errors > 0:
            logger.info("Note: Encountered %d service errors during polling", service_errors)
        return False

    def add_strategy(self, memory_id: str, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Add a strategy to a memory (without waiting).

        WARNING: After adding a strategy, the memory enters CREATING state temporarily.
        Use add_*_strategy_and_wait() methods instead to avoid errors.

        Args:
            memory_id: Memory resource ID
            strategy: Strategy configuration dictionary

        Returns:
            Updated memory response
        """
        warnings.warn(
            "add_strategy() may leave memory in CREATING state. "
            "Use add_*_strategy_and_wait() methods to avoid subsequent errors.",
            UserWarning,
            stacklevel=2,
        )
        return self._add_strategy(memory_id, strategy)

    # Private methods

    def _normalize_memory_response(self, memory: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize memory response to include both old and new field names.

        The API returns new field names but SDK users might expect old ones.
        This ensures compatibility by providing both.
        """
        # Ensure both versions of memory ID exist
        if "id" in memory and "memoryId" not in memory:
            memory["memoryId"] = memory["id"]
        elif "memoryId" in memory and "id" not in memory:
            memory["id"] = memory["memoryId"]

        # Ensure both versions of strategies exist
        if "strategies" in memory and "memoryStrategies" not in memory:
            memory["memoryStrategies"] = memory["strategies"]
        elif "memoryStrategies" in memory and "strategies" not in memory:
            memory["strategies"] = memory["memoryStrategies"]

        # Normalize strategies within memory
        if "strategies" in memory:
            normalized_strategies = []
            for strategy in memory["strategies"]:
                normalized = strategy.copy()

                # Ensure both field name versions exist for strategies
                if "strategyId" in strategy and "memoryStrategyId" not in normalized:
                    normalized["memoryStrategyId"] = strategy["strategyId"]
                elif "memoryStrategyId" in strategy and "strategyId" not in normalized:
                    normalized["strategyId"] = strategy["memoryStrategyId"]

                if "type" in strategy and "memoryStrategyType" not in normalized:
                    normalized["memoryStrategyType"] = strategy["type"]
                elif "memoryStrategyType" in strategy and "type" not in normalized:
                    normalized["type"] = strategy["memoryStrategyType"]

                normalized_strategies.append(normalized)

            memory["strategies"] = normalized_strategies
            memory["memoryStrategies"] = normalized_strategies

        return memory

    def _add_strategy(self, memory_id: str, strategy: Dict[str, Any]) -> Dict[str, Any]:
        """Internal method to add a single strategy."""
        return self.update_memory_strategies(memory_id=memory_id, add_strategies=[strategy])

    def _wait_for_memory_active(self, memory_id: str, max_wait: int, poll_interval: int) -> Dict[str, Any]:
        """Wait for memory to return to ACTIVE state after strategy update."""
        logger.info("Waiting for memory %s to return to ACTIVE state...", memory_id)

        start_time = time.time()
        while time.time() - start_time < max_wait:
            elapsed = int(time.time() - start_time)

            try:
                status = self.get_memory_status(memory_id)

                if status == MemoryStatus.ACTIVE.value:
                    logger.info("Memory %s is ACTIVE again (took %d seconds)", memory_id, elapsed)
                    response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
                    memory = self._normalize_memory_response(response["memory"])
                    return memory
                elif status == MemoryStatus.FAILED.value:
                    response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
                    failure_reason = response["memory"].get("failureReason", "Unknown")
                    raise RuntimeError("Memory update failed: %s" % failure_reason)
                else:
                    logger.debug("Memory status: %s (%d seconds elapsed)", status, elapsed)

            except ClientError as e:
                logger.error("Error checking memory status: %s", e)
                raise

            time.sleep(poll_interval)

        raise TimeoutError("Memory %s did not return to ACTIVE state within %d seconds" % (memory_id, max_wait))

    def _add_default_namespaces(self, strategies: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add default namespaces to strategies that don't have them."""
        processed = []

        for strategy in strategies:
            strategy_copy = copy.deepcopy(strategy)

            strategy_type_key = list(strategy.keys())[0]
            strategy_config = strategy_copy[strategy_type_key]

            if "namespaces" not in strategy_config:
                strategy_type = StrategyType(strategy_type_key)
                strategy_config["namespaces"] = DEFAULT_NAMESPACES.get(strategy_type, ["custom/{actorId}/{sessionId}"])

            self._validate_strategy_config(strategy_copy, strategy_type_key)

            processed.append(strategy_copy)

        return processed

    def _validate_namespace(self, namespace: str) -> bool:
        """Validate namespace format - basic check only."""
        # Only check for template variables in namespace definition
        # Note: Using memoryStrategyId (old name) as it's still used in input parameters
        if "{" in namespace and not (
            "{actorId}" in namespace or "{sessionId}" in namespace or "{memoryStrategyId}" in namespace
        ):
            logger.warning("Namespace with templates should contain valid variables: %s", namespace)

        return True

    def _validate_strategy_config(self, strategy: Dict[str, Any], strategy_type: str) -> None:
        """Validate strategy configuration parameters."""
        strategy_config = strategy[strategy_type]

        namespaces = strategy_config.get("namespaces", [])
        for namespace in namespaces:
            self._validate_namespace(namespace)

    def _wrap_configuration(
        self, config: Dict[str, Any], strategy_type: str, override_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Wrap configuration based on strategy type."""
        wrapped_config = {}

        if "extraction" in config:
            extraction = config["extraction"]

            if any(key in extraction for key in ["triggerEveryNMessages", "historicalContextWindowSize"]):
                strategy_type_enum = MemoryStrategyTypeEnum(strategy_type)

                if strategy_type == "SEMANTIC":
                    wrapped_config["extraction"] = {EXTRACTION_WRAPPER_KEYS[strategy_type_enum]: extraction}
                elif strategy_type == "USER_PREFERENCE":
                    wrapped_config["extraction"] = {EXTRACTION_WRAPPER_KEYS[strategy_type_enum]: extraction}
                elif strategy_type == "CUSTOM" and override_type:
                    override_enum = OverrideType(override_type)
                    if override_type in ["SEMANTIC_OVERRIDE", "USER_PREFERENCE_OVERRIDE"]:
                        wrapped_config["extraction"] = {
                            "customExtractionConfiguration": {CUSTOM_EXTRACTION_WRAPPER_KEYS[override_enum]: extraction}
                        }
            else:
                wrapped_config["extraction"] = extraction

        if "consolidation" in config:
            consolidation = config["consolidation"]

            raw_keys = ["triggerEveryNMessages", "appendToPrompt", "modelId"]
            if any(key in consolidation for key in raw_keys):
                if strategy_type == "SUMMARIZATION":
                    if "triggerEveryNMessages" in consolidation:
                        wrapped_config["consolidation"] = {
                            "summaryConsolidationConfiguration": {
                                "triggerEveryNMessages": consolidation["triggerEveryNMessages"]
                            }
                        }
                elif strategy_type == "CUSTOM" and override_type:
                    override_enum = OverrideType(override_type)
                    if override_enum in CUSTOM_CONSOLIDATION_WRAPPER_KEYS:
                        wrapped_config["consolidation"] = {
                            "customConsolidationConfiguration": {
                                CUSTOM_CONSOLIDATION_WRAPPER_KEYS[override_enum]: consolidation
                            }
                        }
            else:
                wrapped_config["consolidation"] = consolidation

        return wrapped_config
```

#### `__getattr__(name)`

Dynamically forward method calls to the appropriate boto3 client.

This method enables access to all boto3 client methods without explicitly defining them. Methods are looked up in the following order:

1. gmdp_client (bedrock-agentcore) - for data plane operations
1. gmcp_client (bedrock-agentcore-control) - for control plane operations

Parameters:

| Name   | Type  | Description                    | Default    |
| ------ | ----- | ------------------------------ | ---------- |
| `name` | `str` | The method name being accessed | *required* |

Returns:

| Type | Description                                         |
| ---- | --------------------------------------------------- |
|      | A callable method from the appropriate boto3 client |

Raises:

| Type             | Description                                  |
| ---------------- | -------------------------------------------- |
| `AttributeError` | If the method doesn't exist on either client |

Example

##### Access any boto3 method directly

client = MemoryClient()

##### These calls are forwarded to the appropriate boto3 client

response = client.list_memory_records(memoryId="mem-123", namespace="test") metadata = client.get_memory_metadata(memoryId="mem-123")

Source code in `bedrock_agentcore/memory/client.py`

```
def __getattr__(self, name: str):
    """Dynamically forward method calls to the appropriate boto3 client.

    This method enables access to all boto3 client methods without explicitly
    defining them. Methods are looked up in the following order:
    1. gmdp_client (bedrock-agentcore) - for data plane operations
    2. gmcp_client (bedrock-agentcore-control) - for control plane operations

    Args:
        name: The method name being accessed

    Returns:
        A callable method from the appropriate boto3 client

    Raises:
        AttributeError: If the method doesn't exist on either client

    Example:
        # Access any boto3 method directly
        client = MemoryClient()

        # These calls are forwarded to the appropriate boto3 client
        response = client.list_memory_records(memoryId="mem-123", namespace="test")
        metadata = client.get_memory_metadata(memoryId="mem-123")
    """
    if name in self._ALLOWED_GMDP_METHODS and hasattr(self.gmdp_client, name):
        method = getattr(self.gmdp_client, name)
        logger.debug("Forwarding method '%s' to gmdp_client", name)
        return method

    if name in self._ALLOWED_GMCP_METHODS and hasattr(self.gmcp_client, name):
        method = getattr(self.gmcp_client, name)
        logger.debug("Forwarding method '%s' to gmcp_client", name)
        return method

    # Method not found on either client
    raise AttributeError(
        f"'{self.__class__.__name__}' object has no attribute '{name}'. "
        f"Method not found on gmdp_client or gmcp_client. "
        f"Available methods can be found in the boto3 documentation for "
        f"'bedrock-agentcore' and 'bedrock-agentcore-control' services."
    )
```

#### `__init__(region_name=None)`

Initialize the Memory client.

Source code in `bedrock_agentcore/memory/client.py`

```
def __init__(self, region_name: Optional[str] = None):
    """Initialize the Memory client."""
    self.region_name = region_name or boto3.Session().region_name or "us-west-2"

    self.gmcp_client = boto3.client("bedrock-agentcore-control", region_name=self.region_name)
    self.gmdp_client = boto3.client("bedrock-agentcore", region_name=self.region_name)

    logger.info(
        "Initialized MemoryClient for control plane: %s, data plane: %s",
        self.gmcp_client.meta.region_name,
        self.gmdp_client.meta.region_name,
    )
```

#### `add_custom_semantic_strategy(memory_id, name, extraction_config, consolidation_config, description=None, namespaces=None)`

Add a custom semantic strategy with prompts.

Parameters:

| Name                   | Type                  | Description                                        | Default    |
| ---------------------- | --------------------- | -------------------------------------------------- | ---------- |
| `memory_id`            | `str`                 | Memory resource ID                                 | *required* |
| `name`                 | `str`                 | Strategy name                                      | *required* |
| `extraction_config`    | `Dict[str, Any]`      | Extraction configuration with prompt and model:    | *required* |
| `consolidation_config` | `Dict[str, Any]`      | Consolidation configuration with prompt and model: | *required* |
| `description`          | `Optional[str]`       | Optional description                               | `None`     |
| `namespaces`           | `Optional[List[str]]` | Optional namespaces list                           | `None`     |

Source code in `bedrock_agentcore/memory/client.py`

```
def add_custom_semantic_strategy(
    self,
    memory_id: str,
    name: str,
    extraction_config: Dict[str, Any],
    consolidation_config: Dict[str, Any],
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Add a custom semantic strategy with prompts.

    Args:
        memory_id: Memory resource ID
        name: Strategy name
        extraction_config: Extraction configuration with prompt and model:
            {"prompt": "...", "modelId": "..."}
        consolidation_config: Consolidation configuration with prompt and model:
            {"prompt": "...", "modelId": "..."}
        description: Optional description
        namespaces: Optional namespaces list
    """
    strategy = {
        StrategyType.CUSTOM.value: {
            "name": name,
            "configuration": {
                "semanticOverride": {
                    "extraction": {
                        "appendToPrompt": extraction_config["prompt"],
                        "modelId": extraction_config["modelId"],
                    },
                    "consolidation": {
                        "appendToPrompt": consolidation_config["prompt"],
                        "modelId": consolidation_config["modelId"],
                    },
                }
            },
        }
    }

    if description:
        strategy[StrategyType.CUSTOM.value]["description"] = description
    if namespaces:
        strategy[StrategyType.CUSTOM.value]["namespaces"] = namespaces

    return self._add_strategy(memory_id, strategy)
```

#### `add_custom_semantic_strategy_and_wait(memory_id, name, extraction_config, consolidation_config, description=None, namespaces=None, max_wait=300, poll_interval=10)`

Add a custom semantic strategy and wait for memory to return to ACTIVE state.

Source code in `bedrock_agentcore/memory/client.py`

```
def add_custom_semantic_strategy_and_wait(
    self,
    memory_id: str,
    name: str,
    extraction_config: Dict[str, Any],
    consolidation_config: Dict[str, Any],
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Add a custom semantic strategy and wait for memory to return to ACTIVE state."""
    self.add_custom_semantic_strategy(
        memory_id, name, extraction_config, consolidation_config, description, namespaces
    )
    return self._wait_for_memory_active(memory_id, max_wait, poll_interval)
```

#### `add_semantic_strategy(memory_id, name, description=None, namespaces=None)`

Add a semantic memory strategy.

Note: Configuration is no longer provided for built-in strategies as per API changes.

Source code in `bedrock_agentcore/memory/client.py`

```
def add_semantic_strategy(
    self,
    memory_id: str,
    name: str,
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Add a semantic memory strategy.

    Note: Configuration is no longer provided for built-in strategies as per API changes.
    """
    strategy: Dict = {
        StrategyType.SEMANTIC.value: {
            "name": name,
        }
    }

    if description:
        strategy[StrategyType.SEMANTIC.value]["description"] = description
    if namespaces:
        strategy[StrategyType.SEMANTIC.value]["namespaces"] = namespaces

    return self._add_strategy(memory_id, strategy)
```

#### `add_semantic_strategy_and_wait(memory_id, name, description=None, namespaces=None, max_wait=300, poll_interval=10)`

Add a semantic strategy and wait for memory to return to ACTIVE state.

This addresses the issue where adding a strategy puts the memory into CREATING state temporarily, preventing subsequent operations.

Source code in `bedrock_agentcore/memory/client.py`

```
def add_semantic_strategy_and_wait(
    self,
    memory_id: str,
    name: str,
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Add a semantic strategy and wait for memory to return to ACTIVE state.

    This addresses the issue where adding a strategy puts the memory into
    CREATING state temporarily, preventing subsequent operations.
    """
    # Add the strategy
    self.add_semantic_strategy(memory_id, name, description, namespaces)

    # Wait for memory to return to ACTIVE
    return self._wait_for_memory_active(memory_id, max_wait, poll_interval)
```

#### `add_strategy(memory_id, strategy)`

Add a strategy to a memory (without waiting).

WARNING: After adding a strategy, the memory enters CREATING state temporarily. Use add\_\*\_strategy_and_wait() methods instead to avoid errors.

Parameters:

| Name        | Type             | Description                       | Default    |
| ----------- | ---------------- | --------------------------------- | ---------- |
| `memory_id` | `str`            | Memory resource ID                | *required* |
| `strategy`  | `Dict[str, Any]` | Strategy configuration dictionary | *required* |

Returns:

| Type             | Description             |
| ---------------- | ----------------------- |
| `Dict[str, Any]` | Updated memory response |

Source code in `bedrock_agentcore/memory/client.py`

```
def add_strategy(self, memory_id: str, strategy: Dict[str, Any]) -> Dict[str, Any]:
    """Add a strategy to a memory (without waiting).

    WARNING: After adding a strategy, the memory enters CREATING state temporarily.
    Use add_*_strategy_and_wait() methods instead to avoid errors.

    Args:
        memory_id: Memory resource ID
        strategy: Strategy configuration dictionary

    Returns:
        Updated memory response
    """
    warnings.warn(
        "add_strategy() may leave memory in CREATING state. "
        "Use add_*_strategy_and_wait() methods to avoid subsequent errors.",
        UserWarning,
        stacklevel=2,
    )
    return self._add_strategy(memory_id, strategy)
```

#### `add_summary_strategy(memory_id, name, description=None, namespaces=None)`

Add a summary memory strategy.

Note: Configuration is no longer provided for built-in strategies as per API changes.

Source code in `bedrock_agentcore/memory/client.py`

```
def add_summary_strategy(
    self,
    memory_id: str,
    name: str,
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Add a summary memory strategy.

    Note: Configuration is no longer provided for built-in strategies as per API changes.
    """
    strategy: Dict = {
        StrategyType.SUMMARY.value: {
            "name": name,
        }
    }

    if description:
        strategy[StrategyType.SUMMARY.value]["description"] = description
    if namespaces:
        strategy[StrategyType.SUMMARY.value]["namespaces"] = namespaces

    return self._add_strategy(memory_id, strategy)
```

#### `add_summary_strategy_and_wait(memory_id, name, description=None, namespaces=None, max_wait=300, poll_interval=10)`

Add a summary strategy and wait for memory to return to ACTIVE state.

Source code in `bedrock_agentcore/memory/client.py`

```
def add_summary_strategy_and_wait(
    self,
    memory_id: str,
    name: str,
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Add a summary strategy and wait for memory to return to ACTIVE state."""
    self.add_summary_strategy(memory_id, name, description, namespaces)
    return self._wait_for_memory_active(memory_id, max_wait, poll_interval)
```

#### `add_user_preference_strategy(memory_id, name, description=None, namespaces=None)`

Add a user preference memory strategy.

Note: Configuration is no longer provided for built-in strategies as per API changes.

Source code in `bedrock_agentcore/memory/client.py`

```
def add_user_preference_strategy(
    self,
    memory_id: str,
    name: str,
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Add a user preference memory strategy.

    Note: Configuration is no longer provided for built-in strategies as per API changes.
    """
    strategy: Dict = {
        StrategyType.USER_PREFERENCE.value: {
            "name": name,
        }
    }

    if description:
        strategy[StrategyType.USER_PREFERENCE.value]["description"] = description
    if namespaces:
        strategy[StrategyType.USER_PREFERENCE.value]["namespaces"] = namespaces

    return self._add_strategy(memory_id, strategy)
```

#### `add_user_preference_strategy_and_wait(memory_id, name, description=None, namespaces=None, max_wait=300, poll_interval=10)`

Add a user preference strategy and wait for memory to return to ACTIVE state.

Source code in `bedrock_agentcore/memory/client.py`

```
def add_user_preference_strategy_and_wait(
    self,
    memory_id: str,
    name: str,
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Add a user preference strategy and wait for memory to return to ACTIVE state."""
    self.add_user_preference_strategy(memory_id, name, description, namespaces)
    return self._wait_for_memory_active(memory_id, max_wait, poll_interval)
```

#### `create_blob_event(memory_id, actor_id, session_id, blob_data, event_timestamp=None, branch=None)`

Save a blob event to AgentCore Memory.

Parameters:

| Name              | Type                       | Description                        | Default    |
| ----------------- | -------------------------- | ---------------------------------- | ---------- |
| `memory_id`       | `str`                      | Memory resource ID                 | *required* |
| `actor_id`        | `str`                      | Actor identifier                   | *required* |
| `session_id`      | `str`                      | Session identifier                 | *required* |
| `blob_data`       | `Any`                      | Binary or structured data to store | *required* |
| `event_timestamp` | `Optional[datetime]`       | Optional timestamp for the event   | `None`     |
| `branch`          | `Optional[Dict[str, str]]` | Optional branch info               | `None`     |

Returns:

| Type             | Description   |
| ---------------- | ------------- |
| `Dict[str, Any]` | Created event |

Example

##### Store binary data

event = client.create_blob_event( memory_id="mem-xyz", actor_id="user-123", session_id="session-456", blob_data={"file_content": "base64_encoded_data", "metadata": {"type": "image"}} )

Source code in `bedrock_agentcore/memory/client.py`

```
def create_blob_event(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    blob_data: Any,
    event_timestamp: Optional[datetime] = None,
    branch: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Save a blob event to AgentCore Memory.

    Args:
        memory_id: Memory resource ID
        actor_id: Actor identifier
        session_id: Session identifier
        blob_data: Binary or structured data to store
        event_timestamp: Optional timestamp for the event
        branch: Optional branch info

    Returns:
        Created event

    Example:
        # Store binary data
        event = client.create_blob_event(
            memory_id="mem-xyz",
            actor_id="user-123",
            session_id="session-456",
            blob_data={"file_content": "base64_encoded_data", "metadata": {"type": "image"}}
        )
    """
    try:
        payload = [{"blob": blob_data}]

        if event_timestamp is None:
            event_timestamp = datetime.utcnow()

        params = {
            "memoryId": memory_id,
            "actorId": actor_id,
            "sessionId": session_id,
            "eventTimestamp": event_timestamp,
            "payload": payload,
        }

        if branch:
            params["branch"] = branch

        response = self.gmdp_client.create_event(**params)

        event = response["event"]
        logger.info("Created blob event: %s", event["eventId"])

        return event

    except ClientError as e:
        logger.error("Failed to create blob event: %s", e)
        raise
```

#### `create_event(memory_id, actor_id, session_id, messages, event_timestamp=None, branch=None)`

Save an event of an agent interaction or conversation with a user.

This is the basis of short-term memory. If you configured your Memory resource to have MemoryStrategies, then events that are saved in short-term memory via create_event will be used to extract long-term memory records.

Parameters:

| Name              | Type                       | Description                                                                                                                                                                                                                                  | Default    |
| ----------------- | -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `memory_id`       | `str`                      | Memory resource ID                                                                                                                                                                                                                           | *required* |
| `actor_id`        | `str`                      | Actor identifier (could be id of your user or an agent)                                                                                                                                                                                      | *required* |
| `session_id`      | `str`                      | Session identifier (meant to logically group a series of events)                                                                                                                                                                             | *required* |
| `messages`        | `List[Tuple[str, str]]`    | List of (text, role) tuples. Role can be USER, ASSISTANT, TOOL, etc.                                                                                                                                                                         | *required* |
| `event_timestamp` | `Optional[datetime]`       | timestamp for the entire event (not per message)                                                                                                                                                                                             | `None`     |
| `branch`          | `Optional[Dict[str, str]]` | Optional branch info. For new branches: {"rootEventId": "...", "name": "..."} For continuing existing branch: {"name": "..."} or {"name": "...", "rootEventId": "..."} A branch is used when you want to have a different history of events. | `None`     |

Returns:

| Type             | Description   |
| ---------------- | ------------- |
| `Dict[str, Any]` | Created event |

Example

event = client.create_event( memory_id=memory.get("id"), actor_id="weatherWorrier", session_id="WeatherSession", messages=[ ("What's the weather?", "USER"), ("Today is sunny", "ASSISTANT") ] ) root_event_id = event.get("eventId") print(event)

##### Continue the conversation

event = client.create_event( memory_id=memory.get("id"), actor_id="weatherWorrier", session_id="WeatherSession", messages=[ ("How about the weather tomorrow", "USER"), ("Tomorrow is cold!", "ASSISTANT") ] ) print(event)

##### branch the conversation so that the previous message is not part of the history

##### (suppose you did not mean to ask about the weather tomorrow and want to undo

##### that, and replace with a new message)

event = client.create_event( memory_id=memory.get("id"), actor_id="weatherWorrier", session_id="WeatherSession", branch={"name": "differentWeatherQuestion", "rootEventId": root_event_id}, messages=[ ("How about the weather a year from now", "USER"), ("I can't predict that far into the future!", "ASSISTANT") ] ) print(event)

Source code in `bedrock_agentcore/memory/client.py`

```
def create_event(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    messages: List[Tuple[str, str]],
    event_timestamp: Optional[datetime] = None,
    branch: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Save an event of an agent interaction or conversation with a user.

    This is the basis of short-term memory. If you configured your Memory resource
    to have MemoryStrategies, then events that are saved in short-term memory via
    create_event will be used to extract long-term memory records.

    Args:
        memory_id: Memory resource ID
        actor_id: Actor identifier (could be id of your user or an agent)
        session_id: Session identifier (meant to logically group a series of events)
        messages: List of (text, role) tuples. Role can be USER, ASSISTANT, TOOL, etc.
        event_timestamp: timestamp for the entire event (not per message)
        branch: Optional branch info. For new branches: {"rootEventId": "...", "name": "..."}
               For continuing existing branch: {"name": "..."} or {"name": "...", "rootEventId": "..."}
               A branch is used when you want to have a different history of events.

    Returns:
        Created event

    Example:
        event = client.create_event(
            memory_id=memory.get("id"),
            actor_id="weatherWorrier",
            session_id="WeatherSession",
            messages=[
                ("What's the weather?", "USER"),
                ("Today is sunny", "ASSISTANT")
            ]
        )
        root_event_id = event.get("eventId")
        print(event)

        # Continue the conversation
        event = client.create_event(
            memory_id=memory.get("id"),
            actor_id="weatherWorrier",
            session_id="WeatherSession",
            messages=[
                ("How about the weather tomorrow", "USER"),
                ("Tomorrow is cold!", "ASSISTANT")
            ]
        )
        print(event)

        # branch the conversation so that the previous message is not part of the history
        # (suppose you did not mean to ask about the weather tomorrow and want to undo
        # that, and replace with a new message)
        event = client.create_event(
            memory_id=memory.get("id"),
            actor_id="weatherWorrier",
            session_id="WeatherSession",
            branch={"name": "differentWeatherQuestion", "rootEventId": root_event_id},
            messages=[
                ("How about the weather a year from now", "USER"),
                ("I can't predict that far into the future!", "ASSISTANT")
            ]
        )
        print(event)
    """
    try:
        if not messages:
            raise ValueError("At least one message is required")

        payload = []
        for msg in messages:
            if len(msg) != 2:
                raise ValueError("Each message must be (text, role)")

            text, role = msg

            try:
                role_enum = MessageRole(role.upper())
            except ValueError as err:
                raise ValueError(
                    "Invalid role '%s'. Must be one of: %s" % (role, ", ".join([r.value for r in MessageRole]))
                ) from err

            payload.append({"conversational": {"content": {"text": text}, "role": role_enum.value}})

        # Use provided timestamp or current time
        if event_timestamp is None:
            event_timestamp = datetime.utcnow()

        params = {
            "memoryId": memory_id,
            "actorId": actor_id,
            "sessionId": session_id,
            "eventTimestamp": event_timestamp,
            "payload": payload,
        }

        if branch:
            params["branch"] = branch

        response = self.gmdp_client.create_event(**params)

        event = response["event"]
        logger.info("Created event: %s", event["eventId"])

        return event

    except ClientError as e:
        logger.error("Failed to create event: %s", e)
        raise
```

#### `create_memory(name, strategies=None, description=None, event_expiry_days=90, memory_execution_role_arn=None)`

Create a memory with simplified configuration.

Source code in `bedrock_agentcore/memory/client.py`

```
def create_memory(
    self,
    name: str,
    strategies: Optional[List[Dict[str, Any]]] = None,
    description: Optional[str] = None,
    event_expiry_days: int = 90,
    memory_execution_role_arn: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a memory with simplified configuration."""
    if strategies is None:
        strategies = []

    try:
        processed_strategies = self._add_default_namespaces(strategies)

        params = {
            "name": name,
            "eventExpiryDuration": event_expiry_days,
            "memoryStrategies": processed_strategies,  # Using old field name for input
            "clientToken": str(uuid.uuid4()),
        }

        if description is not None:
            params["description"] = description

        if memory_execution_role_arn is not None:
            params["memoryExecutionRoleArn"] = memory_execution_role_arn

        response = self.gmcp_client.create_memory(**params)

        memory = response["memory"]
        # Normalize response to handle new field names
        memory = self._normalize_memory_response(memory)

        logger.info("Created memory: %s", memory["memoryId"])
        return memory

    except ClientError as e:
        logger.error("Failed to create memory: %s", e)
        raise
```

#### `create_memory_and_wait(name, strategies, description=None, event_expiry_days=90, memory_execution_role_arn=None, max_wait=300, poll_interval=10)`

Create a memory and wait for it to become ACTIVE.

This method creates a memory and polls until it reaches ACTIVE status, providing a convenient way to ensure the memory is ready for use.

Parameters:

| Name                        | Type                   | Description                                  | Default    |
| --------------------------- | ---------------------- | -------------------------------------------- | ---------- |
| `name`                      | `str`                  | Name for the memory resource                 | *required* |
| `strategies`                | `List[Dict[str, Any]]` | List of strategy configurations              | *required* |
| `description`               | `Optional[str]`        | Optional description                         | `None`     |
| `event_expiry_days`         | `int`                  | How long to retain events (default: 90 days) | `90`       |
| `memory_execution_role_arn` | `Optional[str]`        | IAM role ARN for memory execution            | `None`     |
| `max_wait`                  | `int`                  | Maximum seconds to wait (default: 300)       | `300`      |
| `poll_interval`             | `int`                  | Seconds between status checks (default: 10)  | `10`       |

Returns:

| Type             | Description                            |
| ---------------- | -------------------------------------- |
| `Dict[str, Any]` | Created memory object in ACTIVE status |

Raises:

| Type           | Description                                     |
| -------------- | ----------------------------------------------- |
| `TimeoutError` | If memory doesn't become ACTIVE within max_wait |
| `RuntimeError` | If memory creation fails                        |

Source code in `bedrock_agentcore/memory/client.py`

```
def create_memory_and_wait(
    self,
    name: str,
    strategies: List[Dict[str, Any]],
    description: Optional[str] = None,
    event_expiry_days: int = 90,
    memory_execution_role_arn: Optional[str] = None,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Create a memory and wait for it to become ACTIVE.

    This method creates a memory and polls until it reaches ACTIVE status,
    providing a convenient way to ensure the memory is ready for use.

    Args:
        name: Name for the memory resource
        strategies: List of strategy configurations
        description: Optional description
        event_expiry_days: How long to retain events (default: 90 days)
        memory_execution_role_arn: IAM role ARN for memory execution
        max_wait: Maximum seconds to wait (default: 300)
        poll_interval: Seconds between status checks (default: 10)

    Returns:
        Created memory object in ACTIVE status

    Raises:
        TimeoutError: If memory doesn't become ACTIVE within max_wait
        RuntimeError: If memory creation fails
    """
    # Create the memory
    memory = self.create_memory(
        name=name,
        strategies=strategies,
        description=description,
        event_expiry_days=event_expiry_days,
        memory_execution_role_arn=memory_execution_role_arn,
    )

    memory_id = memory.get("memoryId", memory.get("id"))  # Handle both field names
    if memory_id is None:
        memory_id = ""
    logger.info("Created memory %s, waiting for ACTIVE status...", memory_id)

    start_time = time.time()
    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        try:
            status = self.get_memory_status(memory_id)

            if status == MemoryStatus.ACTIVE.value:
                logger.info("Memory %s is now ACTIVE (took %d seconds)", memory_id, elapsed)
                # Get fresh memory details
                response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
                memory = self._normalize_memory_response(response["memory"])
                return memory
            elif status == MemoryStatus.FAILED.value:
                # Get failure reason if available
                response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
                failure_reason = response["memory"].get("failureReason", "Unknown")
                raise RuntimeError("Memory creation failed: %s" % failure_reason)
            else:
                logger.debug("Memory status: %s (%d seconds elapsed)", status, elapsed)

        except ClientError as e:
            logger.error("Error checking memory status: %s", e)
            raise

        time.sleep(poll_interval)

    raise TimeoutError("Memory %s did not become ACTIVE within %d seconds" % (memory_id, max_wait))
```

#### `create_or_get_memory(name, strategies=None, description=None, event_expiry_days=90, memory_execution_role_arn=None)`

Create a memory resource or fetch the existing memory details if it already exists.

Returns:

| Type             | Description                                     |
| ---------------- | ----------------------------------------------- |
| `Dict[str, Any]` | Memory object, either newly created or existing |

Source code in `bedrock_agentcore/memory/client.py`

```
def create_or_get_memory(
    self,
    name: str,
    strategies: Optional[List[Dict[str, Any]]] = None,
    description: Optional[str] = None,
    event_expiry_days: int = 90,
    memory_execution_role_arn: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a memory resource or fetch the existing memory details if it already exists.

    Returns:
        Memory object, either newly created or existing
    """
    try:
        memory = self.create_memory_and_wait(
            name=name,
            strategies=strategies,
            description=description,
            event_expiry_days=event_expiry_days,
            memory_execution_role_arn=memory_execution_role_arn,
        )
        return memory
    except ClientError as e:
        if e.response["Error"]["Code"] == "ValidationException" and "already exists" in str(e):
            memories = self.list_memories()
            memory = next((m for m in memories if m["id"].startswith(name)), None)
            logger.info("Memory already exists. Using existing memory ID: %s", memory["id"])
            return memory
        else:
            logger.error("ClientError: Failed to create or get memory: %s", e)
            raise
    except Exception:
        raise
```

#### `delete_memory(memory_id)`

Delete a memory resource.

Source code in `bedrock_agentcore/memory/client.py`

```
def delete_memory(self, memory_id: str) -> Dict[str, Any]:
    """Delete a memory resource."""
    try:
        response = self.gmcp_client.delete_memory(
            memoryId=memory_id, clientToken=str(uuid.uuid4())
        )  # Input uses old field name
        logger.info("Deleted memory: %s", memory_id)
        return response
    except ClientError as e:
        logger.error("Failed to delete memory: %s", e)
        raise
```

#### `delete_memory_and_wait(memory_id, max_wait=300, poll_interval=10)`

Delete a memory and wait for deletion to complete.

This method deletes a memory and polls until it's fully deleted, ensuring clean resource cleanup.

Parameters:

| Name            | Type  | Description                            | Default    |
| --------------- | ----- | -------------------------------------- | ---------- |
| `memory_id`     | `str` | Memory resource ID to delete           | *required* |
| `max_wait`      | `int` | Maximum seconds to wait (default: 300) | `300`      |
| `poll_interval` | `int` | Seconds between checks (default: 10)   | `10`       |

Returns:

| Type             | Description             |
| ---------------- | ----------------------- |
| `Dict[str, Any]` | Final deletion response |

Raises:

| Type           | Description                                  |
| -------------- | -------------------------------------------- |
| `TimeoutError` | If deletion doesn't complete within max_wait |

Source code in `bedrock_agentcore/memory/client.py`

```
def delete_memory_and_wait(self, memory_id: str, max_wait: int = 300, poll_interval: int = 10) -> Dict[str, Any]:
    """Delete a memory and wait for deletion to complete.

    This method deletes a memory and polls until it's fully deleted,
    ensuring clean resource cleanup.

    Args:
        memory_id: Memory resource ID to delete
        max_wait: Maximum seconds to wait (default: 300)
        poll_interval: Seconds between checks (default: 10)

    Returns:
        Final deletion response

    Raises:
        TimeoutError: If deletion doesn't complete within max_wait
    """
    # Initiate deletion
    response = self.delete_memory(memory_id)
    logger.info("Initiated deletion of memory %s", memory_id)

    start_time = time.time()
    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        try:
            # Try to get the memory - if it doesn't exist, deletion is complete
            self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
            logger.debug("Memory still exists, waiting... (%d seconds elapsed)", elapsed)

        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.info("Memory %s successfully deleted (took %d seconds)", memory_id, elapsed)
                return response
            else:
                logger.error("Error checking memory status: %s", e)
                raise

        time.sleep(poll_interval)

    raise TimeoutError("Memory %s was not deleted within %d seconds" % (memory_id, max_wait))
```

#### `delete_strategy(memory_id, strategy_id)`

Delete a strategy from a memory.

Source code in `bedrock_agentcore/memory/client.py`

```
def delete_strategy(self, memory_id: str, strategy_id: str) -> Dict[str, Any]:
    """Delete a strategy from a memory."""
    return self.update_memory_strategies(memory_id=memory_id, delete_strategy_ids=[strategy_id])
```

#### `fork_conversation(memory_id, actor_id, session_id, root_event_id, branch_name, new_messages, event_timestamp=None)`

Fork a conversation from a specific event to create a new branch.

Source code in `bedrock_agentcore/memory/client.py`

```
def fork_conversation(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    root_event_id: str,
    branch_name: str,
    new_messages: List[Tuple[str, str]],
    event_timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Fork a conversation from a specific event to create a new branch."""
    try:
        branch = {"rootEventId": root_event_id, "name": branch_name}

        event = self.create_event(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            messages=new_messages,
            branch=branch,
            event_timestamp=event_timestamp,
        )

        logger.info("Created branch '%s' from event %s", branch_name, root_event_id)
        return event

    except ClientError as e:
        logger.error("Failed to fork conversation: %s", e)
        raise
```

#### `get_conversation_tree(memory_id, actor_id, session_id)`

Get a tree structure of the conversation with all branches.

This method transforms a flat list of events into a hierarchical tree structure, providing visualization-ready data that would be complex to build from raw events. It handles:

- Full pagination to get all events
- Grouping by branches
- Message summarization
- Tree structure building

Returns:

| Type             | Description                                             |
| ---------------- | ------------------------------------------------------- |
| `Dict[str, Any]` | Dictionary representing the conversation tree structure |

Source code in `bedrock_agentcore/memory/client.py`

```
def get_conversation_tree(self, memory_id: str, actor_id: str, session_id: str) -> Dict[str, Any]:
    """Get a tree structure of the conversation with all branches.

    This method transforms a flat list of events into a hierarchical tree structure,
    providing visualization-ready data that would be complex to build from raw events.
    It handles:
    - Full pagination to get all events
    - Grouping by branches
    - Message summarization
    - Tree structure building

    Returns:
        Dictionary representing the conversation tree structure
    """
    try:
        # Get all events - need to handle pagination for complete list
        all_events = []
        next_token = None

        while True:
            params = {"memoryId": memory_id, "actorId": actor_id, "sessionId": session_id, "maxResults": 100}

            if next_token:
                params["nextToken"] = next_token

            response = self.gmdp_client.list_events(**params)
            all_events.extend(response.get("events", []))

            next_token = response.get("nextToken")
            if not next_token:
                break

        # Build tree structure
        tree = {"session_id": session_id, "actor_id": actor_id, "main_branch": {"events": [], "branches": {}}}

        # Group events by branch
        for event in all_events:
            event_summary = {"eventId": event["eventId"], "timestamp": event["eventTimestamp"], "messages": []}

            # Extract message summaries
            if "payload" in event:
                for payload_item in event.get("payload", []):
                    if "conversational" in payload_item:
                        conv = payload_item["conversational"]
                        event_summary["messages"].append(
                            {"role": conv.get("role"), "text": conv.get("content", {}).get("text", "")[:50] + "..."}
                        )

            branch_info = event.get("branch")
            if branch_info:
                branch_name = branch_info["name"]
                root_event = branch_info.get("rootEventId")  # Use .get() to handle missing field

                if branch_name not in tree["main_branch"]["branches"]:
                    tree["main_branch"]["branches"][branch_name] = {"root_event_id": root_event, "events": []}

                tree["main_branch"]["branches"][branch_name]["events"].append(event_summary)
            else:
                tree["main_branch"]["events"].append(event_summary)

        logger.info("Built conversation tree with %d branches", len(tree["main_branch"]["branches"]))
        return tree

    except ClientError as e:
        logger.error("Failed to build conversation tree: %s", e)
        raise
```

#### `get_last_k_turns(memory_id, actor_id, session_id, k=5, branch_name=None, include_branches=False, max_results=100)`

Get the last K conversation turns.

A "turn" typically consists of a user message followed by assistant response(s). This method groups messages into logical turns for easier processing.

Returns:

| Type                         | Description                                                      |
| ---------------------------- | ---------------------------------------------------------------- |
| `List[List[Dict[str, Any]]]` | List of turns, where each turn is a list of message dictionaries |

Source code in `bedrock_agentcore/memory/client.py`

```
def get_last_k_turns(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    k: int = 5,
    branch_name: Optional[str] = None,
    include_branches: bool = False,
    max_results: int = 100,
) -> List[List[Dict[str, Any]]]:
    """Get the last K conversation turns.

    A "turn" typically consists of a user message followed by assistant response(s).
    This method groups messages into logical turns for easier processing.

    Returns:
        List of turns, where each turn is a list of message dictionaries
    """
    try:
        # Use the new list_events method
        events = self.list_events(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            branch_name=branch_name,
            include_parent_branches=False,
            max_results=max_results,
        )

        if not events:
            return []

        # Process events to group into turns
        turns = []
        current_turn = []

        for event in events:
            if len(turns) >= k:
                break  # Only need last K turns
            for payload_item in event.get("payload", []):
                if "conversational" in payload_item:
                    role = payload_item["conversational"].get("role")

                    # Start new turn on USER message
                    if role == Role.USER.value and current_turn:
                        turns.append(current_turn)
                        current_turn = []

                    current_turn.append(payload_item["conversational"])

        # Don't forget the last turn
        if current_turn:
            turns.append(current_turn)

        # Return the last k turns
        return turns[:k] if len(turns) > k else turns

    except ClientError as e:
        logger.error("Failed to get last K turns: %s", e)
        raise
```

#### `get_memory_status(memory_id)`

Get current memory status.

Source code in `bedrock_agentcore/memory/client.py`

```
def get_memory_status(self, memory_id: str) -> str:
    """Get current memory status."""
    try:
        response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
        return response["memory"]["status"]
    except ClientError as e:
        logger.error("Failed to get memory status: %s", e)
        raise
```

#### `get_memory_strategies(memory_id)`

Get all strategies for a memory.

Source code in `bedrock_agentcore/memory/client.py`

```
def get_memory_strategies(self, memory_id: str) -> List[Dict[str, Any]]:
    """Get all strategies for a memory."""
    try:
        response = self.gmcp_client.get_memory(memoryId=memory_id)  # Input uses old field name
        memory = response["memory"]

        # Handle both old and new field names in response
        strategies = memory.get("strategies", memory.get("memoryStrategies", []))

        # Normalize strategy fields
        normalized_strategies = []
        for strategy in strategies:
            # Create normalized version with both old and new field names
            normalized = strategy.copy()

            # Ensure both field name versions exist
            if "strategyId" in strategy and "memoryStrategyId" not in normalized:
                normalized["memoryStrategyId"] = strategy["strategyId"]
            elif "memoryStrategyId" in strategy and "strategyId" not in normalized:
                normalized["strategyId"] = strategy["memoryStrategyId"]

            if "type" in strategy and "memoryStrategyType" not in normalized:
                normalized["memoryStrategyType"] = strategy["type"]
            elif "memoryStrategyType" in strategy and "type" not in normalized:
                normalized["type"] = strategy["memoryStrategyType"]

            normalized_strategies.append(normalized)

        return normalized_strategies
    except ClientError as e:
        logger.error("Failed to get memory strategies: %s", e)
        raise
```

#### `list_branch_events(memory_id, actor_id, session_id, branch_name=None, include_parent_branches=False, max_results=100)`

List events in a specific branch.

This method provides complex filtering and pagination that would require significant boilerplate code with raw boto3. It handles:

- Automatic pagination across multiple API calls
- Branch filtering with parent event inclusion logic
- Main branch isolation (events without branch info)

Parameters:

| Name                      | Type            | Description                                    | Default    |
| ------------------------- | --------------- | ---------------------------------------------- | ---------- |
| `memory_id`               | `str`           | Memory resource ID                             | *required* |
| `actor_id`                | `str`           | Actor identifier                               | *required* |
| `session_id`              | `str`           | Session identifier                             | *required* |
| `branch_name`             | `Optional[str]` | Branch name (None for main branch)             | `None`     |
| `include_parent_branches` | `bool`          | Whether to include events from parent branches | `False`    |
| `max_results`             | `int`           | Maximum events to return                       | `100`      |

Returns:

| Type                   | Description                  |
| ---------------------- | ---------------------------- |
| `List[Dict[str, Any]]` | List of events in the branch |

Source code in `bedrock_agentcore/memory/client.py`

```
def list_branch_events(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    branch_name: Optional[str] = None,
    include_parent_branches: bool = False,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """List events in a specific branch.

    This method provides complex filtering and pagination that would require
    significant boilerplate code with raw boto3. It handles:
    - Automatic pagination across multiple API calls
    - Branch filtering with parent event inclusion logic
    - Main branch isolation (events without branch info)

    Args:
        memory_id: Memory resource ID
        actor_id: Actor identifier
        session_id: Session identifier
        branch_name: Branch name (None for main branch)
        include_parent_branches: Whether to include events from parent branches
        max_results: Maximum events to return

    Returns:
        List of events in the branch
    """
    try:
        params = {
            "memoryId": memory_id,
            "actorId": actor_id,
            "sessionId": session_id,
            "maxResults": min(100, max_results),
        }

        # Only add filter when we have a specific branch name
        if branch_name:
            params["filter"] = {"branch": {"name": branch_name, "includeParentBranches": include_parent_branches}}

        response = self.gmdp_client.list_events(**params)
        events = response.get("events", [])

        # Handle pagination
        next_token = response.get("nextToken")
        while next_token and len(events) < max_results:
            params["nextToken"] = next_token
            params["maxResults"] = min(100, max_results - len(events))
            response = self.gmdp_client.list_events(**params)
            events.extend(response.get("events", []))
            next_token = response.get("nextToken")

        # Filter for main branch if no branch specified
        if not branch_name:
            events = [e for e in events if not e.get("branch")]

        logger.info("Retrieved %d events from branch '%s'", len(events), branch_name or "main")
        return events

    except ClientError as e:
        logger.error("Failed to list branch events: %s", e)
        raise
```

#### `list_branches(memory_id, actor_id, session_id)`

List all branches in a session.

This method handles pagination automatically and provides a structured view of all conversation branches, which would require complex pagination and grouping logic if done with raw boto3 calls.

Returns:

| Type                   | Description                                              |
| ---------------------- | -------------------------------------------------------- |
| `List[Dict[str, Any]]` | List of branch information including name and root event |

Source code in `bedrock_agentcore/memory/client.py`

```
def list_branches(self, memory_id: str, actor_id: str, session_id: str) -> List[Dict[str, Any]]:
    """List all branches in a session.

    This method handles pagination automatically and provides a structured view
    of all conversation branches, which would require complex pagination and
    grouping logic if done with raw boto3 calls.

    Returns:
        List of branch information including name and root event
    """
    try:
        # Get all events - need to handle pagination for complete list
        all_events = []
        next_token = None

        while True:
            params = {"memoryId": memory_id, "actorId": actor_id, "sessionId": session_id, "maxResults": 100}

            if next_token:
                params["nextToken"] = next_token

            response = self.gmdp_client.list_events(**params)
            all_events.extend(response.get("events", []))

            next_token = response.get("nextToken")
            if not next_token:
                break

        branches = {}
        main_branch_events = []

        for event in all_events:
            branch_info = event.get("branch")
            if branch_info:
                branch_name = branch_info["name"]
                if branch_name not in branches:
                    branches[branch_name] = {
                        "name": branch_name,
                        "rootEventId": branch_info.get("rootEventId"),
                        "firstEventId": event["eventId"],
                        "eventCount": 1,
                        "created": event["eventTimestamp"],
                    }
                else:
                    branches[branch_name]["eventCount"] += 1
            else:
                main_branch_events.append(event)

        # Build result list
        result = []

        # Only add main branch if there are actual events
        if main_branch_events:
            result.append(
                {
                    "name": "main",
                    "rootEventId": None,
                    "firstEventId": main_branch_events[0]["eventId"],
                    "eventCount": len(main_branch_events),
                    "created": main_branch_events[0]["eventTimestamp"],
                }
            )

        # Add other branches
        result.extend(list(branches.values()))

        logger.info("Found %d branches in session %s", len(result), session_id)
        return result

    except ClientError as e:
        logger.error("Failed to list branches: %s", e)
        raise
```

#### `list_events(memory_id, actor_id, session_id, branch_name=None, include_parent_branches=False, max_results=100, include_payload=True)`

List all events in a session with pagination support.

This method provides direct access to the raw events API, allowing developers to retrieve all events without the turn grouping logic of get_last_k_turns.

Parameters:

| Name                      | Type            | Description                                                             | Default    |
| ------------------------- | --------------- | ----------------------------------------------------------------------- | ---------- |
| `memory_id`               | `str`           | Memory resource ID                                                      | *required* |
| `actor_id`                | `str`           | Actor identifier                                                        | *required* |
| `session_id`              | `str`           | Session identifier                                                      | *required* |
| `branch_name`             | `Optional[str]` | Optional branch name to filter events (None for all branches)           | `None`     |
| `include_parent_branches` | `bool`          | Whether to include parent branch events (only applies with branch_name) | `False`    |
| `max_results`             | `int`           | Maximum number of events to return                                      | `100`      |
| `include_payload`         | `bool`          | Whether to include event payloads in response                           | `True`     |

Returns:

| Type                   | Description                                       |
| ---------------------- | ------------------------------------------------- |
| `List[Dict[str, Any]]` | List of event dictionaries in chronological order |

Example

##### Get all events

events = client.list_events(memory_id, actor_id, session_id)

##### Get only main branch events

main_events = client.list_events(memory_id, actor_id, session_id, branch_name="main")

##### Get events from a specific branch

branch_events = client.list_events(memory_id, actor_id, session_id, branch_name="test-branch")

Source code in `bedrock_agentcore/memory/client.py`

```
def list_events(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    branch_name: Optional[str] = None,
    include_parent_branches: bool = False,
    max_results: int = 100,
    include_payload: bool = True,
) -> List[Dict[str, Any]]:
    """List all events in a session with pagination support.

    This method provides direct access to the raw events API, allowing developers
    to retrieve all events without the turn grouping logic of get_last_k_turns.

    Args:
        memory_id: Memory resource ID
        actor_id: Actor identifier
        session_id: Session identifier
        branch_name: Optional branch name to filter events (None for all branches)
        include_parent_branches: Whether to include parent branch events (only applies with branch_name)
        max_results: Maximum number of events to return
        include_payload: Whether to include event payloads in response

    Returns:
        List of event dictionaries in chronological order

    Example:
        # Get all events
        events = client.list_events(memory_id, actor_id, session_id)

        # Get only main branch events
        main_events = client.list_events(memory_id, actor_id, session_id, branch_name="main")

        # Get events from a specific branch
        branch_events = client.list_events(memory_id, actor_id, session_id, branch_name="test-branch")
    """
    try:
        all_events = []
        next_token = None

        while len(all_events) < max_results:
            params = {
                "memoryId": memory_id,
                "actorId": actor_id,
                "sessionId": session_id,
                "maxResults": min(100, max_results - len(all_events)),
                "includePayloads": include_payload,
            }

            if next_token:
                params["nextToken"] = next_token

            # Add branch filter if specified (but not for "main")
            if branch_name and branch_name != "main":
                params["filter"] = {
                    "branch": {"name": branch_name, "includeParentBranches": include_parent_branches}
                }

            response = self.gmdp_client.list_events(**params)

            events = response.get("events", [])
            all_events.extend(events)

            next_token = response.get("nextToken")
            if not next_token or len(all_events) >= max_results:
                break

        logger.info("Retrieved total of %d events", len(all_events))
        return all_events[:max_results]

    except ClientError as e:
        logger.error("Failed to list events: %s", e)
        raise
```

#### `list_memories(max_results=100)`

List all memories for the account.

Source code in `bedrock_agentcore/memory/client.py`

```
def list_memories(self, max_results: int = 100) -> List[Dict[str, Any]]:
    """List all memories for the account."""
    try:
        # Ensure max_results doesn't exceed API limit per request
        results_per_request = min(max_results, 100)

        response = self.gmcp_client.list_memories(maxResults=results_per_request)
        memories = response.get("memories", [])

        next_token = response.get("nextToken")
        while next_token and len(memories) < max_results:
            remaining = max_results - len(memories)
            results_per_request = min(remaining, 100)

            response = self.gmcp_client.list_memories(maxResults=results_per_request, nextToken=next_token)
            memories.extend(response.get("memories", []))
            next_token = response.get("nextToken")

        # Normalize memory summaries if they contain new field names
        normalized_memories = []
        for memory in memories[:max_results]:
            normalized = memory.copy()
            # Ensure both field name versions exist
            if "id" in memory and "memoryId" not in normalized:
                normalized["memoryId"] = memory["id"]
            elif "memoryId" in memory and "id" not in normalized:
                normalized["id"] = memory["memoryId"]
            normalized_memories.append(normalized)

        return normalized_memories

    except ClientError as e:
        logger.error("Failed to list memories: %s", e)
        raise
```

#### `merge_branch_context(memory_id, actor_id, session_id, branch_name, include_parent=True)`

Get all messages from a branch for context building.

Parameters:

| Name             | Type   | Description                             | Default    |
| ---------------- | ------ | --------------------------------------- | ---------- |
| `memory_id`      | `str`  | Memory resource ID                      | *required* |
| `actor_id`       | `str`  | Actor identifier                        | *required* |
| `session_id`     | `str`  | Session identifier                      | *required* |
| `branch_name`    | `str`  | Branch to get context from              | *required* |
| `include_parent` | `bool` | Whether to include parent branch events | `True`     |

Returns:

| Type                   | Description                                 |
| ---------------------- | ------------------------------------------- |
| `List[Dict[str, Any]]` | List of all messages in chronological order |

Source code in `bedrock_agentcore/memory/client.py`

```
def merge_branch_context(
    self, memory_id: str, actor_id: str, session_id: str, branch_name: str, include_parent: bool = True
) -> List[Dict[str, Any]]:
    """Get all messages from a branch for context building.

    Args:
        memory_id: Memory resource ID
        actor_id: Actor identifier
        session_id: Session identifier
        branch_name: Branch to get context from
        include_parent: Whether to include parent branch events

    Returns:
        List of all messages in chronological order
    """
    events = self.list_branch_events(
        memory_id=memory_id,
        actor_id=actor_id,
        session_id=session_id,
        branch_name=branch_name,
        include_parent_branches=include_parent,
        max_results=100,
    )

    messages = []
    for event in events:
        if "payload" in event:
            for payload_item in event.get("payload", []):
                if "conversational" in payload_item:
                    conv = payload_item["conversational"]
                    messages.append(
                        {
                            "timestamp": event["eventTimestamp"],
                            "eventId": event["eventId"],
                            "branch": event.get("branch", {}).get("name", "main"),
                            "role": conv.get("role"),
                            "content": conv.get("content", {}).get("text", ""),
                        }
                    )

    # Sort by timestamp
    messages.sort(key=lambda x: x["timestamp"])

    logger.info("Retrieved %d messages from branch '%s'", len(messages), branch_name)
    return messages
```

#### `modify_strategy(memory_id, strategy_id, description=None, namespaces=None, configuration=None)`

Modify a strategy with full control over configuration.

Source code in `bedrock_agentcore/memory/client.py`

```
def modify_strategy(
    self,
    memory_id: str,
    strategy_id: str,
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
    configuration: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Modify a strategy with full control over configuration."""
    modify_config: Dict = {"memoryStrategyId": strategy_id}  # Using old field name for input

    if description is not None:
        modify_config["description"] = description
    if namespaces is not None:
        modify_config["namespaces"] = namespaces
    if configuration is not None:
        modify_config["configuration"] = configuration

    return self.update_memory_strategies(memory_id=memory_id, modify_strategies=[modify_config])
```

#### `process_turn(memory_id, actor_id, session_id, user_input, agent_response, event_timestamp=None, retrieval_namespace=None, retrieval_query=None, top_k=3)`

DEPRECATED: Use retrieve_memories() and save_conversation() separately.

This method will be removed in v1.0.0.

Source code in `bedrock_agentcore/memory/client.py`

```
def process_turn(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    user_input: str,
    agent_response: str,
    event_timestamp: Optional[datetime] = None,
    retrieval_namespace: Optional[str] = None,
    retrieval_query: Optional[str] = None,
    top_k: int = 3,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """DEPRECATED: Use retrieve_memories() and save_conversation() separately.

    This method will be removed in v1.0.0.
    """
    warnings.warn(
        "process_turn() is deprecated and will be removed in v1.0.0. "
        "Use retrieve_memories() and save_conversation() separately, or use process_turn_with_llm().",
        DeprecationWarning,
        stacklevel=2,
    )

    retrieved_memories = []

    if retrieval_namespace:
        search_query = retrieval_query or user_input
        retrieved_memories = self.retrieve_memories(
            memory_id=memory_id, namespace=retrieval_namespace, query=search_query, top_k=top_k
        )

    event = self.save_turn(
        memory_id=memory_id,
        actor_id=actor_id,
        session_id=session_id,
        user_input=user_input,
        agent_response=agent_response,
        event_timestamp=event_timestamp,
    )

    return retrieved_memories, event
```

#### `process_turn_with_llm(memory_id, actor_id, session_id, user_input, llm_callback, retrieval_namespace=None, retrieval_query=None, top_k=3, event_timestamp=None)`

Complete conversation turn with LLM callback integration.

This method combines memory retrieval, LLM invocation, and response storage in a single call using a callback pattern.

Parameters:

| Name                  | Type                                         | Description                                                                                                                                                                      | Default    |
| --------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `memory_id`           | `str`                                        | Memory resource ID                                                                                                                                                               | *required* |
| `actor_id`            | `str`                                        | Actor identifier (e.g., "user-123")                                                                                                                                              | *required* |
| `session_id`          | `str`                                        | Session identifier                                                                                                                                                               | *required* |
| `user_input`          | `str`                                        | The user's message                                                                                                                                                               | *required* |
| `llm_callback`        | `Callable[[str, List[Dict[str, Any]]], str]` | Function that takes (user_input, memories) and returns agent_response The callback receives the user input and retrieved memories, and should return the agent's response string | *required* |
| `retrieval_namespace` | `Optional[str]`                              | Namespace to search for memories (optional)                                                                                                                                      | `None`     |
| `retrieval_query`     | `Optional[str]`                              | Custom search query (defaults to user_input)                                                                                                                                     | `None`     |
| `top_k`               | `int`                                        | Number of memories to retrieve                                                                                                                                                   | `3`        |
| `event_timestamp`     | `Optional[datetime]`                         | Optional timestamp for the event                                                                                                                                                 | `None`     |

Returns:

| Type                                               | Description                                                  |
| -------------------------------------------------- | ------------------------------------------------------------ |
| `Tuple[List[Dict[str, Any]], str, Dict[str, Any]]` | Tuple of (retrieved_memories, agent_response, created_event) |

Example

def my_llm(user_input: str, memories: List[Dict]) -> str:

# Format context from memories

context = "\\n".join([m'content' for m in memories])

```
# Call your LLM (Bedrock, OpenAI, etc.)
response = bedrock.invoke_model(
    messages=[
        {"role": "system", "content": f"Context: {context}"},
        {"role": "user", "content": user_input}
    ]
)
return response['content']
```

memories, response, event = client.process_turn_with_llm( memory_id="mem-xyz", actor_id="user-123", session_id="session-456", user_input="What did we discuss yesterday?", llm_callback=my_llm, retrieval_namespace="support/facts/{sessionId}" )

Source code in `bedrock_agentcore/memory/client.py`

```
def process_turn_with_llm(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    user_input: str,
    llm_callback: Callable[[str, List[Dict[str, Any]]], str],
    retrieval_namespace: Optional[str] = None,
    retrieval_query: Optional[str] = None,
    top_k: int = 3,
    event_timestamp: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    r"""Complete conversation turn with LLM callback integration.

    This method combines memory retrieval, LLM invocation, and response storage
    in a single call using a callback pattern.

    Args:
        memory_id: Memory resource ID
        actor_id: Actor identifier (e.g., "user-123")
        session_id: Session identifier
        user_input: The user's message
        llm_callback: Function that takes (user_input, memories) and returns agent_response
                     The callback receives the user input and retrieved memories,
                     and should return the agent's response string
        retrieval_namespace: Namespace to search for memories (optional)
        retrieval_query: Custom search query (defaults to user_input)
        top_k: Number of memories to retrieve
        event_timestamp: Optional timestamp for the event

    Returns:
        Tuple of (retrieved_memories, agent_response, created_event)

    Example:
        def my_llm(user_input: str, memories: List[Dict]) -> str:
            # Format context from memories
            context = "\\n".join([m['content']['text'] for m in memories])

            # Call your LLM (Bedrock, OpenAI, etc.)
            response = bedrock.invoke_model(
                messages=[
                    {"role": "system", "content": f"Context: {context}"},
                    {"role": "user", "content": user_input}
                ]
            )
            return response['content']

        memories, response, event = client.process_turn_with_llm(
            memory_id="mem-xyz",
            actor_id="user-123",
            session_id="session-456",
            user_input="What did we discuss yesterday?",
            llm_callback=my_llm,
            retrieval_namespace="support/facts/{sessionId}"
        )
    """
    # Step 1: Retrieve relevant memories
    retrieved_memories = []
    if retrieval_namespace:
        search_query = retrieval_query or user_input
        retrieved_memories = self.retrieve_memories(
            memory_id=memory_id, namespace=retrieval_namespace, query=search_query, top_k=top_k
        )
        logger.info("Retrieved %d memories for LLM context", len(retrieved_memories))

    # Step 2: Invoke LLM callback
    try:
        agent_response = llm_callback(user_input, retrieved_memories)
        if not isinstance(agent_response, str):
            raise ValueError("LLM callback must return a string response")
        logger.info("LLM callback generated response")
    except Exception as e:
        logger.error("LLM callback failed: %s", e)
        raise

    # Step 3: Save the conversation turn
    event = self.create_event(
        memory_id=memory_id,
        actor_id=actor_id,
        session_id=session_id,
        messages=[(user_input, "USER"), (agent_response, "ASSISTANT")],
        event_timestamp=event_timestamp,
    )

    logger.info("Completed full conversation turn with LLM")
    return retrieved_memories, agent_response, event
```

#### `retrieve_memories(memory_id, namespace, query, actor_id=None, top_k=3)`

Retrieve relevant memories from a namespace.

Note: Wildcards (\*) are NOT supported in namespaces. You must provide the exact namespace path with all variables resolved.

Parameters:

| Name        | Type            | Description                                   | Default    |
| ----------- | --------------- | --------------------------------------------- | ---------- |
| `memory_id` | `str`           | Memory resource ID                            | *required* |
| `namespace` | `str`           | Exact namespace path (no wildcards)           | *required* |
| `query`     | `str`           | Search query                                  | *required* |
| `actor_id`  | `Optional[str]` | Optional actor ID (deprecated, use namespace) | `None`     |
| `top_k`     | `int`           | Number of results to return                   | `3`        |

Returns:

| Type                   | Description            |
| ---------------------- | ---------------------- |
| `List[Dict[str, Any]]` | List of memory records |

Example

##### Correct - exact namespace

memories = client.retrieve_memories( memory_id="mem-123", namespace="support/facts/session-456", query="customer preferences" )

##### Incorrect - wildcards not supported

##### memories = client.retrieve_memories(..., namespace="support/facts/\*", ...)

Source code in `bedrock_agentcore/memory/client.py`

```
def retrieve_memories(
    self, memory_id: str, namespace: str, query: str, actor_id: Optional[str] = None, top_k: int = 3
) -> List[Dict[str, Any]]:
    """Retrieve relevant memories from a namespace.

    Note: Wildcards (*) are NOT supported in namespaces. You must provide the
    exact namespace path with all variables resolved.

    Args:
        memory_id: Memory resource ID
        namespace: Exact namespace path (no wildcards)
        query: Search query
        actor_id: Optional actor ID (deprecated, use namespace)
        top_k: Number of results to return

    Returns:
        List of memory records

    Example:
        # Correct - exact namespace
        memories = client.retrieve_memories(
            memory_id="mem-123",
            namespace="support/facts/session-456",
            query="customer preferences"
        )

        # Incorrect - wildcards not supported
        # memories = client.retrieve_memories(..., namespace="support/facts/*", ...)
    """
    if "*" in namespace:
        logger.error("Wildcards are not supported in namespaces. Please provide exact namespace.")
        return []

    try:
        # Let service handle all namespace validation
        response = self.gmdp_client.retrieve_memory_records(
            memoryId=memory_id, namespace=namespace, searchCriteria={"searchQuery": query, "topK": top_k}
        )

        memories = response.get("memoryRecordSummaries", [])
        logger.info("Retrieved %d memories from namespace: %s", len(memories), namespace)
        return memories

    except ClientError as e:
        error_code = e.response["Error"]["Code"]
        error_msg = e.response["Error"]["Message"]

        if error_code == "ResourceNotFoundException":
            logger.warning(
                "Memory or namespace not found. Ensure memory %s exists and namespace '%s' is configured",
                memory_id,
                namespace,
            )
        elif error_code == "ValidationException":
            logger.warning("Invalid search parameters: %s", error_msg)
        elif error_code == "ServiceException":
            logger.warning("Service error: %s. This may be temporary - try again later", error_msg)
        else:
            logger.warning("Memory retrieval failed (%s): %s", error_code, error_msg)

        return []
```

#### `save_conversation(memory_id, actor_id, session_id, messages, event_timestamp=None, branch=None)`

DEPRECATED: Use create_event() instead.

Parameters:

| Name              | Type                       | Description                                                                                                                                                            | Default    |
| ----------------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `memory_id`       | `str`                      | Memory resource ID                                                                                                                                                     | *required* |
| `actor_id`        | `str`                      | Actor identifier                                                                                                                                                       | *required* |
| `session_id`      | `str`                      | Session identifier                                                                                                                                                     | *required* |
| `messages`        | `List[Tuple[str, str]]`    | List of (text, role) tuples. Role can be USER, ASSISTANT, TOOL, etc.                                                                                                   | *required* |
| `event_timestamp` | `Optional[datetime]`       | Optional timestamp for the entire event (not per message)                                                                                                              | `None`     |
| `branch`          | `Optional[Dict[str, str]]` | Optional branch info. For new branches: {"rootEventId": "...", "name": "..."} For continuing existing branch: {"name": "..."} or {"name": "...", "rootEventId": "..."} | `None`     |

Returns:

| Type             | Description   |
| ---------------- | ------------- |
| `Dict[str, Any]` | Created event |

Example

##### Save multi-turn conversation

event = client.save_conversation( memory_id="mem-xyz", actor_id="user-123", session_id="session-456", messages=[ ("What's the weather?", "USER"), ("And tomorrow?", "USER"), ("Checking weather...", "TOOL"), ("Today sunny, tomorrow rain", "ASSISTANT") ] )

##### Continue existing branch (only name required)

event = client.save_conversation( memory_id="mem-xyz", actor_id="user-123", session_id="session-456", messages=[("Continue conversation", "USER")], branch={"name": "existing-branch"} )

Source code in `bedrock_agentcore/memory/client.py`

```
def save_conversation(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    messages: List[Tuple[str, str]],
    event_timestamp: Optional[datetime] = None,
    branch: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """DEPRECATED: Use create_event() instead.

    Args:
        memory_id: Memory resource ID
        actor_id: Actor identifier
        session_id: Session identifier
        messages: List of (text, role) tuples. Role can be USER, ASSISTANT, TOOL, etc.
        event_timestamp: Optional timestamp for the entire event (not per message)
        branch: Optional branch info. For new branches: {"rootEventId": "...", "name": "..."}
               For continuing existing branch: {"name": "..."} or {"name": "...", "rootEventId": "..."}

    Returns:
        Created event

    Example:
        # Save multi-turn conversation
        event = client.save_conversation(
            memory_id="mem-xyz",
            actor_id="user-123",
            session_id="session-456",
            messages=[
                ("What's the weather?", "USER"),
                ("And tomorrow?", "USER"),
                ("Checking weather...", "TOOL"),
                ("Today sunny, tomorrow rain", "ASSISTANT")
            ]
        )

        # Continue existing branch (only name required)
        event = client.save_conversation(
            memory_id="mem-xyz",
            actor_id="user-123",
            session_id="session-456",
            messages=[("Continue conversation", "USER")],
            branch={"name": "existing-branch"}
        )
    """
    try:
        if not messages:
            raise ValueError("At least one message is required")

        # Build payload
        payload = []

        for msg in messages:
            if len(msg) != 2:
                raise ValueError("Each message must be (text, role)")

            text, role = msg

            # Validate role
            try:
                role_enum = MessageRole(role.upper())
            except ValueError as err:
                raise ValueError(
                    "Invalid role '%s'. Must be one of: %s" % (role, ", ".join([r.value for r in MessageRole]))
                ) from err

            payload.append({"conversational": {"content": {"text": text}, "role": role_enum.value}})

        # Use provided timestamp or current time
        if event_timestamp is None:
            event_timestamp = datetime.utcnow()

        params = {
            "memoryId": memory_id,
            "actorId": actor_id,
            "sessionId": session_id,
            "eventTimestamp": event_timestamp,
            "payload": payload,
            "clientToken": str(uuid.uuid4()),
        }

        if branch:
            params["branch"] = branch

        response = self.gmdp_client.create_event(**params)

        event = response["event"]
        logger.info("Created event: %s", event["eventId"])

        return event

    except ClientError as e:
        logger.error("Failed to create event: %s", e)
        raise
```

#### `save_turn(memory_id, actor_id, session_id, user_input, agent_response, event_timestamp=None)`

DEPRECATED: Use save_conversation() for more flexibility.

This method will be removed in v1.0.0.

Source code in `bedrock_agentcore/memory/client.py`

```
def save_turn(
    self,
    memory_id: str,
    actor_id: str,
    session_id: str,
    user_input: str,
    agent_response: str,
    event_timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    """DEPRECATED: Use save_conversation() for more flexibility.

    This method will be removed in v1.0.0.
    """
    warnings.warn(
        "save_turn() is deprecated and will be removed in v1.0.0. "
        "Use save_conversation() for flexible message handling.",
        DeprecationWarning,
        stacklevel=2,
    )

    messages = [(user_input, "USER"), (agent_response, "ASSISTANT")]

    return self.create_event(
        memory_id=memory_id,
        actor_id=actor_id,
        session_id=session_id,
        messages=messages,
        event_timestamp=event_timestamp,
    )
```

#### `update_memory_strategies(memory_id, add_strategies=None, modify_strategies=None, delete_strategy_ids=None)`

Update memory strategies - add, modify, or delete.

Source code in `bedrock_agentcore/memory/client.py`

```
def update_memory_strategies(
    self,
    memory_id: str,
    add_strategies: Optional[List[Dict[str, Any]]] = None,
    modify_strategies: Optional[List[Dict[str, Any]]] = None,
    delete_strategy_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Update memory strategies - add, modify, or delete."""
    try:
        memory_strategies = {}

        if add_strategies:
            processed_add = self._add_default_namespaces(add_strategies)
            memory_strategies["addMemoryStrategies"] = processed_add  # Using old field name for input

        if modify_strategies:
            current_strategies = self.get_memory_strategies(memory_id)
            strategy_map = {s["memoryStrategyId"]: s for s in current_strategies}  # Using normalized field

            modify_list = []
            for strategy in modify_strategies:
                if "memoryStrategyId" not in strategy:  # Using old field name
                    raise ValueError("Each modify strategy must include memoryStrategyId")

                strategy_id = strategy["memoryStrategyId"]  # Using old field name
                strategy_info = strategy_map.get(strategy_id)

                if not strategy_info:
                    raise ValueError("Strategy %s not found in memory %s" % (strategy_id, memory_id))

                strategy_type = strategy_info["memoryStrategyType"]  # Using normalized field
                override_type = strategy_info.get("configuration", {}).get("type")

                strategy_copy = copy.deepcopy(strategy)

                if "configuration" in strategy_copy:
                    wrapped_config = self._wrap_configuration(
                        strategy_copy["configuration"], strategy_type, override_type
                    )
                    strategy_copy["configuration"] = wrapped_config

                modify_list.append(strategy_copy)

            memory_strategies["modifyMemoryStrategies"] = modify_list  # Using old field name for input

        if delete_strategy_ids:
            delete_list = [{"memoryStrategyId": sid} for sid in delete_strategy_ids]  # Using old field name
            memory_strategies["deleteMemoryStrategies"] = delete_list  # Using old field name for input

        if not memory_strategies:
            raise ValueError("No strategy operations provided")

        response = self.gmcp_client.update_memory(
            memoryId=memory_id,
            memoryStrategies=memory_strategies,
            clientToken=str(uuid.uuid4()),  # Using old field names for input
        )

        logger.info("Updated memory strategies for: %s", memory_id)
        memory = self._normalize_memory_response(response["memory"])
        return memory

    except ClientError as e:
        logger.error("Failed to update memory strategies: %s", e)
        raise
```

#### `update_memory_strategies_and_wait(memory_id, add_strategies=None, modify_strategies=None, delete_strategy_ids=None, max_wait=300, poll_interval=10)`

Update memory strategies and wait for memory to return to ACTIVE state.

This method handles the temporary CREATING state that occurs when updating strategies, preventing subsequent update errors.

Source code in `bedrock_agentcore/memory/client.py`

```
def update_memory_strategies_and_wait(
    self,
    memory_id: str,
    add_strategies: Optional[List[Dict[str, Any]]] = None,
    modify_strategies: Optional[List[Dict[str, Any]]] = None,
    delete_strategy_ids: Optional[List[str]] = None,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Update memory strategies and wait for memory to return to ACTIVE state.

    This method handles the temporary CREATING state that occurs when
    updating strategies, preventing subsequent update errors.
    """
    # Update strategies
    self.update_memory_strategies(memory_id, add_strategies, modify_strategies, delete_strategy_ids)

    # Wait for memory to return to ACTIVE
    return self._wait_for_memory_active(memory_id, max_wait, poll_interval)
```

#### `wait_for_memories(memory_id, namespace, test_query='test', max_wait=180, poll_interval=15)`

Wait for memory extraction to complete by polling.

IMPORTANT LIMITATIONS:

1. This method only works reliably on empty namespaces. If there are already existing memories in the namespace, this method may return True immediately even if new extractions haven't completed.
1. Wildcards (*) are NOT supported in namespaces. You must provide the exact namespace path with all variables resolved (e.g., "support/facts/session-123" not "support/facts/*").

For subsequent extractions in populated namespaces, use a fixed wait time: time.sleep(150) # Wait 2.5 minutes for extraction

Parameters:

| Name            | Type  | Description                             | Default    |
| --------------- | ----- | --------------------------------------- | ---------- |
| `memory_id`     | `str` | Memory resource ID                      | *required* |
| `namespace`     | `str` | Exact namespace to check (no wildcards) | *required* |
| `test_query`    | `str` | Query to test with (default: "test")    | `'test'`   |
| `max_wait`      | `int` | Maximum seconds to wait (default: 180)  | `180`      |
| `poll_interval` | `int` | Seconds between checks (default: 15)    | `15`       |

Returns:

| Type   | Description                              |
| ------ | ---------------------------------------- |
| `bool` | True if memories found, False if timeout |

Note

This method will be deprecated in future versions once the API provides extraction status or timestamps.

Source code in `bedrock_agentcore/memory/client.py`

```
def wait_for_memories(
    self, memory_id: str, namespace: str, test_query: str = "test", max_wait: int = 180, poll_interval: int = 15
) -> bool:
    """Wait for memory extraction to complete by polling.

    IMPORTANT LIMITATIONS:
    1. This method only works reliably on empty namespaces. If there are already
       existing memories in the namespace, this method may return True immediately
       even if new extractions haven't completed.
    2. Wildcards (*) are NOT supported in namespaces. You must provide the exact
       namespace path with all variables resolved (e.g., "support/facts/session-123"
       not "support/facts/*").

    For subsequent extractions in populated namespaces, use a fixed wait time:
        time.sleep(150)  # Wait 2.5 minutes for extraction

    Args:
        memory_id: Memory resource ID
        namespace: Exact namespace to check (no wildcards)
        test_query: Query to test with (default: "test")
        max_wait: Maximum seconds to wait (default: 180)
        poll_interval: Seconds between checks (default: 15)

    Returns:
        True if memories found, False if timeout

    Note:
        This method will be deprecated in future versions once the API
        provides extraction status or timestamps.
    """
    if "*" in namespace:
        logger.error("Wildcards are not supported in namespaces. Please provide exact namespace.")
        return False

    logger.warning(
        "wait_for_memories() only works reliably on empty namespaces. "
        "For populated namespaces, consider using a fixed wait time instead."
    )

    logger.info("Waiting for memory extraction in namespace: %s", namespace)
    start_time = time.time()
    service_errors = 0

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        try:
            memories = self.retrieve_memories(memory_id=memory_id, namespace=namespace, query=test_query, top_k=1)

            if memories:
                logger.info("Memory extraction complete after %d seconds", elapsed)
                return True

            # Reset service error count on successful call
            service_errors = 0

        except Exception as e:
            if "ServiceException" in str(e):
                service_errors += 1
                if service_errors >= 3:
                    logger.warning("Multiple service errors - the service may be experiencing issues")
            logger.debug("Retrieval attempt failed: %s", e)

        if time.time() - start_time < max_wait:
            time.sleep(poll_interval)

    logger.warning("No memories found after %d seconds", max_wait)
    if service_errors > 0:
        logger.info("Note: Encountered %d service errors during polling", service_errors)
    return False
```

### `MemoryControlPlaneClient`

Client for Bedrock AgentCore Memory control plane operations.

Source code in `bedrock_agentcore/memory/controlplane.py`

```
class MemoryControlPlaneClient:
    """Client for Bedrock AgentCore Memory control plane operations."""

    def __init__(self, region_name: str = "us-west-2", environment: str = "prod"):
        """Initialize the Memory Control Plane client.

        Args:
            region_name: AWS region name
            environment: Environment name (prod, gamma, etc.)
        """
        self.region_name = region_name
        self.environment = environment

        self.endpoint = os.getenv(
            "BEDROCK_AGENTCORE_CONTROL_ENDPOINT", f"https://bedrock-agentcore-control.{region_name}.amazonaws.com"
        )

        service_name = os.getenv("BEDROCK_AGENTCORE_CONTROL_SERVICE", "bedrock-agentcore-control")
        self.client = boto3.client(service_name, region_name=self.region_name, endpoint_url=self.endpoint)

        logger.info("Initialized MemoryControlPlaneClient for %s in %s", environment, region_name)

    # ==================== MEMORY OPERATIONS ====================

    def create_memory(
        self,
        name: str,
        event_expiry_days: int = 90,
        description: Optional[str] = None,
        memory_execution_role_arn: Optional[str] = None,
        strategies: Optional[List[Dict[str, Any]]] = None,
        wait_for_active: bool = False,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Create a memory resource with optional strategies.

        Args:
            name: Name for the memory resource
            event_expiry_days: How long to retain events (default: 90 days)
            description: Optional description
            memory_execution_role_arn: IAM role ARN for memory execution
            strategies: Optional list of strategy configurations
            wait_for_active: Whether to wait for memory to become ACTIVE
            max_wait: Maximum seconds to wait if wait_for_active is True
            poll_interval: Seconds between status checks if wait_for_active is True

        Returns:
            Created memory object
        """
        params = {
            "name": name,
            "eventExpiryDuration": event_expiry_days,
            "clientToken": str(uuid.uuid4()),
        }

        if description:
            params["description"] = description

        if memory_execution_role_arn:
            params["memoryExecutionRoleArn"] = memory_execution_role_arn

        if strategies:
            params["memoryStrategies"] = strategies

        try:
            response = self.client.create_memory(**params)
            memory = response["memory"]
            memory_id = memory["id"]

            logger.info("Created memory: %s", memory_id)

            if wait_for_active:
                return self._wait_for_memory_active(memory_id, max_wait, poll_interval)

            return memory

        except ClientError as e:
            logger.error("Failed to create memory: %s", e)
            raise

    def get_memory(self, memory_id: str, include_strategies: bool = True) -> Dict[str, Any]:
        """Get a memory resource by ID.

        Args:
            memory_id: Memory resource ID
            include_strategies: Whether to include strategy details in response

        Returns:
            Memory resource details
        """
        try:
            response = self.client.get_memory(memoryId=memory_id)
            memory = response["memory"]

            # Add strategy count
            strategies = memory.get("strategies", [])
            memory["strategyCount"] = len(strategies)

            # Remove strategies if not requested
            if not include_strategies and "strategies" in memory:
                del memory["strategies"]

            return memory

        except ClientError as e:
            logger.error("Failed to get memory: %s", e)
            raise

    def list_memories(self, max_results: int = 100) -> List[Dict[str, Any]]:
        """List all memories for the account with pagination support.

        Args:
            max_results: Maximum number of memories to return

        Returns:
            List of memory summaries
        """
        try:
            memories = []
            next_token = None

            while len(memories) < max_results:
                params = {"maxResults": min(100, max_results - len(memories))}
                if next_token:
                    params["nextToken"] = next_token

                response = self.client.list_memories(**params)
                batch = response.get("memories", [])
                memories.extend(batch)

                next_token = response.get("nextToken")
                if not next_token or len(memories) >= max_results:
                    break

            # Add strategy count to each memory summary
            for memory in memories:
                memory["strategyCount"] = 0  # List memories doesn't include strategies

            return memories[:max_results]

        except ClientError as e:
            logger.error("Failed to list memories: %s", e)
            raise

    def update_memory(
        self,
        memory_id: str,
        description: Optional[str] = None,
        event_expiry_days: Optional[int] = None,
        memory_execution_role_arn: Optional[str] = None,
        add_strategies: Optional[List[Dict[str, Any]]] = None,
        modify_strategies: Optional[List[Dict[str, Any]]] = None,
        delete_strategy_ids: Optional[List[str]] = None,
        wait_for_active: bool = False,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Update a memory resource properties and/or strategies.

        Args:
            memory_id: Memory resource ID
            description: Optional new description
            event_expiry_days: Optional new event expiry duration
            memory_execution_role_arn: Optional new execution role ARN
            add_strategies: Optional list of strategies to add
            modify_strategies: Optional list of strategies to modify
            delete_strategy_ids: Optional list of strategy IDs to delete
            wait_for_active: Whether to wait for memory to become ACTIVE
            max_wait: Maximum seconds to wait if wait_for_active is True
            poll_interval: Seconds between status checks if wait_for_active is True

        Returns:
            Updated memory object
        """
        params: Dict = {
            "memoryId": memory_id,
            "clientToken": str(uuid.uuid4()),
        }

        # Add memory properties if provided
        if description is not None:
            params["description"] = description

        if event_expiry_days is not None:
            params["eventExpiryDuration"] = event_expiry_days

        if memory_execution_role_arn is not None:
            params["memoryExecutionRoleArn"] = memory_execution_role_arn

        # Add strategy operations if provided
        memory_strategies = {}

        if add_strategies:
            memory_strategies["addMemoryStrategies"] = add_strategies

        if modify_strategies:
            memory_strategies["modifyMemoryStrategies"] = modify_strategies

        if delete_strategy_ids:
            memory_strategies["deleteMemoryStrategies"] = [
                {"memoryStrategyId": strategy_id} for strategy_id in delete_strategy_ids
            ]

        if memory_strategies:
            params["memoryStrategies"] = memory_strategies

        try:
            response = self.client.update_memory(**params)
            memory = response["memory"]
            logger.info("Updated memory: %s", memory_id)

            if wait_for_active:
                return self._wait_for_memory_active(memory_id, max_wait, poll_interval)

            return memory

        except ClientError as e:
            logger.error("Failed to update memory: %s", e)
            raise

    def delete_memory(
        self,
        memory_id: str,
        wait_for_deletion: bool = False,
        wait_for_strategies: bool = False,  # Changed default to False
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Delete a memory resource.

        Args:
            memory_id: Memory resource ID to delete
            wait_for_deletion: Whether to wait for complete deletion
            wait_for_strategies: Whether to wait for strategies to become ACTIVE before deletion
            max_wait: Maximum seconds to wait if wait_for_deletion is True
            poll_interval: Seconds between checks if wait_for_deletion is True

        Returns:
            Deletion response
        """
        try:
            # If requested, wait for all strategies to become ACTIVE before deletion
            if wait_for_strategies:
                try:
                    memory = self.get_memory(memory_id)
                    strategies = memory.get("strategies", [])

                    # Check if any strategies are in a transitional state
                    transitional_strategies = [
                        s
                        for s in strategies
                        if s.get("status") not in [MemoryStatus.ACTIVE.value, MemoryStatus.FAILED.value]
                    ]

                    if transitional_strategies:
                        logger.info(
                            "Waiting for %d strategies to become ACTIVE before deletion", len(transitional_strategies)
                        )
                        self._wait_for_status(
                            memory_id=memory_id,
                            target_status=MemoryStatus.ACTIVE.value,
                            max_wait=max_wait,
                            poll_interval=poll_interval,
                            check_strategies=True,
                        )
                except Exception as e:
                    logger.warning("Error waiting for strategies to become ACTIVE: %s", e)

            # Now delete the memory
            response = self.client.delete_memory(memoryId=memory_id, clientToken=str(uuid.uuid4()))

            logger.info("Initiated deletion of memory: %s", memory_id)

            if not wait_for_deletion:
                return response

            # Wait for deletion to complete
            start_time = time.time()
            while time.time() - start_time < max_wait:
                try:
                    self.client.get_memory(memoryId=memory_id)
                    time.sleep(poll_interval)
                except ClientError as e:
                    if e.response["Error"]["Code"] == "ResourceNotFoundException":
                        logger.info("Memory %s successfully deleted", memory_id)
                        return response
                    raise

            raise TimeoutError(f"Memory {memory_id} was not deleted within {max_wait} seconds")

        except ClientError as e:
            logger.error("Failed to delete memory: %s", e)
            raise

    # ==================== STRATEGY OPERATIONS ====================

    def add_strategy(
        self,
        memory_id: str,
        strategy: Dict[str, Any],
        wait_for_active: bool = False,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Add a strategy to a memory resource.

        Args:
            memory_id: Memory resource ID
            strategy: Strategy configuration dictionary
            wait_for_active: Whether to wait for strategy to become ACTIVE
            max_wait: Maximum seconds to wait if wait_for_active is True
            poll_interval: Seconds between status checks if wait_for_active is True

        Returns:
            Updated memory object with strategyId field
        """
        # Get the strategy type and name for identification
        strategy_type = list(strategy.keys())[0]  # e.g., 'semanticMemoryStrategy'
        strategy_name = strategy[strategy_type].get("name")

        logger.info("Adding strategy %s of type %s to memory %s", strategy_name, strategy_type, memory_id)

        # Use update_memory with add_strategies parameter but don't wait for memory
        memory = self.update_memory(
            memory_id=memory_id,
            add_strategies=[strategy],
            wait_for_active=False,  # Don't wait for memory, we'll check strategy specifically
        )

        # If we need to wait for the strategy to become active
        if wait_for_active:
            # First, get the memory again to ensure we have the latest state
            memory = self.get_memory(memory_id)

            # Find the newly added strategy by matching name
            strategies = memory.get("strategies", [])
            strategy_id = None

            for s in strategies:
                # Match by name since that's unique within a memory
                if s.get("name") == strategy_name:
                    strategy_id = s.get("strategyId")
                    logger.info("Found newly added strategy %s with ID %s", strategy_name, strategy_id)
                    break

            if strategy_id:
                return self._wait_for_strategy_active(memory_id, strategy_id, max_wait, poll_interval)
            else:
                logger.warning("Could not identify newly added strategy %s to wait for activation", strategy_name)

        return memory

    def get_strategy(self, memory_id: str, strategy_id: str) -> Dict[str, Any]:
        """Get a specific strategy from a memory resource.

        Args:
            memory_id: Memory resource ID
            strategy_id: Strategy ID

        Returns:
            Strategy details
        """
        try:
            memory = self.get_memory(memory_id)
            strategies = memory.get("strategies", [])

            for strategy in strategies:
                if strategy.get("strategyId") == strategy_id:
                    return strategy

            raise ValueError(f"Strategy {strategy_id} not found in memory {memory_id}")

        except ClientError as e:
            logger.error("Failed to get strategy: %s", e)
            raise

    def update_strategy(
        self,
        memory_id: str,
        strategy_id: str,
        description: Optional[str] = None,
        namespaces: Optional[List[str]] = None,
        configuration: Optional[Dict[str, Any]] = None,
        wait_for_active: bool = False,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Update a strategy in a memory resource.

        Args:
            memory_id: Memory resource ID
            strategy_id: Strategy ID to update
            description: Optional new description
            namespaces: Optional new namespaces list
            configuration: Optional new configuration
            wait_for_active: Whether to wait for strategy to become ACTIVE
            max_wait: Maximum seconds to wait if wait_for_active is True
            poll_interval: Seconds between status checks if wait_for_active is True

        Returns:
            Updated memory object
        """
        # Note: API expects memoryStrategyId for input but returns strategyId in response
        modify_config: Dict = {"memoryStrategyId": strategy_id}

        if description is not None:
            modify_config["description"] = description

        if namespaces is not None:
            modify_config["namespaces"] = namespaces

        if configuration is not None:
            modify_config["configuration"] = configuration

        # Use update_memory with modify_strategies parameter but don't wait for memory
        memory = self.update_memory(
            memory_id=memory_id,
            modify_strategies=[modify_config],
            wait_for_active=False,  # Don't wait for memory, we'll check strategy specifically
        )

        # If we need to wait for the strategy to become active
        if wait_for_active:
            return self._wait_for_strategy_active(memory_id, strategy_id, max_wait, poll_interval)

        return memory

    def remove_strategy(
        self,
        memory_id: str,
        strategy_id: str,
        wait_for_active: bool = False,
        max_wait: int = 300,
        poll_interval: int = 10,
    ) -> Dict[str, Any]:
        """Remove a strategy from a memory resource.

        Args:
            memory_id: Memory resource ID
            strategy_id: Strategy ID to remove
            wait_for_active: Whether to wait for memory to become ACTIVE
            max_wait: Maximum seconds to wait if wait_for_active is True
            poll_interval: Seconds between status checks if wait_for_active is True

        Returns:
            Updated memory object
        """
        # For remove_strategy, we only need to wait for memory to be active
        # since the strategy will be gone
        return self.update_memory(
            memory_id=memory_id,
            delete_strategy_ids=[strategy_id],
            wait_for_active=wait_for_active,
            max_wait=max_wait,
            poll_interval=poll_interval,
        )

    # ==================== HELPER METHODS ====================

    def _wait_for_memory_active(self, memory_id: str, max_wait: int, poll_interval: int) -> Dict[str, Any]:
        """Wait for memory to return to ACTIVE state."""
        logger.info("Waiting for memory %s to become ACTIVE...", memory_id)
        return self._wait_for_status(
            memory_id=memory_id, target_status=MemoryStatus.ACTIVE.value, max_wait=max_wait, poll_interval=poll_interval
        )

    def _wait_for_strategy_active(
        self, memory_id: str, strategy_id: str, max_wait: int, poll_interval: int
    ) -> Dict[str, Any]:
        """Wait for specific memory strategy to become ACTIVE."""
        logger.info("Waiting for strategy %s to become ACTIVE (max wait: %d seconds)...", strategy_id, max_wait)

        start_time = time.time()
        last_status = None

        while time.time() - start_time < max_wait:
            try:
                memory = self.get_memory(memory_id)
                strategies = memory.get("strategies", [])

                for strategy in strategies:
                    if strategy.get("strategyId") == strategy_id:
                        status = strategy["status"]

                        # Log status changes
                        if status != last_status:
                            logger.info("Strategy %s status: %s", strategy_id, status)
                            last_status = status

                        if status == MemoryStatus.ACTIVE.value:
                            elapsed = time.time() - start_time
                            logger.info("Strategy %s is now ACTIVE (took %.1f seconds)", strategy_id, elapsed)
                            return memory
                        elif status == MemoryStatus.FAILED.value:
                            failure_reason = strategy.get("failureReason", "Unknown")
                            raise RuntimeError(f"Strategy {strategy_id} failed to activate: {failure_reason}")

                        break
                else:
                    logger.warning("Strategy %s not found in memory %s", strategy_id, memory_id)

                # Wait before checking again
                time.sleep(poll_interval)

            except ClientError as e:
                logger.error("Error checking strategy status: %s", e)
                raise

        elapsed = time.time() - start_time
        raise TimeoutError(
            f"Strategy {strategy_id} did not become ACTIVE within {max_wait} seconds (last status: {last_status})"
        )

    def _wait_for_status(
        self, memory_id: str, target_status: str, max_wait: int, poll_interval: int, check_strategies: bool = True
    ) -> Dict[str, Any]:
        """Generic method to wait for a memory to reach a specific status.

        Args:
            memory_id: The ID of the memory to check
            target_status: The status to wait for (e.g., "ACTIVE")
            max_wait: Maximum time to wait in seconds
            poll_interval: Time between status checks in seconds
            check_strategies: Whether to also check that all strategies are in the target status

        Returns:
            The memory object once it reaches the target status

        Raises:
            TimeoutError: If the memory doesn't reach the target status within max_wait
            RuntimeError: If the memory or any strategy reaches a FAILED state
        """
        logger.info("Waiting for memory %s to reach status %s...", memory_id, target_status)

        start_time = time.time()
        last_memory_status = None
        strategy_statuses = {}

        while time.time() - start_time < max_wait:
            try:
                memory = self.get_memory(memory_id)
                status = memory.get("status")

                # Log status changes for memory
                if status != last_memory_status:
                    logger.info("Memory %s status: %s", memory_id, status)
                    last_memory_status = status

                if status == target_status:
                    # Check if all strategies are also in the target status
                    if check_strategies and target_status == MemoryStatus.ACTIVE.value:
                        strategies = memory.get("strategies", [])
                        all_strategies_active = True

                        for strategy in strategies:
                            strategy_id = strategy.get("strategyId")
                            strategy_status = strategy.get("status")

                            # Log strategy status changes
                            if (
                                strategy_id not in strategy_statuses
                                or strategy_statuses[strategy_id] != strategy_status
                            ):
                                logger.info("Strategy %s status: %s", strategy_id, strategy_status)
                                strategy_statuses[strategy_id] = strategy_status

                            if strategy_status != target_status:
                                if strategy_status == MemoryStatus.FAILED.value:
                                    failure_reason = strategy.get("failureReason", "Unknown")
                                    raise RuntimeError(f"Strategy {strategy_id} failed: {failure_reason}")

                                all_strategies_active = False

                        if not all_strategies_active:
                            logger.info(
                                "Memory %s is %s but %d strategies are still processing",
                                memory_id,
                                target_status,
                                len([s for s in strategies if s.get("status") != target_status]),
                            )
                            time.sleep(poll_interval)
                            continue

                    elapsed = time.time() - start_time
                    logger.info(
                        "Memory %s and all strategies are now %s (took %.1f seconds)", memory_id, target_status, elapsed
                    )
                    return memory
                elif status == MemoryStatus.FAILED.value:
                    failure_reason = memory.get("failureReason", "Unknown")
                    raise RuntimeError(f"Memory operation failed: {failure_reason}")

                time.sleep(poll_interval)

            except ClientError as e:
                logger.error("Error checking memory status: %s", e)
                raise

        elapsed = time.time() - start_time
        raise TimeoutError(
            f"Memory {memory_id} did not reach status {target_status} within {max_wait} seconds "
            f"(elapsed: {elapsed:.1f}s)"
        )
```

#### `__init__(region_name='us-west-2', environment='prod')`

Initialize the Memory Control Plane client.

Parameters:

| Name          | Type  | Description                          | Default       |
| ------------- | ----- | ------------------------------------ | ------------- |
| `region_name` | `str` | AWS region name                      | `'us-west-2'` |
| `environment` | `str` | Environment name (prod, gamma, etc.) | `'prod'`      |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def __init__(self, region_name: str = "us-west-2", environment: str = "prod"):
    """Initialize the Memory Control Plane client.

    Args:
        region_name: AWS region name
        environment: Environment name (prod, gamma, etc.)
    """
    self.region_name = region_name
    self.environment = environment

    self.endpoint = os.getenv(
        "BEDROCK_AGENTCORE_CONTROL_ENDPOINT", f"https://bedrock-agentcore-control.{region_name}.amazonaws.com"
    )

    service_name = os.getenv("BEDROCK_AGENTCORE_CONTROL_SERVICE", "bedrock-agentcore-control")
    self.client = boto3.client(service_name, region_name=self.region_name, endpoint_url=self.endpoint)

    logger.info("Initialized MemoryControlPlaneClient for %s in %s", environment, region_name)
```

#### `add_strategy(memory_id, strategy, wait_for_active=False, max_wait=300, poll_interval=10)`

Add a strategy to a memory resource.

Parameters:

| Name              | Type             | Description                                              | Default    |
| ----------------- | ---------------- | -------------------------------------------------------- | ---------- |
| `memory_id`       | `str`            | Memory resource ID                                       | *required* |
| `strategy`        | `Dict[str, Any]` | Strategy configuration dictionary                        | *required* |
| `wait_for_active` | `bool`           | Whether to wait for strategy to become ACTIVE            | `False`    |
| `max_wait`        | `int`            | Maximum seconds to wait if wait_for_active is True       | `300`      |
| `poll_interval`   | `int`            | Seconds between status checks if wait_for_active is True | `10`       |

Returns:

| Type             | Description                                 |
| ---------------- | ------------------------------------------- |
| `Dict[str, Any]` | Updated memory object with strategyId field |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def add_strategy(
    self,
    memory_id: str,
    strategy: Dict[str, Any],
    wait_for_active: bool = False,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Add a strategy to a memory resource.

    Args:
        memory_id: Memory resource ID
        strategy: Strategy configuration dictionary
        wait_for_active: Whether to wait for strategy to become ACTIVE
        max_wait: Maximum seconds to wait if wait_for_active is True
        poll_interval: Seconds between status checks if wait_for_active is True

    Returns:
        Updated memory object with strategyId field
    """
    # Get the strategy type and name for identification
    strategy_type = list(strategy.keys())[0]  # e.g., 'semanticMemoryStrategy'
    strategy_name = strategy[strategy_type].get("name")

    logger.info("Adding strategy %s of type %s to memory %s", strategy_name, strategy_type, memory_id)

    # Use update_memory with add_strategies parameter but don't wait for memory
    memory = self.update_memory(
        memory_id=memory_id,
        add_strategies=[strategy],
        wait_for_active=False,  # Don't wait for memory, we'll check strategy specifically
    )

    # If we need to wait for the strategy to become active
    if wait_for_active:
        # First, get the memory again to ensure we have the latest state
        memory = self.get_memory(memory_id)

        # Find the newly added strategy by matching name
        strategies = memory.get("strategies", [])
        strategy_id = None

        for s in strategies:
            # Match by name since that's unique within a memory
            if s.get("name") == strategy_name:
                strategy_id = s.get("strategyId")
                logger.info("Found newly added strategy %s with ID %s", strategy_name, strategy_id)
                break

        if strategy_id:
            return self._wait_for_strategy_active(memory_id, strategy_id, max_wait, poll_interval)
        else:
            logger.warning("Could not identify newly added strategy %s to wait for activation", strategy_name)

    return memory
```

#### `create_memory(name, event_expiry_days=90, description=None, memory_execution_role_arn=None, strategies=None, wait_for_active=False, max_wait=300, poll_interval=10)`

Create a memory resource with optional strategies.

Parameters:

| Name                        | Type                             | Description                                              | Default    |
| --------------------------- | -------------------------------- | -------------------------------------------------------- | ---------- |
| `name`                      | `str`                            | Name for the memory resource                             | *required* |
| `event_expiry_days`         | `int`                            | How long to retain events (default: 90 days)             | `90`       |
| `description`               | `Optional[str]`                  | Optional description                                     | `None`     |
| `memory_execution_role_arn` | `Optional[str]`                  | IAM role ARN for memory execution                        | `None`     |
| `strategies`                | `Optional[List[Dict[str, Any]]]` | Optional list of strategy configurations                 | `None`     |
| `wait_for_active`           | `bool`                           | Whether to wait for memory to become ACTIVE              | `False`    |
| `max_wait`                  | `int`                            | Maximum seconds to wait if wait_for_active is True       | `300`      |
| `poll_interval`             | `int`                            | Seconds between status checks if wait_for_active is True | `10`       |

Returns:

| Type             | Description           |
| ---------------- | --------------------- |
| `Dict[str, Any]` | Created memory object |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def create_memory(
    self,
    name: str,
    event_expiry_days: int = 90,
    description: Optional[str] = None,
    memory_execution_role_arn: Optional[str] = None,
    strategies: Optional[List[Dict[str, Any]]] = None,
    wait_for_active: bool = False,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Create a memory resource with optional strategies.

    Args:
        name: Name for the memory resource
        event_expiry_days: How long to retain events (default: 90 days)
        description: Optional description
        memory_execution_role_arn: IAM role ARN for memory execution
        strategies: Optional list of strategy configurations
        wait_for_active: Whether to wait for memory to become ACTIVE
        max_wait: Maximum seconds to wait if wait_for_active is True
        poll_interval: Seconds between status checks if wait_for_active is True

    Returns:
        Created memory object
    """
    params = {
        "name": name,
        "eventExpiryDuration": event_expiry_days,
        "clientToken": str(uuid.uuid4()),
    }

    if description:
        params["description"] = description

    if memory_execution_role_arn:
        params["memoryExecutionRoleArn"] = memory_execution_role_arn

    if strategies:
        params["memoryStrategies"] = strategies

    try:
        response = self.client.create_memory(**params)
        memory = response["memory"]
        memory_id = memory["id"]

        logger.info("Created memory: %s", memory_id)

        if wait_for_active:
            return self._wait_for_memory_active(memory_id, max_wait, poll_interval)

        return memory

    except ClientError as e:
        logger.error("Failed to create memory: %s", e)
        raise
```

#### `delete_memory(memory_id, wait_for_deletion=False, wait_for_strategies=False, max_wait=300, poll_interval=10)`

Delete a memory resource.

Parameters:

| Name                  | Type   | Description                                                     | Default    |
| --------------------- | ------ | --------------------------------------------------------------- | ---------- |
| `memory_id`           | `str`  | Memory resource ID to delete                                    | *required* |
| `wait_for_deletion`   | `bool` | Whether to wait for complete deletion                           | `False`    |
| `wait_for_strategies` | `bool` | Whether to wait for strategies to become ACTIVE before deletion | `False`    |
| `max_wait`            | `int`  | Maximum seconds to wait if wait_for_deletion is True            | `300`      |
| `poll_interval`       | `int`  | Seconds between checks if wait_for_deletion is True             | `10`       |

Returns:

| Type             | Description       |
| ---------------- | ----------------- |
| `Dict[str, Any]` | Deletion response |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def delete_memory(
    self,
    memory_id: str,
    wait_for_deletion: bool = False,
    wait_for_strategies: bool = False,  # Changed default to False
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Delete a memory resource.

    Args:
        memory_id: Memory resource ID to delete
        wait_for_deletion: Whether to wait for complete deletion
        wait_for_strategies: Whether to wait for strategies to become ACTIVE before deletion
        max_wait: Maximum seconds to wait if wait_for_deletion is True
        poll_interval: Seconds between checks if wait_for_deletion is True

    Returns:
        Deletion response
    """
    try:
        # If requested, wait for all strategies to become ACTIVE before deletion
        if wait_for_strategies:
            try:
                memory = self.get_memory(memory_id)
                strategies = memory.get("strategies", [])

                # Check if any strategies are in a transitional state
                transitional_strategies = [
                    s
                    for s in strategies
                    if s.get("status") not in [MemoryStatus.ACTIVE.value, MemoryStatus.FAILED.value]
                ]

                if transitional_strategies:
                    logger.info(
                        "Waiting for %d strategies to become ACTIVE before deletion", len(transitional_strategies)
                    )
                    self._wait_for_status(
                        memory_id=memory_id,
                        target_status=MemoryStatus.ACTIVE.value,
                        max_wait=max_wait,
                        poll_interval=poll_interval,
                        check_strategies=True,
                    )
            except Exception as e:
                logger.warning("Error waiting for strategies to become ACTIVE: %s", e)

        # Now delete the memory
        response = self.client.delete_memory(memoryId=memory_id, clientToken=str(uuid.uuid4()))

        logger.info("Initiated deletion of memory: %s", memory_id)

        if not wait_for_deletion:
            return response

        # Wait for deletion to complete
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                self.client.get_memory(memoryId=memory_id)
                time.sleep(poll_interval)
            except ClientError as e:
                if e.response["Error"]["Code"] == "ResourceNotFoundException":
                    logger.info("Memory %s successfully deleted", memory_id)
                    return response
                raise

        raise TimeoutError(f"Memory {memory_id} was not deleted within {max_wait} seconds")

    except ClientError as e:
        logger.error("Failed to delete memory: %s", e)
        raise
```

#### `get_memory(memory_id, include_strategies=True)`

Get a memory resource by ID.

Parameters:

| Name                 | Type   | Description                                     | Default    |
| -------------------- | ------ | ----------------------------------------------- | ---------- |
| `memory_id`          | `str`  | Memory resource ID                              | *required* |
| `include_strategies` | `bool` | Whether to include strategy details in response | `True`     |

Returns:

| Type             | Description             |
| ---------------- | ----------------------- |
| `Dict[str, Any]` | Memory resource details |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def get_memory(self, memory_id: str, include_strategies: bool = True) -> Dict[str, Any]:
    """Get a memory resource by ID.

    Args:
        memory_id: Memory resource ID
        include_strategies: Whether to include strategy details in response

    Returns:
        Memory resource details
    """
    try:
        response = self.client.get_memory(memoryId=memory_id)
        memory = response["memory"]

        # Add strategy count
        strategies = memory.get("strategies", [])
        memory["strategyCount"] = len(strategies)

        # Remove strategies if not requested
        if not include_strategies and "strategies" in memory:
            del memory["strategies"]

        return memory

    except ClientError as e:
        logger.error("Failed to get memory: %s", e)
        raise
```

#### `get_strategy(memory_id, strategy_id)`

Get a specific strategy from a memory resource.

Parameters:

| Name          | Type  | Description        | Default    |
| ------------- | ----- | ------------------ | ---------- |
| `memory_id`   | `str` | Memory resource ID | *required* |
| `strategy_id` | `str` | Strategy ID        | *required* |

Returns:

| Type             | Description      |
| ---------------- | ---------------- |
| `Dict[str, Any]` | Strategy details |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def get_strategy(self, memory_id: str, strategy_id: str) -> Dict[str, Any]:
    """Get a specific strategy from a memory resource.

    Args:
        memory_id: Memory resource ID
        strategy_id: Strategy ID

    Returns:
        Strategy details
    """
    try:
        memory = self.get_memory(memory_id)
        strategies = memory.get("strategies", [])

        for strategy in strategies:
            if strategy.get("strategyId") == strategy_id:
                return strategy

        raise ValueError(f"Strategy {strategy_id} not found in memory {memory_id}")

    except ClientError as e:
        logger.error("Failed to get strategy: %s", e)
        raise
```

#### `list_memories(max_results=100)`

List all memories for the account with pagination support.

Parameters:

| Name          | Type  | Description                          | Default |
| ------------- | ----- | ------------------------------------ | ------- |
| `max_results` | `int` | Maximum number of memories to return | `100`   |

Returns:

| Type                   | Description              |
| ---------------------- | ------------------------ |
| `List[Dict[str, Any]]` | List of memory summaries |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def list_memories(self, max_results: int = 100) -> List[Dict[str, Any]]:
    """List all memories for the account with pagination support.

    Args:
        max_results: Maximum number of memories to return

    Returns:
        List of memory summaries
    """
    try:
        memories = []
        next_token = None

        while len(memories) < max_results:
            params = {"maxResults": min(100, max_results - len(memories))}
            if next_token:
                params["nextToken"] = next_token

            response = self.client.list_memories(**params)
            batch = response.get("memories", [])
            memories.extend(batch)

            next_token = response.get("nextToken")
            if not next_token or len(memories) >= max_results:
                break

        # Add strategy count to each memory summary
        for memory in memories:
            memory["strategyCount"] = 0  # List memories doesn't include strategies

        return memories[:max_results]

    except ClientError as e:
        logger.error("Failed to list memories: %s", e)
        raise
```

#### `remove_strategy(memory_id, strategy_id, wait_for_active=False, max_wait=300, poll_interval=10)`

Remove a strategy from a memory resource.

Parameters:

| Name              | Type   | Description                                              | Default    |
| ----------------- | ------ | -------------------------------------------------------- | ---------- |
| `memory_id`       | `str`  | Memory resource ID                                       | *required* |
| `strategy_id`     | `str`  | Strategy ID to remove                                    | *required* |
| `wait_for_active` | `bool` | Whether to wait for memory to become ACTIVE              | `False`    |
| `max_wait`        | `int`  | Maximum seconds to wait if wait_for_active is True       | `300`      |
| `poll_interval`   | `int`  | Seconds between status checks if wait_for_active is True | `10`       |

Returns:

| Type             | Description           |
| ---------------- | --------------------- |
| `Dict[str, Any]` | Updated memory object |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def remove_strategy(
    self,
    memory_id: str,
    strategy_id: str,
    wait_for_active: bool = False,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Remove a strategy from a memory resource.

    Args:
        memory_id: Memory resource ID
        strategy_id: Strategy ID to remove
        wait_for_active: Whether to wait for memory to become ACTIVE
        max_wait: Maximum seconds to wait if wait_for_active is True
        poll_interval: Seconds between status checks if wait_for_active is True

    Returns:
        Updated memory object
    """
    # For remove_strategy, we only need to wait for memory to be active
    # since the strategy will be gone
    return self.update_memory(
        memory_id=memory_id,
        delete_strategy_ids=[strategy_id],
        wait_for_active=wait_for_active,
        max_wait=max_wait,
        poll_interval=poll_interval,
    )
```

#### `update_memory(memory_id, description=None, event_expiry_days=None, memory_execution_role_arn=None, add_strategies=None, modify_strategies=None, delete_strategy_ids=None, wait_for_active=False, max_wait=300, poll_interval=10)`

Update a memory resource properties and/or strategies.

Parameters:

| Name                        | Type                             | Description                                              | Default    |
| --------------------------- | -------------------------------- | -------------------------------------------------------- | ---------- |
| `memory_id`                 | `str`                            | Memory resource ID                                       | *required* |
| `description`               | `Optional[str]`                  | Optional new description                                 | `None`     |
| `event_expiry_days`         | `Optional[int]`                  | Optional new event expiry duration                       | `None`     |
| `memory_execution_role_arn` | `Optional[str]`                  | Optional new execution role ARN                          | `None`     |
| `add_strategies`            | `Optional[List[Dict[str, Any]]]` | Optional list of strategies to add                       | `None`     |
| `modify_strategies`         | `Optional[List[Dict[str, Any]]]` | Optional list of strategies to modify                    | `None`     |
| `delete_strategy_ids`       | `Optional[List[str]]`            | Optional list of strategy IDs to delete                  | `None`     |
| `wait_for_active`           | `bool`                           | Whether to wait for memory to become ACTIVE              | `False`    |
| `max_wait`                  | `int`                            | Maximum seconds to wait if wait_for_active is True       | `300`      |
| `poll_interval`             | `int`                            | Seconds between status checks if wait_for_active is True | `10`       |

Returns:

| Type             | Description           |
| ---------------- | --------------------- |
| `Dict[str, Any]` | Updated memory object |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def update_memory(
    self,
    memory_id: str,
    description: Optional[str] = None,
    event_expiry_days: Optional[int] = None,
    memory_execution_role_arn: Optional[str] = None,
    add_strategies: Optional[List[Dict[str, Any]]] = None,
    modify_strategies: Optional[List[Dict[str, Any]]] = None,
    delete_strategy_ids: Optional[List[str]] = None,
    wait_for_active: bool = False,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Update a memory resource properties and/or strategies.

    Args:
        memory_id: Memory resource ID
        description: Optional new description
        event_expiry_days: Optional new event expiry duration
        memory_execution_role_arn: Optional new execution role ARN
        add_strategies: Optional list of strategies to add
        modify_strategies: Optional list of strategies to modify
        delete_strategy_ids: Optional list of strategy IDs to delete
        wait_for_active: Whether to wait for memory to become ACTIVE
        max_wait: Maximum seconds to wait if wait_for_active is True
        poll_interval: Seconds between status checks if wait_for_active is True

    Returns:
        Updated memory object
    """
    params: Dict = {
        "memoryId": memory_id,
        "clientToken": str(uuid.uuid4()),
    }

    # Add memory properties if provided
    if description is not None:
        params["description"] = description

    if event_expiry_days is not None:
        params["eventExpiryDuration"] = event_expiry_days

    if memory_execution_role_arn is not None:
        params["memoryExecutionRoleArn"] = memory_execution_role_arn

    # Add strategy operations if provided
    memory_strategies = {}

    if add_strategies:
        memory_strategies["addMemoryStrategies"] = add_strategies

    if modify_strategies:
        memory_strategies["modifyMemoryStrategies"] = modify_strategies

    if delete_strategy_ids:
        memory_strategies["deleteMemoryStrategies"] = [
            {"memoryStrategyId": strategy_id} for strategy_id in delete_strategy_ids
        ]

    if memory_strategies:
        params["memoryStrategies"] = memory_strategies

    try:
        response = self.client.update_memory(**params)
        memory = response["memory"]
        logger.info("Updated memory: %s", memory_id)

        if wait_for_active:
            return self._wait_for_memory_active(memory_id, max_wait, poll_interval)

        return memory

    except ClientError as e:
        logger.error("Failed to update memory: %s", e)
        raise
```

#### `update_strategy(memory_id, strategy_id, description=None, namespaces=None, configuration=None, wait_for_active=False, max_wait=300, poll_interval=10)`

Update a strategy in a memory resource.

Parameters:

| Name              | Type                       | Description                                              | Default    |
| ----------------- | -------------------------- | -------------------------------------------------------- | ---------- |
| `memory_id`       | `str`                      | Memory resource ID                                       | *required* |
| `strategy_id`     | `str`                      | Strategy ID to update                                    | *required* |
| `description`     | `Optional[str]`            | Optional new description                                 | `None`     |
| `namespaces`      | `Optional[List[str]]`      | Optional new namespaces list                             | `None`     |
| `configuration`   | `Optional[Dict[str, Any]]` | Optional new configuration                               | `None`     |
| `wait_for_active` | `bool`                     | Whether to wait for strategy to become ACTIVE            | `False`    |
| `max_wait`        | `int`                      | Maximum seconds to wait if wait_for_active is True       | `300`      |
| `poll_interval`   | `int`                      | Seconds between status checks if wait_for_active is True | `10`       |

Returns:

| Type             | Description           |
| ---------------- | --------------------- |
| `Dict[str, Any]` | Updated memory object |

Source code in `bedrock_agentcore/memory/controlplane.py`

```
def update_strategy(
    self,
    memory_id: str,
    strategy_id: str,
    description: Optional[str] = None,
    namespaces: Optional[List[str]] = None,
    configuration: Optional[Dict[str, Any]] = None,
    wait_for_active: bool = False,
    max_wait: int = 300,
    poll_interval: int = 10,
) -> Dict[str, Any]:
    """Update a strategy in a memory resource.

    Args:
        memory_id: Memory resource ID
        strategy_id: Strategy ID to update
        description: Optional new description
        namespaces: Optional new namespaces list
        configuration: Optional new configuration
        wait_for_active: Whether to wait for strategy to become ACTIVE
        max_wait: Maximum seconds to wait if wait_for_active is True
        poll_interval: Seconds between status checks if wait_for_active is True

    Returns:
        Updated memory object
    """
    # Note: API expects memoryStrategyId for input but returns strategyId in response
    modify_config: Dict = {"memoryStrategyId": strategy_id}

    if description is not None:
        modify_config["description"] = description

    if namespaces is not None:
        modify_config["namespaces"] = namespaces

    if configuration is not None:
        modify_config["configuration"] = configuration

    # Use update_memory with modify_strategies parameter but don't wait for memory
    memory = self.update_memory(
        memory_id=memory_id,
        modify_strategies=[modify_config],
        wait_for_active=False,  # Don't wait for memory, we'll check strategy specifically
    )

    # If we need to wait for the strategy to become active
    if wait_for_active:
        return self._wait_for_strategy_active(memory_id, strategy_id, max_wait, poll_interval)

    return memory
```

### `MemorySession`

Bases: `DictWrapper`

Represents a single, AgentCore MemorySession resource.

This class provides convenient delegation to MemorySessionManager operations.

Source code in `bedrock_agentcore/memory/session.py`

```
class MemorySession(DictWrapper):
    """Represents a single, AgentCore MemorySession resource.

    This class provides convenient delegation to MemorySessionManager operations.
    """

    def __init__(self, memory_id: str, actor_id: str, session_id: str, manager: MemorySessionManager):
        """Initialize a MemorySession instance.

        Args:
            memory_id: The memory identifier for this session.
            actor_id: The actor identifier for this session.
            session_id: The session identifier.
            manager: The MemorySessionManager instance to delegate operations to.
        """
        self._memory_id = memory_id
        self._actor_id = actor_id
        self._session_id = session_id
        self._manager = manager
        super().__init__(self._construct_session_dict())

    def _construct_session_dict(self) -> Dict[str, Any]:
        """Constructs a dictionary representing the session."""
        return {"memoryId": self._memory_id, "actorId": self._actor_id, "sessionId": self._session_id}

    def add_turns(
        self,
        messages: List[Union[ConversationalMessage, BlobMessage]],
        branch: Optional[Dict[str, str]] = None,
        event_timestamp: Optional[datetime] = None,
    ) -> Event:
        """Delegates to manager.add_turns."""
        return self._manager.add_turns(self._actor_id, self._session_id, messages, branch, event_timestamp)

    def fork_conversation(
        self,
        messages: List[Union[ConversationalMessage, BlobMessage]],
        root_event_id: str,
        branch_name: str,
        event_timestamp: Optional[datetime] = None,
    ) -> Event:
        """Delegates to manager.fork_conversation."""
        return self._manager.fork_conversation(
            self._actor_id, self._session_id, root_event_id, branch_name, messages, event_timestamp
        )

    def process_turn_with_llm(
        self,
        user_input: str,
        llm_callback: Callable[[str, List[Dict[str, Any]]], str],
        retrieval_config: Optional[Dict[str, RetrievalConfig]],
        event_timestamp: Optional[datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        """Delegates to manager.process_turn_with_llm."""
        return self._manager.process_turn_with_llm(
            self._actor_id,
            self._session_id,
            user_input,
            llm_callback,
            retrieval_config,
            event_timestamp,
        )

    def get_last_k_turns(
        self,
        k: int = 5,
        branch_name: Optional[str] = None,
        include_parent_branches: Optional[bool] = None,
        max_results: int = 100,
    ) -> List[List[EventMessage]]:
        """Delegates to manager.get_last_k_turns."""
        return self._manager.get_last_k_turns(
            self._actor_id, self._session_id, k, branch_name, include_parent_branches, max_results
        )

    def get_event(self, event_id: str) -> Event:
        """Delegates to manager.get_event."""
        return self._manager.get_event(self._actor_id, self._session_id, event_id)

    def delete_event(self, event_id: str):
        """Delegates to manager.delete_event."""
        return self._manager.delete_event(self._actor_id, self._session_id, event_id)

    def get_memory_record(self, record_id: str) -> MemoryRecord:
        """Delegates to manager.get_memory_record."""
        return self._manager.get_memory_record(record_id)

    def delete_memory_record(self, record_id: str):
        """Delegates to manager.delete_memory_record."""
        return self._manager.delete_memory_record(record_id)

    def search_long_term_memories(
        self,
        query: str,
        namespace_prefix: str,
        top_k: int = 3,
        strategy_id: Optional[str] = None,
        max_results: int = 20,
    ) -> List[MemoryRecord]:
        """Delegates to manager.search_long_term_memories."""
        return self._manager.search_long_term_memories(query, namespace_prefix, top_k, strategy_id, max_results)

    def list_long_term_memory_records(
        self, namespace_prefix: str, strategy_id: Optional[str] = None, max_results: int = 10
    ) -> List[MemoryRecord]:
        """Delegates to manager.list_long_term_memory_records."""
        return self._manager.list_long_term_memory_records(namespace_prefix, strategy_id, max_results)

    def list_actors(self) -> List[ActorSummary]:
        """Delegates to manager.list_actors."""
        return self._manager.list_actors()

    def list_events(
        self,
        branch_name: Optional[str] = None,
        include_parent_branches: bool = False,
        max_results: int = 100,
        include_payload: bool = True,
    ) -> List[Event]:
        """Delegates to manager.list_events."""
        return self._manager.list_events(
            actor_id=self._actor_id,
            session_id=self._session_id,
            branch_name=branch_name,
            include_parent_branches=include_parent_branches,
            include_payload=include_payload,
            max_results=max_results,
        )

    def list_branches(self) -> List[Branch]:
        """Delegates to manager.list_branches."""
        return self._manager.list_branches(self._actor_id, self._session_id)

    def get_actor(self) -> "Actor":
        """Returns an Actor instance for this conversation's actor."""
        return Actor(self._actor_id, self._manager)
```

#### `__init__(memory_id, actor_id, session_id, manager)`

Initialize a MemorySession instance.

Parameters:

| Name         | Type                   | Description                                                  | Default    |
| ------------ | ---------------------- | ------------------------------------------------------------ | ---------- |
| `memory_id`  | `str`                  | The memory identifier for this session.                      | *required* |
| `actor_id`   | `str`                  | The actor identifier for this session.                       | *required* |
| `session_id` | `str`                  | The session identifier.                                      | *required* |
| `manager`    | `MemorySessionManager` | The MemorySessionManager instance to delegate operations to. | *required* |

Source code in `bedrock_agentcore/memory/session.py`

```
def __init__(self, memory_id: str, actor_id: str, session_id: str, manager: MemorySessionManager):
    """Initialize a MemorySession instance.

    Args:
        memory_id: The memory identifier for this session.
        actor_id: The actor identifier for this session.
        session_id: The session identifier.
        manager: The MemorySessionManager instance to delegate operations to.
    """
    self._memory_id = memory_id
    self._actor_id = actor_id
    self._session_id = session_id
    self._manager = manager
    super().__init__(self._construct_session_dict())
```

#### `add_turns(messages, branch=None, event_timestamp=None)`

Delegates to manager.add_turns.

Source code in `bedrock_agentcore/memory/session.py`

```
def add_turns(
    self,
    messages: List[Union[ConversationalMessage, BlobMessage]],
    branch: Optional[Dict[str, str]] = None,
    event_timestamp: Optional[datetime] = None,
) -> Event:
    """Delegates to manager.add_turns."""
    return self._manager.add_turns(self._actor_id, self._session_id, messages, branch, event_timestamp)
```

#### `delete_event(event_id)`

Delegates to manager.delete_event.

Source code in `bedrock_agentcore/memory/session.py`

```
def delete_event(self, event_id: str):
    """Delegates to manager.delete_event."""
    return self._manager.delete_event(self._actor_id, self._session_id, event_id)
```

#### `delete_memory_record(record_id)`

Delegates to manager.delete_memory_record.

Source code in `bedrock_agentcore/memory/session.py`

```
def delete_memory_record(self, record_id: str):
    """Delegates to manager.delete_memory_record."""
    return self._manager.delete_memory_record(record_id)
```

#### `fork_conversation(messages, root_event_id, branch_name, event_timestamp=None)`

Delegates to manager.fork_conversation.

Source code in `bedrock_agentcore/memory/session.py`

```
def fork_conversation(
    self,
    messages: List[Union[ConversationalMessage, BlobMessage]],
    root_event_id: str,
    branch_name: str,
    event_timestamp: Optional[datetime] = None,
) -> Event:
    """Delegates to manager.fork_conversation."""
    return self._manager.fork_conversation(
        self._actor_id, self._session_id, root_event_id, branch_name, messages, event_timestamp
    )
```

#### `get_actor()`

Returns an Actor instance for this conversation's actor.

Source code in `bedrock_agentcore/memory/session.py`

```
def get_actor(self) -> "Actor":
    """Returns an Actor instance for this conversation's actor."""
    return Actor(self._actor_id, self._manager)
```

#### `get_event(event_id)`

Delegates to manager.get_event.

Source code in `bedrock_agentcore/memory/session.py`

```
def get_event(self, event_id: str) -> Event:
    """Delegates to manager.get_event."""
    return self._manager.get_event(self._actor_id, self._session_id, event_id)
```

#### `get_last_k_turns(k=5, branch_name=None, include_parent_branches=None, max_results=100)`

Delegates to manager.get_last_k_turns.

Source code in `bedrock_agentcore/memory/session.py`

```
def get_last_k_turns(
    self,
    k: int = 5,
    branch_name: Optional[str] = None,
    include_parent_branches: Optional[bool] = None,
    max_results: int = 100,
) -> List[List[EventMessage]]:
    """Delegates to manager.get_last_k_turns."""
    return self._manager.get_last_k_turns(
        self._actor_id, self._session_id, k, branch_name, include_parent_branches, max_results
    )
```

#### `get_memory_record(record_id)`

Delegates to manager.get_memory_record.

Source code in `bedrock_agentcore/memory/session.py`

```
def get_memory_record(self, record_id: str) -> MemoryRecord:
    """Delegates to manager.get_memory_record."""
    return self._manager.get_memory_record(record_id)
```

#### `list_actors()`

Delegates to manager.list_actors.

Source code in `bedrock_agentcore/memory/session.py`

```
def list_actors(self) -> List[ActorSummary]:
    """Delegates to manager.list_actors."""
    return self._manager.list_actors()
```

#### `list_branches()`

Delegates to manager.list_branches.

Source code in `bedrock_agentcore/memory/session.py`

```
def list_branches(self) -> List[Branch]:
    """Delegates to manager.list_branches."""
    return self._manager.list_branches(self._actor_id, self._session_id)
```

#### `list_events(branch_name=None, include_parent_branches=False, max_results=100, include_payload=True)`

Delegates to manager.list_events.

Source code in `bedrock_agentcore/memory/session.py`

```
def list_events(
    self,
    branch_name: Optional[str] = None,
    include_parent_branches: bool = False,
    max_results: int = 100,
    include_payload: bool = True,
) -> List[Event]:
    """Delegates to manager.list_events."""
    return self._manager.list_events(
        actor_id=self._actor_id,
        session_id=self._session_id,
        branch_name=branch_name,
        include_parent_branches=include_parent_branches,
        include_payload=include_payload,
        max_results=max_results,
    )
```

#### `list_long_term_memory_records(namespace_prefix, strategy_id=None, max_results=10)`

Delegates to manager.list_long_term_memory_records.

Source code in `bedrock_agentcore/memory/session.py`

```
def list_long_term_memory_records(
    self, namespace_prefix: str, strategy_id: Optional[str] = None, max_results: int = 10
) -> List[MemoryRecord]:
    """Delegates to manager.list_long_term_memory_records."""
    return self._manager.list_long_term_memory_records(namespace_prefix, strategy_id, max_results)
```

#### `process_turn_with_llm(user_input, llm_callback, retrieval_config, event_timestamp=None)`

Delegates to manager.process_turn_with_llm.

Source code in `bedrock_agentcore/memory/session.py`

```
def process_turn_with_llm(
    self,
    user_input: str,
    llm_callback: Callable[[str, List[Dict[str, Any]]], str],
    retrieval_config: Optional[Dict[str, RetrievalConfig]],
    event_timestamp: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    """Delegates to manager.process_turn_with_llm."""
    return self._manager.process_turn_with_llm(
        self._actor_id,
        self._session_id,
        user_input,
        llm_callback,
        retrieval_config,
        event_timestamp,
    )
```

#### `search_long_term_memories(query, namespace_prefix, top_k=3, strategy_id=None, max_results=20)`

Delegates to manager.search_long_term_memories.

Source code in `bedrock_agentcore/memory/session.py`

```
def search_long_term_memories(
    self,
    query: str,
    namespace_prefix: str,
    top_k: int = 3,
    strategy_id: Optional[str] = None,
    max_results: int = 20,
) -> List[MemoryRecord]:
    """Delegates to manager.search_long_term_memories."""
    return self._manager.search_long_term_memories(query, namespace_prefix, top_k, strategy_id, max_results)
```

### `MemorySessionManager`

Manages conversational sessions and memory operations for AWS Bedrock AgentCore.

The MemorySessionManager provides a high-level interface for managing conversational AI sessions, handling both short-term (conversational events) and long-term (semantic memory) storage. It serves as the primary entry point for data plane operations with AWS Bedrock AgentCore Memory services.

Key Capabilities

- **Conversation Management**: Store, retrieve, and organize conversational turns
- **Memory Operations**: Search and manage long-term semantic memory records
- **Branch Support**: Create and manage conversation branches for alternative flows
- **LLM Integration**: Built-in callback pattern for LLM processing with memory context
- **Actor & Session Tracking**: Multi-user, multi-session conversation management

Usage Patterns

1. **Simple Conversation**: Store user/assistant message pairs
1. **Memory-Enhanced Chat**: Retrieve relevant context before LLM processing
1. **Branched Conversations**: Fork conversations for alternative responses
1. **Multi-Modal**: Handle both text and binary data (images, files, etc.)

Example

```
# Initialize manager
manager = MemorySessionManager(memory_id="my-memory-123", region_name="us-east-1")

# Store a conversation turn
manager.add_turns(
    actor_id="user-456",
    session_id="session-789",
    messages=[
        ConversationalMessage("Hello!", MessageRole.USER),
        ConversationalMessage("Hi there!", MessageRole.ASSISTANT)
    ]
)

# Search long-term memory and process with LLM
def my_llm(user_input: str, memories: List[Dict]) -> str:
    # Your LLM processing logic here
    return "Response based on context"

memories, response, event = manager.process_turn_with_llm(
    actor_id="user-456",
    session_id="session-789",
    user_input="What did we discuss?",
    llm_callback=my_llm,
    retrieval_namespace="support/facts/{sessionId}"
)
```

Thread Safety

This class is not thread-safe. Create separate instances for concurrent operations.

AWS Permissions Required

- bedrock-agentcore:CreateEvent
- bedrock-agentcore:GetEvent
- bedrock-agentcore:ListEvents
- bedrock-agentcore:DeleteEvent
- bedrock-agentcore:RetrieveMemoryRecords
- bedrock-agentcore:ListMemoryRecords
- bedrock-agentcore:GetMemoryRecord
- bedrock-agentcore:DeleteMemoryRecord
- bedrock-agentcore:ListActors
- bedrock-agentcore:ListSessions

Source code in `bedrock_agentcore/memory/session.py`

````
class MemorySessionManager:
    """Manages conversational sessions and memory operations for AWS Bedrock AgentCore.

    The MemorySessionManager provides a high-level interface for managing conversational AI sessions,
    handling both short-term (conversational events) and long-term (semantic memory) storage.
    It serves as the primary entry point for data plane operations with AWS Bedrock AgentCore
    Memory services.

    Key Capabilities:
        - **Conversation Management**: Store, retrieve, and organize conversational turns
        - **Memory Operations**: Search and manage long-term semantic memory records
        - **Branch Support**: Create and manage conversation branches for alternative flows
        - **LLM Integration**: Built-in callback pattern for LLM processing with memory context
        - **Actor & Session Tracking**: Multi-user, multi-session conversation management

    Usage Patterns:
        1. **Simple Conversation**: Store user/assistant message pairs
        2. **Memory-Enhanced Chat**: Retrieve relevant context before LLM processing
        3. **Branched Conversations**: Fork conversations for alternative responses
        4. **Multi-Modal**: Handle both text and binary data (images, files, etc.)

    Example:
        ```python
        # Initialize manager
        manager = MemorySessionManager(memory_id="my-memory-123", region_name="us-east-1")

        # Store a conversation turn
        manager.add_turns(
            actor_id="user-456",
            session_id="session-789",
            messages=[
                ConversationalMessage("Hello!", MessageRole.USER),
                ConversationalMessage("Hi there!", MessageRole.ASSISTANT)
            ]
        )

        # Search long-term memory and process with LLM
        def my_llm(user_input: str, memories: List[Dict]) -> str:
            # Your LLM processing logic here
            return "Response based on context"

        memories, response, event = manager.process_turn_with_llm(
            actor_id="user-456",
            session_id="session-789",
            user_input="What did we discuss?",
            llm_callback=my_llm,
            retrieval_namespace="support/facts/{sessionId}"
        )
        ```

    Thread Safety:
        This class is not thread-safe. Create separate instances for concurrent operations.

    AWS Permissions Required:
        - bedrock-agentcore:CreateEvent
        - bedrock-agentcore:GetEvent
        - bedrock-agentcore:ListEvents
        - bedrock-agentcore:DeleteEvent
        - bedrock-agentcore:RetrieveMemoryRecords
        - bedrock-agentcore:ListMemoryRecords
        - bedrock-agentcore:GetMemoryRecord
        - bedrock-agentcore:DeleteMemoryRecord
        - bedrock-agentcore:ListActors
        - bedrock-agentcore:ListSessions
    """

    def __init__(
        self,
        memory_id: str,
        region_name: Optional[str] = None,
        boto3_session: Optional[boto3.Session] = None,
        boto_client_config: Optional[BotocoreConfig] = None,
    ):
        """Initialize a MemorySessionManager instance.

        Args:
            memory_id: The memory identifier for this session manager.
            region_name: AWS region for the bedrock-agentcore client. If not provided,
                   will use the region from boto3_session or default session.
            boto3_session: Optional boto3 Session to use. If provided and region_name
                          parameter is also specified, validation will ensure they match.
            boto_client_config: Optional boto3 client configuration. If provided, will be
                              merged with default configuration including user agent.

        Raises:
            ValueError: If region_name parameter conflicts with boto3_session region.
        """
        # Initialize core attributes
        self._memory_id = memory_id

        # Setup session and validate region consistency
        self.region_name = self._validate_and_resolve_region(region_name, boto3_session)
        session = boto3_session if boto3_session else boto3.Session()

        # Configure and create boto3 client
        client_config = self._build_client_config(boto_client_config)
        self._data_plane_client = session.client(
            "bedrock-agentcore", region_name=self.region_name, config=client_config
        )

        # Configure timestamp serialization to use float representation
        self._configure_timestamp_serialization()

        # Define allowed data plane methods
        self._ALLOWED_DATA_PLANE_METHODS = {
            "retrieve_memory_records",
            "get_memory_record",
            "delete_memory_record",
            "list_memory_records",
            "create_event",
            "get_event",
            "delete_event",
            "list_events",
        }

    def _validate_and_resolve_region(self, region_name: Optional[str], session: Optional[boto3.Session]) -> str:
        """Validate region consistency and resolve the final region to use.

        Args:
            region_name: Explicitly provided region name
            session: Optional Boto3 session instance

        Returns:
            The resolved region name to use

        Raises:
            ValueError: If region_name conflicts with session region
        """
        session_region = session.region_name if session else None

        # Validate region consistency if both are provided
        if region_name and session and session_region and (region_name != session_region):
            raise ValueError(
                f"Region mismatch: provided region_name '{region_name}' does not match "
                f"boto3_session region '{session_region}'. Please ensure both "
                f"parameters specify the same region or omit the region_name parameter "
                f"to use the session's region."
            )

        return region_name or session_region

    def _build_client_config(self, boto_client_config: Optional[BotocoreConfig]) -> BotocoreConfig:
        """Build the final boto3 client configuration with SDK user agent.

        Args:
            boto_client_config: Optional user-provided client configuration

        Returns:
            Final client configuration with SDK user agent
        """
        sdk_user_agent = "bedrock-agentcore-sdk"

        if boto_client_config:
            existing_user_agent = getattr(boto_client_config, "user_agent_extra", None)
            if existing_user_agent:
                new_user_agent = f"{existing_user_agent} {sdk_user_agent}"
            else:
                new_user_agent = sdk_user_agent
            return boto_client_config.merge(BotocoreConfig(user_agent_extra=new_user_agent))
        else:
            return BotocoreConfig(user_agent_extra=sdk_user_agent)

    def _configure_timestamp_serialization(self) -> None:
        """Configure the boto3 client to serialize timestamps as float values.

        This method overrides the default timestamp serialization to convert datetime objects
        to float timestamps (seconds since Unix epoch) which preserves millisecond precision
        when sending datetime objects to the AgentCore Memory service.
        """
        original_serialize_timestamp = self._data_plane_client._serializer._serializer._serialize_type_timestamp

        def serialize_timestamp_as_float(serialized, value, shape, name):
            if isinstance(value, datetime):
                serialized[name] = value.timestamp()  # Convert to float (seconds since epoch with fractional seconds)
            else:
                original_serialize_timestamp(serialized, value, shape, name)

        self._data_plane_client._serializer._serializer._serialize_type_timestamp = serialize_timestamp_as_float

    def __getattr__(self, name: str):
        """Dynamically forward method calls to the appropriate boto3 client.

        This method enables access to all data_plane boto3 client methods without explicitly
        defining them. Methods are looked up in the following order:
        _data_plane_client (bedrock-agentcore) - for data plane operations

        Args:
            name: The method name being accessed

        Returns:
            A callable method from the boto3 client

        Raises:
            AttributeError: If the method doesn't exist on _data_plane_client

        Example:
            # Access any boto3 method directly
            manager = MemorySessionManager(region_name="us-east-1")

            # These calls are forwarded to the appropriate boto3 functions
            memory_records = manager.retrieve_memory_records()
            events = manager.list_events(...)
        """
        if name in self._ALLOWED_DATA_PLANE_METHODS and hasattr(self._data_plane_client, name):
            method = getattr(self._data_plane_client, name)
            logger.debug("Forwarding method '%s' to _data_plane_client", name)
            return method

        # Method not found on client
        raise AttributeError(
            f"'{self.__class__.__name__}' object has no attribute '{name}'. "
            f"Method not found on _data_plane_client. "
            f"Available methods can be found in the boto3 documentation for "
            f"'bedrock-agentcore' services."
        )

    def process_turn_with_llm(
        self,
        actor_id: str,
        session_id: str,
        user_input: str,
        llm_callback: Callable[[str, List[Dict[str, Any]]], str],
        retrieval_config: Optional[Dict[str, RetrievalConfig]],
        event_timestamp: Optional[datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
        r"""Complete conversation turn with LLM callback integration.

        This method combines memory retrieval, LLM invocation, and response storage
        in a single call using a callback pattern.

        Args:
            actor_id: Actor identifier (e.g., "user-123")
            session_id: Session identifier
            user_input: The user's message
            llm_callback: Function that takes (user_input, memories) and returns agent_response
                         The callback receives the user input and retrieved memories,
                         and should return the agent's response string
            retrieval_config: Optional dictionary mapping namespaces to RetrievalConfig objects.
                            Each namespace can contain template variables like {actorId}, {sessionId},
                            {memoryStrategyId} that will be resolved at runtime.
            event_timestamp: Optional timestamp for the event

        Returns:
            Tuple of (retrieved_memories, agent_response, created_event)

        Example:
            from bedrock_agentcore.memory.constants import RetrievalConfig

            def my_llm(user_input: str, memories: List[Dict]) -> str:
                # Format context from memories
                context = "\\n".join([m.get('content', {}).get('text', '') for m in memories])

                # Call your LLM (Bedrock, OpenAI, etc.)
                response = bedrock.invoke_model(
                    messages=[
                        {"role": "system", "content": f"Context: {context}"},
                        {"role": "user", "content": user_input}
                    ]
                )
                return response['content']

            retrieval_config = {
                "support/facts/{sessionId}": RetrievalConfig(top_k=5, relevance_score=0.3),
                "user/preferences/{actorId}": RetrievalConfig(top_k=3, relevance_score=0.5)
            }

            memories, response, event = manager.process_turn_with_llm(
                actor_id="user-123",
                session_id="session-456",
                user_input="What did we discuss yesterday?",
                llm_callback=my_llm,
                retrieval_config=retrieval_config
            )
        """
        # Step 1: Retrieve relevant memories
        retrieved_memories = []
        if retrieval_config:
            for namespace, config in retrieval_config.items():
                resolved_namespace = namespace.format(
                    actorId=actor_id,
                    sessionId=session_id,
                    strategyId=config.strategy_id or "",
                )
                search_query = f"{config.retrieval_query} {user_input}" if config.retrieval_query else user_input
                memory_records = self.search_long_term_memories(
                    query=search_query, namespace_prefix=resolved_namespace, top_k=config.top_k
                )
                # Filter memory records with a relevance score which is lower than config.relevance_score
                if config.relevance_score:
                    memory_records = [
                        record
                        for record in memory_records
                        if record.get("relevanceScore", config.relevance_score) >= config.relevance_score
                    ]

                retrieved_memories.extend(memory_records)

        logger.info("Retrieved %d memories for LLM context", len(retrieved_memories))

        # Step 2: Invoke LLM callback
        try:
            agent_response = llm_callback(user_input, retrieved_memories)
            if not isinstance(agent_response, str):
                raise ValueError("LLM callback must return a string response")
            logger.info("LLM callback generated response")
        except Exception as e:
            logger.error("LLM callback failed: %s", e)
            raise

        # Step 3: Save the conversation turn
        event = self.add_turns(
            actor_id=actor_id,
            session_id=session_id,
            messages=[
                ConversationalMessage(user_input, MessageRole.USER),
                ConversationalMessage(agent_response, MessageRole.ASSISTANT),
            ],
            event_timestamp=event_timestamp,
        )

        logger.info("Completed full conversation turn with LLM")
        return retrieved_memories, agent_response, event

    def add_turns(
        self,
        actor_id: str,
        session_id: str,
        messages: List[Union[ConversationalMessage, BlobMessage]],
        branch: Optional[Dict[str, str]] = None,
        event_timestamp: Optional[datetime] = None,
    ) -> Event:
        """Adds conversational turns or blob objects to short-term memory.

        Maps to: bedrock-agentcore.create_event

        Args:
            actor_id: Actor identifier
            session_id: Session identifier
            messages: List of either:
                - ConversationalMessage objects for conversational messages
                - BlobMessage objects for blob data
            branch: Optional branch info
            event_timestamp: Optional timestamp for the event

        Returns:
            Created event

        Example:
            manager.add_turns(
                actor_id="user-123",
                session_id="session-456",
                messages=[
                    ConversationalMessage("Hello", USER),
                    BlobMessage({"file_data": "base64_content"}),
                    ConversationalMessage("How can I help?", ASSISTANT)
                ]
            )
        """
        logger.info("  -> Storing %d messages in short-term memory...", len(messages))

        if not messages:
            raise ValueError("At least one message is required")

        payload = []
        for message in messages:
            if isinstance(message, ConversationalMessage):
                # Handle ConversationalMessage data class
                payload.append({"conversational": {"content": {"text": message.text}, "role": message.role.value}})

            elif isinstance(message, BlobMessage):
                # Handle BlobMessage data class
                payload.append({"blob": message.data})
            else:
                raise ValueError("Invalid message format. Must be ConversationalMessage or BlobMessage")

        # Use provided timestamp or current time
        if event_timestamp is None:
            event_timestamp = datetime.now(timezone.utc)

        params = {
            "memoryId": self._memory_id,
            "actorId": actor_id,
            "sessionId": session_id,
            "eventTimestamp": event_timestamp,
            "payload": payload,
        }

        if branch:
            params["branch"] = branch
        try:
            response = self._data_plane_client.create_event(**params)
            logger.info("     ✅ Turn stored successfully with Event ID: %s", response.get("eventId"))
            return Event(response["event"])
        except ClientError as e:
            logger.error("     ❌ Error storing turn: %s", e)
            raise

    def fork_conversation(
        self,
        actor_id: str,
        session_id: str,
        root_event_id: str,
        branch_name: str,
        messages: List[Union[ConversationalMessage, BlobMessage]],
        event_timestamp: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Fork a conversation from a specific event to create a new branch."""
        try:
            branch = {"rootEventId": root_event_id, "name": branch_name}

            event = self.add_turns(
                actor_id=actor_id,
                session_id=session_id,
                messages=messages,
                event_timestamp=event_timestamp,
                branch=branch,
            )

            logger.info("Created branch '%s' from event %s", branch_name, root_event_id)
            return event

        except ClientError as e:
            logger.error("Failed to fork conversation: %s", e)
            raise

    def list_events(
        self,
        actor_id: str,
        session_id: str,
        branch_name: Optional[str] = None,
        include_parent_branches: bool = False,
        max_results: int = 100,
        include_payload: bool = True,
    ) -> List[Event]:
        """List all events in a session with pagination support.

        This method provides direct access to the raw events API, allowing developers
        to retrieve all events without the turn grouping logic of get_last_k_turns.

        Args:
            actor_id: Actor identifier
            session_id: Session identifier
            branch_name: Optional branch name to filter events (None for all branches)
            include_parent_branches: Whether to include parent branch events (only applies with branch_name)
            max_results: Maximum number of events to return
            include_payload: Whether to include event payloads in response

        Returns:
            List of event dictionaries in chronological order

        Example:
            # Get all events
            events = client.list_events(actor_id, session_id)

            # Get only main branch events
            main_events = client.list_events(actor_id, session_id, branch_name="main")

            # Get events from a specific branch
            branch_events = client.list_events(actor_id, session_id, branch_name="test-branch")
        """
        try:
            all_events: List[Event] = []
            next_token = None
            max_iterations = 1000  # Safety limit to prevent infinite loops

            iteration_count = 0
            while len(all_events) < max_results and iteration_count < max_iterations:
                iteration_count += 1

                params = {
                    "memoryId": self._memory_id,
                    "actorId": actor_id,
                    "sessionId": session_id,
                    "maxResults": min(100, max_results - len(all_events)),
                    "includePayloads": include_payload,
                }

                if next_token:
                    params["nextToken"] = next_token

                # Add branch filter if specified (but not for "main")
                if branch_name and branch_name != "main":
                    params["filter"] = {
                        "branch": {"name": branch_name, "includeParentBranches": include_parent_branches}
                    }

                response = self._data_plane_client.list_events(**params)

                events = response.get("events", [])

                # If no events returned, break to prevent infinite loop
                if not events:
                    logger.debug("No more events returned, ending pagination")
                    break

                all_events.extend([Event(event) for event in events])

                next_token = response.get("nextToken")
                if not next_token or len(all_events) >= max_results:
                    break

            if iteration_count >= max_iterations:
                logger.warning("Reached maximum iteration limit (%d) in list_events pagination", max_iterations)

            logger.info("Retrieved total of %d events", len(all_events))
            return all_events[:max_results]

        except ClientError as e:
            logger.error("Failed to list events: %s", e)
            raise

    def list_branches(self, actor_id: str, session_id: str) -> List[Branch]:
        """List all branches in a session.

        This method handles pagination automatically and provides a structured view
        of all conversation branches, which would require complex pagination and
        grouping logic if done with raw boto3 calls.

        Returns:
            List of branch information including name and root event
        """
        try:
            # Get all events - need to handle pagination for complete list
            all_events = []
            next_token = None
            max_iterations = 1000  # Safety limit to prevent infinite loops

            iteration_count = 0
            while iteration_count < max_iterations:
                iteration_count += 1

                params = {"memoryId": self._memory_id, "actorId": actor_id, "sessionId": session_id, "maxResults": 100}

                if next_token:
                    params["nextToken"] = next_token

                response = self._data_plane_client.list_events(**params)
                events = response.get("events", [])

                # If no events returned, break to prevent infinite loop
                if not events:
                    logger.debug("No more events returned, ending pagination in list_branches")
                    break

                all_events.extend(events)

                next_token = response.get("nextToken")
                if not next_token:
                    break

            if iteration_count >= max_iterations:
                logger.warning("Reached maximum iteration limit (%d) in list_branches pagination", max_iterations)

            branches = {}
            main_branch_events = []

            for event in all_events:
                branch_info = event.get("branch")
                if branch_info:
                    branch_name = branch_info["name"]
                    if branch_name not in branches:
                        branches[branch_name] = {
                            "name": branch_name,
                            "rootEventId": branch_info.get("rootEventId"),
                            "firstEventId": event["eventId"],
                            "eventCount": 1,
                            "created": event["eventTimestamp"],
                        }
                    else:
                        branches[branch_name]["eventCount"] += 1
                else:
                    main_branch_events.append(event)

            # Build result list
            result: List[Branch] = []

            # Only add main branch if there are actual events
            if main_branch_events:
                result.append(
                    {
                        "name": "main",
                        "rootEventId": None,
                        "firstEventId": main_branch_events[0]["eventId"],
                        "eventCount": len(main_branch_events),
                        "created": main_branch_events[0]["eventTimestamp"],
                    }
                )

            # Add other branches
            result.extend(list(branches.values()))

            logger.info("Found %d branches in session %s", len(result), session_id)
            return [Branch(branch) for branch in result]

        except ClientError as e:
            logger.error("Failed to list branches: %s", e)
            raise

    def get_last_k_turns(
        self,
        actor_id: str,
        session_id: str,
        k: int = 5,
        branch_name: Optional[str] = None,
        include_parent_branches: bool = False,
        max_results: int = 100,
    ) -> List[List[EventMessage]]:
        """Get the last K conversation turns.

        A "turn" typically consists of a user message followed by assistant response(s).
        This method groups messages into logical turns for easier processing.

        Returns:
            List of turns, where each turn is a list of message dictionaries
        """
        try:
            events = self.list_events(
                actor_id=actor_id,
                session_id=session_id,
                branch_name=branch_name,
                include_parent_branches=include_parent_branches,
                max_results=max_results,
            )

            if not events:
                return []

            # Process events to group into turns
            turns = []
            current_turn = []

            for event in events:
                if len(turns) >= k:
                    break  # Only need last K turns
                for payload_item in event.get("payload", []):
                    if "conversational" in payload_item:
                        role = payload_item["conversational"].get("role")

                        # Start new turn on USER message
                        if role == MessageRole.USER.value and current_turn:
                            turns.append(current_turn)
                            current_turn = []

                        current_turn.append(EventMessage(payload_item["conversational"]))

            # Don't forget the last turn
            if current_turn:
                turns.append(current_turn)

            # Return the last k turns
            return turns[:k] if len(turns) > k else turns

        except ClientError as e:
            logger.error("Failed to get last K turns: %s", e)
            raise

    def get_event(self, actor_id: str, session_id: str, event_id: str) -> Event:
        """Retrieves a specific event from short-term memory by its ID.

        Maps to: bedrock-agentcore.get_event.
        """
        logger.info("  -> Retrieving event by ID: %s...", event_id)
        try:
            response = self._data_plane_client.get_event(
                memoryId=self._memory_id, actorId=actor_id, sessionId=session_id, eventId=event_id
            )
            logger.info("     ✅ Event retrieved.")
            return Event(response.get("event", {}))
        except ClientError as e:
            logger.error("     ❌ Error retrieving event: %s", e)
            raise

    def delete_event(self, actor_id: str, session_id: str, event_id: str):
        """Deletes a specific event from short-term memory by its ID.

        Maps to: bedrock-agentcore.delete_event.
        """
        logger.info("  -> Deleting event by ID: %s...", event_id)
        try:
            self._data_plane_client.delete_event(
                memoryId=self._memory_id, actorId=actor_id, sessionId=session_id, eventId=event_id
            )
            logger.info("     ✅ Event deleted successfully.")
        except ClientError as e:
            logger.error("     ❌ Error deleting event: %s", e)
            raise

    def search_long_term_memories(
        self,
        query: str,
        namespace_prefix: str,
        top_k: int = 3,
        strategy_id: str = None,
        max_results: int = 20,
    ) -> List[MemoryRecord]:
        """Performs a semantic search against the long-term memory for this actor.

        Maps to: bedrock-agentcore.retrieve_memory_records.
        """
        logger.info("  -> Querying long-term memory in namespace '%s' with query: '%s'...", namespace_prefix, query)
        search_criteria = {"searchQuery": query, "topK": top_k}
        if strategy_id:
            search_criteria["strategyId"] = strategy_id

        namespace = namespace_prefix
        params = {
            "memoryId": self._memory_id,
            "searchCriteria": search_criteria,
            "namespace": namespace,
            "maxResults": max_results,
        }

        try:
            response = self._data_plane_client.retrieve_memory_records(**params)
            records = response.get("memoryRecordSummaries", [])
            logger.info("     ✅ Found %d relevant long-term records.", len(records))
            return [MemoryRecord(record) for record in records]
        except ClientError as e:
            logger.info("     ❌ Error querying long-term memory", e)
            raise

    def list_long_term_memory_records(
        self, namespace_prefix: str, strategy_id: Optional[str] = None, max_results: int = 10
    ) -> List[MemoryRecord]:
        """Lists all long-term memory records for this actor without a semantic query.

        Maps to: bedrock-agentcore.list_memory_records.
        """
        logger.info("  -> Listing all long-term records in namespace '%s'...", namespace_prefix)

        try:
            paginator = self._data_plane_client.get_paginator("list_memory_records")

            params = {
                "memoryId": self._memory_id,
                "namespace": namespace_prefix,
            }

            if strategy_id:
                params["memoryStrategyId"] = strategy_id

            pages = paginator.paginate(**params)
            all_records: List[MemoryRecord] = []

            for page in pages:
                memory_records = page.get("memoryRecords", [])
                # Also check for memoryRecordSummaries (which is what the API actually returns)
                if not memory_records:
                    memory_records = page.get("memoryRecordSummaries", [])

                all_records.extend([MemoryRecord(record) for record in memory_records])

                # Stop if we've reached max_results
                if len(all_records) >= max_results:
                    break

            logger.info("     ✅ Found a total of %d long-term records.", len(all_records))
            return all_records[:max_results]

        except ClientError as e:
            logger.error("     ❌ Error listing long-term records: %s", e)
            raise

    def list_actors(self) -> List[ActorSummary]:
        """Lists all actors who have events in a specific memory.

        Maps to: bedrock-agentcore.list_actors.
        """
        logger.info("👥 Listing all actors for memory %s...", self._memory_id)
        try:
            paginator = self._data_plane_client.get_paginator("list_actors")
            pages = paginator.paginate(memoryId=self._memory_id)
            all_actors = []
            for page in pages:
                actor_summaries = page.get("actorSummaries", [])
                all_actors.extend([ActorSummary(actor) for actor in actor_summaries])
            logger.info("  ✅ Found %d actors.", len(all_actors))
            return all_actors
        except ClientError as e:
            logger.error("  ❌ Error listing actors: %s", e)
            raise

    def get_memory_record(self, record_id: str) -> MemoryRecord:
        """Retrieves a specific long-term memory record by its ID.

        Maps to: bedrock-agentcore.get_memory_record.
        """
        logger.info("📄 Retrieving long-term record by ID: %s from memory %s...", record_id, self._memory_id)
        try:
            response = self._data_plane_client.get_memory_record(memoryId=self._memory_id, memoryRecordId=record_id)
            logger.info("  ✅ Record retrieved.")
            memory_record = response.get("memoryRecord", {})
            return MemoryRecord(memory_record)
        except ClientError as e:
            logger.error("  ❌ Error retrieving record: %s", e)
            raise

    def delete_memory_record(self, record_id: str):
        """Deletes a specific long-term memory record by its ID.

        Maps to: bedrock-agentcore.delete_memory_record.
        """
        logger.info("🗑️ Deleting long-term record by ID: %s from memory %s...", record_id, self._memory_id)
        try:
            self._data_plane_client.delete_memory_record(memoryId=self._memory_id, memoryRecordId=record_id)
            logger.info("  ✅ Record deleted successfully.")
        except ClientError as e:
            logger.error("  ❌ Error deleting record: %s", e)
            raise

    def list_actor_sessions(self, actor_id: str) -> List[SessionSummary]:
        """Lists all sessions for a specific actor in a specific memory.

        Maps to: bedrock-agentcore.list_sessions.
        """
        logger.info("🗂️ Listing all sessions for actor '%s' in memory %s...", actor_id, self._memory_id)
        try:
            paginator = self._data_plane_client.get_paginator("list_sessions")
            pages = paginator.paginate(memoryId=self._memory_id, actorId=actor_id)
            all_sessions: List[SessionSummary] = []
            for page in pages:
                response = page.get("sessionSummaries", [])
                all_sessions.extend([SessionSummary(session) for session in response])
            logger.info("  ✅ Found %d sessions.", len(all_sessions))
            return all_sessions
        except ClientError as e:
            logger.error("  ❌ Error listing sessions: %s", e)
            raise

    def create_memory_session(self, actor_id: str, session_id: str = None) -> "MemorySession":
        """Creates a new MemorySession instance."""
        session_id = session_id or str(uuid.uuid4())
        logger.info("💬 Creating new conversation for actor '%s' in session '%s'...", actor_id, session_id)
        return MemorySession(memory_id=self._memory_id, actor_id=actor_id, session_id=session_id, manager=self)
````

#### `__getattr__(name)`

Dynamically forward method calls to the appropriate boto3 client.

This method enables access to all data_plane boto3 client methods without explicitly defining them. Methods are looked up in the following order: \_data_plane_client (bedrock-agentcore) - for data plane operations

Parameters:

| Name   | Type  | Description                    | Default    |
| ------ | ----- | ------------------------------ | ---------- |
| `name` | `str` | The method name being accessed | *required* |

Returns:

| Type | Description                             |
| ---- | --------------------------------------- |
|      | A callable method from the boto3 client |

Raises:

| Type             | Description                                        |
| ---------------- | -------------------------------------------------- |
| `AttributeError` | If the method doesn't exist on \_data_plane_client |

Example

##### Access any boto3 method directly

manager = MemorySessionManager(region_name="us-east-1")

##### These calls are forwarded to the appropriate boto3 functions

memory_records = manager.retrieve_memory_records() events = manager.list_events(...)

Source code in `bedrock_agentcore/memory/session.py`

```
def __getattr__(self, name: str):
    """Dynamically forward method calls to the appropriate boto3 client.

    This method enables access to all data_plane boto3 client methods without explicitly
    defining them. Methods are looked up in the following order:
    _data_plane_client (bedrock-agentcore) - for data plane operations

    Args:
        name: The method name being accessed

    Returns:
        A callable method from the boto3 client

    Raises:
        AttributeError: If the method doesn't exist on _data_plane_client

    Example:
        # Access any boto3 method directly
        manager = MemorySessionManager(region_name="us-east-1")

        # These calls are forwarded to the appropriate boto3 functions
        memory_records = manager.retrieve_memory_records()
        events = manager.list_events(...)
    """
    if name in self._ALLOWED_DATA_PLANE_METHODS and hasattr(self._data_plane_client, name):
        method = getattr(self._data_plane_client, name)
        logger.debug("Forwarding method '%s' to _data_plane_client", name)
        return method

    # Method not found on client
    raise AttributeError(
        f"'{self.__class__.__name__}' object has no attribute '{name}'. "
        f"Method not found on _data_plane_client. "
        f"Available methods can be found in the boto3 documentation for "
        f"'bedrock-agentcore' services."
    )
```

#### `__init__(memory_id, region_name=None, boto3_session=None, boto_client_config=None)`

Initialize a MemorySessionManager instance.

Parameters:

| Name                 | Type                | Description                                                                                                                | Default    |
| -------------------- | ------------------- | -------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `memory_id`          | `str`               | The memory identifier for this session manager.                                                                            | *required* |
| `region_name`        | `Optional[str]`     | AWS region for the bedrock-agentcore client. If not provided, will use the region from boto3_session or default session.   | `None`     |
| `boto3_session`      | `Optional[Session]` | Optional boto3 Session to use. If provided and region_name parameter is also specified, validation will ensure they match. | `None`     |
| `boto_client_config` | `Optional[Config]`  | Optional boto3 client configuration. If provided, will be merged with default configuration including user agent.          | `None`     |

Raises:

| Type         | Description                                                   |
| ------------ | ------------------------------------------------------------- |
| `ValueError` | If region_name parameter conflicts with boto3_session region. |

Source code in `bedrock_agentcore/memory/session.py`

```
def __init__(
    self,
    memory_id: str,
    region_name: Optional[str] = None,
    boto3_session: Optional[boto3.Session] = None,
    boto_client_config: Optional[BotocoreConfig] = None,
):
    """Initialize a MemorySessionManager instance.

    Args:
        memory_id: The memory identifier for this session manager.
        region_name: AWS region for the bedrock-agentcore client. If not provided,
               will use the region from boto3_session or default session.
        boto3_session: Optional boto3 Session to use. If provided and region_name
                      parameter is also specified, validation will ensure they match.
        boto_client_config: Optional boto3 client configuration. If provided, will be
                          merged with default configuration including user agent.

    Raises:
        ValueError: If region_name parameter conflicts with boto3_session region.
    """
    # Initialize core attributes
    self._memory_id = memory_id

    # Setup session and validate region consistency
    self.region_name = self._validate_and_resolve_region(region_name, boto3_session)
    session = boto3_session if boto3_session else boto3.Session()

    # Configure and create boto3 client
    client_config = self._build_client_config(boto_client_config)
    self._data_plane_client = session.client(
        "bedrock-agentcore", region_name=self.region_name, config=client_config
    )

    # Configure timestamp serialization to use float representation
    self._configure_timestamp_serialization()

    # Define allowed data plane methods
    self._ALLOWED_DATA_PLANE_METHODS = {
        "retrieve_memory_records",
        "get_memory_record",
        "delete_memory_record",
        "list_memory_records",
        "create_event",
        "get_event",
        "delete_event",
        "list_events",
    }
```

#### `add_turns(actor_id, session_id, messages, branch=None, event_timestamp=None)`

Adds conversational turns or blob objects to short-term memory.

Maps to: bedrock-agentcore.create_event

Parameters:

| Name              | Type                                              | Description                                                                                                     | Default    |
| ----------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ---------- |
| `actor_id`        | `str`                                             | Actor identifier                                                                                                | *required* |
| `session_id`      | `str`                                             | Session identifier                                                                                              | *required* |
| `messages`        | `List[Union[ConversationalMessage, BlobMessage]]` | List of either: - ConversationalMessage objects for conversational messages - BlobMessage objects for blob data | *required* |
| `branch`          | `Optional[Dict[str, str]]`                        | Optional branch info                                                                                            | `None`     |
| `event_timestamp` | `Optional[datetime]`                              | Optional timestamp for the event                                                                                | `None`     |

Returns:

| Type    | Description   |
| ------- | ------------- |
| `Event` | Created event |

Example

manager.add_turns( actor_id="user-123", session_id="session-456", messages=[ ConversationalMessage("Hello", USER), BlobMessage({"file_data": "base64_content"}), ConversationalMessage("How can I help?", ASSISTANT) ] )

Source code in `bedrock_agentcore/memory/session.py`

```
def add_turns(
    self,
    actor_id: str,
    session_id: str,
    messages: List[Union[ConversationalMessage, BlobMessage]],
    branch: Optional[Dict[str, str]] = None,
    event_timestamp: Optional[datetime] = None,
) -> Event:
    """Adds conversational turns or blob objects to short-term memory.

    Maps to: bedrock-agentcore.create_event

    Args:
        actor_id: Actor identifier
        session_id: Session identifier
        messages: List of either:
            - ConversationalMessage objects for conversational messages
            - BlobMessage objects for blob data
        branch: Optional branch info
        event_timestamp: Optional timestamp for the event

    Returns:
        Created event

    Example:
        manager.add_turns(
            actor_id="user-123",
            session_id="session-456",
            messages=[
                ConversationalMessage("Hello", USER),
                BlobMessage({"file_data": "base64_content"}),
                ConversationalMessage("How can I help?", ASSISTANT)
            ]
        )
    """
    logger.info("  -> Storing %d messages in short-term memory...", len(messages))

    if not messages:
        raise ValueError("At least one message is required")

    payload = []
    for message in messages:
        if isinstance(message, ConversationalMessage):
            # Handle ConversationalMessage data class
            payload.append({"conversational": {"content": {"text": message.text}, "role": message.role.value}})

        elif isinstance(message, BlobMessage):
            # Handle BlobMessage data class
            payload.append({"blob": message.data})
        else:
            raise ValueError("Invalid message format. Must be ConversationalMessage or BlobMessage")

    # Use provided timestamp or current time
    if event_timestamp is None:
        event_timestamp = datetime.now(timezone.utc)

    params = {
        "memoryId": self._memory_id,
        "actorId": actor_id,
        "sessionId": session_id,
        "eventTimestamp": event_timestamp,
        "payload": payload,
    }

    if branch:
        params["branch"] = branch
    try:
        response = self._data_plane_client.create_event(**params)
        logger.info("     ✅ Turn stored successfully with Event ID: %s", response.get("eventId"))
        return Event(response["event"])
    except ClientError as e:
        logger.error("     ❌ Error storing turn: %s", e)
        raise
```

#### `create_memory_session(actor_id, session_id=None)`

Creates a new MemorySession instance.

Source code in `bedrock_agentcore/memory/session.py`

```
def create_memory_session(self, actor_id: str, session_id: str = None) -> "MemorySession":
    """Creates a new MemorySession instance."""
    session_id = session_id or str(uuid.uuid4())
    logger.info("💬 Creating new conversation for actor '%s' in session '%s'...", actor_id, session_id)
    return MemorySession(memory_id=self._memory_id, actor_id=actor_id, session_id=session_id, manager=self)
```

#### `delete_event(actor_id, session_id, event_id)`

Deletes a specific event from short-term memory by its ID.

Maps to: bedrock-agentcore.delete_event.

Source code in `bedrock_agentcore/memory/session.py`

```
def delete_event(self, actor_id: str, session_id: str, event_id: str):
    """Deletes a specific event from short-term memory by its ID.

    Maps to: bedrock-agentcore.delete_event.
    """
    logger.info("  -> Deleting event by ID: %s...", event_id)
    try:
        self._data_plane_client.delete_event(
            memoryId=self._memory_id, actorId=actor_id, sessionId=session_id, eventId=event_id
        )
        logger.info("     ✅ Event deleted successfully.")
    except ClientError as e:
        logger.error("     ❌ Error deleting event: %s", e)
        raise
```

#### `delete_memory_record(record_id)`

Deletes a specific long-term memory record by its ID.

Maps to: bedrock-agentcore.delete_memory_record.

Source code in `bedrock_agentcore/memory/session.py`

```
def delete_memory_record(self, record_id: str):
    """Deletes a specific long-term memory record by its ID.

    Maps to: bedrock-agentcore.delete_memory_record.
    """
    logger.info("🗑️ Deleting long-term record by ID: %s from memory %s...", record_id, self._memory_id)
    try:
        self._data_plane_client.delete_memory_record(memoryId=self._memory_id, memoryRecordId=record_id)
        logger.info("  ✅ Record deleted successfully.")
    except ClientError as e:
        logger.error("  ❌ Error deleting record: %s", e)
        raise
```

#### `fork_conversation(actor_id, session_id, root_event_id, branch_name, messages, event_timestamp=None)`

Fork a conversation from a specific event to create a new branch.

Source code in `bedrock_agentcore/memory/session.py`

```
def fork_conversation(
    self,
    actor_id: str,
    session_id: str,
    root_event_id: str,
    branch_name: str,
    messages: List[Union[ConversationalMessage, BlobMessage]],
    event_timestamp: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Fork a conversation from a specific event to create a new branch."""
    try:
        branch = {"rootEventId": root_event_id, "name": branch_name}

        event = self.add_turns(
            actor_id=actor_id,
            session_id=session_id,
            messages=messages,
            event_timestamp=event_timestamp,
            branch=branch,
        )

        logger.info("Created branch '%s' from event %s", branch_name, root_event_id)
        return event

    except ClientError as e:
        logger.error("Failed to fork conversation: %s", e)
        raise
```

#### `get_event(actor_id, session_id, event_id)`

Retrieves a specific event from short-term memory by its ID.

Maps to: bedrock-agentcore.get_event.

Source code in `bedrock_agentcore/memory/session.py`

```
def get_event(self, actor_id: str, session_id: str, event_id: str) -> Event:
    """Retrieves a specific event from short-term memory by its ID.

    Maps to: bedrock-agentcore.get_event.
    """
    logger.info("  -> Retrieving event by ID: %s...", event_id)
    try:
        response = self._data_plane_client.get_event(
            memoryId=self._memory_id, actorId=actor_id, sessionId=session_id, eventId=event_id
        )
        logger.info("     ✅ Event retrieved.")
        return Event(response.get("event", {}))
    except ClientError as e:
        logger.error("     ❌ Error retrieving event: %s", e)
        raise
```

#### `get_last_k_turns(actor_id, session_id, k=5, branch_name=None, include_parent_branches=False, max_results=100)`

Get the last K conversation turns.

A "turn" typically consists of a user message followed by assistant response(s). This method groups messages into logical turns for easier processing.

Returns:

| Type                       | Description                                                      |
| -------------------------- | ---------------------------------------------------------------- |
| `List[List[EventMessage]]` | List of turns, where each turn is a list of message dictionaries |

Source code in `bedrock_agentcore/memory/session.py`

```
def get_last_k_turns(
    self,
    actor_id: str,
    session_id: str,
    k: int = 5,
    branch_name: Optional[str] = None,
    include_parent_branches: bool = False,
    max_results: int = 100,
) -> List[List[EventMessage]]:
    """Get the last K conversation turns.

    A "turn" typically consists of a user message followed by assistant response(s).
    This method groups messages into logical turns for easier processing.

    Returns:
        List of turns, where each turn is a list of message dictionaries
    """
    try:
        events = self.list_events(
            actor_id=actor_id,
            session_id=session_id,
            branch_name=branch_name,
            include_parent_branches=include_parent_branches,
            max_results=max_results,
        )

        if not events:
            return []

        # Process events to group into turns
        turns = []
        current_turn = []

        for event in events:
            if len(turns) >= k:
                break  # Only need last K turns
            for payload_item in event.get("payload", []):
                if "conversational" in payload_item:
                    role = payload_item["conversational"].get("role")

                    # Start new turn on USER message
                    if role == MessageRole.USER.value and current_turn:
                        turns.append(current_turn)
                        current_turn = []

                    current_turn.append(EventMessage(payload_item["conversational"]))

        # Don't forget the last turn
        if current_turn:
            turns.append(current_turn)

        # Return the last k turns
        return turns[:k] if len(turns) > k else turns

    except ClientError as e:
        logger.error("Failed to get last K turns: %s", e)
        raise
```

#### `get_memory_record(record_id)`

Retrieves a specific long-term memory record by its ID.

Maps to: bedrock-agentcore.get_memory_record.

Source code in `bedrock_agentcore/memory/session.py`

```
def get_memory_record(self, record_id: str) -> MemoryRecord:
    """Retrieves a specific long-term memory record by its ID.

    Maps to: bedrock-agentcore.get_memory_record.
    """
    logger.info("📄 Retrieving long-term record by ID: %s from memory %s...", record_id, self._memory_id)
    try:
        response = self._data_plane_client.get_memory_record(memoryId=self._memory_id, memoryRecordId=record_id)
        logger.info("  ✅ Record retrieved.")
        memory_record = response.get("memoryRecord", {})
        return MemoryRecord(memory_record)
    except ClientError as e:
        logger.error("  ❌ Error retrieving record: %s", e)
        raise
```

#### `list_actor_sessions(actor_id)`

Lists all sessions for a specific actor in a specific memory.

Maps to: bedrock-agentcore.list_sessions.

Source code in `bedrock_agentcore/memory/session.py`

```
def list_actor_sessions(self, actor_id: str) -> List[SessionSummary]:
    """Lists all sessions for a specific actor in a specific memory.

    Maps to: bedrock-agentcore.list_sessions.
    """
    logger.info("🗂️ Listing all sessions for actor '%s' in memory %s...", actor_id, self._memory_id)
    try:
        paginator = self._data_plane_client.get_paginator("list_sessions")
        pages = paginator.paginate(memoryId=self._memory_id, actorId=actor_id)
        all_sessions: List[SessionSummary] = []
        for page in pages:
            response = page.get("sessionSummaries", [])
            all_sessions.extend([SessionSummary(session) for session in response])
        logger.info("  ✅ Found %d sessions.", len(all_sessions))
        return all_sessions
    except ClientError as e:
        logger.error("  ❌ Error listing sessions: %s", e)
        raise
```

#### `list_actors()`

Lists all actors who have events in a specific memory.

Maps to: bedrock-agentcore.list_actors.

Source code in `bedrock_agentcore/memory/session.py`

```
def list_actors(self) -> List[ActorSummary]:
    """Lists all actors who have events in a specific memory.

    Maps to: bedrock-agentcore.list_actors.
    """
    logger.info("👥 Listing all actors for memory %s...", self._memory_id)
    try:
        paginator = self._data_plane_client.get_paginator("list_actors")
        pages = paginator.paginate(memoryId=self._memory_id)
        all_actors = []
        for page in pages:
            actor_summaries = page.get("actorSummaries", [])
            all_actors.extend([ActorSummary(actor) for actor in actor_summaries])
        logger.info("  ✅ Found %d actors.", len(all_actors))
        return all_actors
    except ClientError as e:
        logger.error("  ❌ Error listing actors: %s", e)
        raise
```

#### `list_branches(actor_id, session_id)`

List all branches in a session.

This method handles pagination automatically and provides a structured view of all conversation branches, which would require complex pagination and grouping logic if done with raw boto3 calls.

Returns:

| Type           | Description                                              |
| -------------- | -------------------------------------------------------- |
| `List[Branch]` | List of branch information including name and root event |

Source code in `bedrock_agentcore/memory/session.py`

```
def list_branches(self, actor_id: str, session_id: str) -> List[Branch]:
    """List all branches in a session.

    This method handles pagination automatically and provides a structured view
    of all conversation branches, which would require complex pagination and
    grouping logic if done with raw boto3 calls.

    Returns:
        List of branch information including name and root event
    """
    try:
        # Get all events - need to handle pagination for complete list
        all_events = []
        next_token = None
        max_iterations = 1000  # Safety limit to prevent infinite loops

        iteration_count = 0
        while iteration_count < max_iterations:
            iteration_count += 1

            params = {"memoryId": self._memory_id, "actorId": actor_id, "sessionId": session_id, "maxResults": 100}

            if next_token:
                params["nextToken"] = next_token

            response = self._data_plane_client.list_events(**params)
            events = response.get("events", [])

            # If no events returned, break to prevent infinite loop
            if not events:
                logger.debug("No more events returned, ending pagination in list_branches")
                break

            all_events.extend(events)

            next_token = response.get("nextToken")
            if not next_token:
                break

        if iteration_count >= max_iterations:
            logger.warning("Reached maximum iteration limit (%d) in list_branches pagination", max_iterations)

        branches = {}
        main_branch_events = []

        for event in all_events:
            branch_info = event.get("branch")
            if branch_info:
                branch_name = branch_info["name"]
                if branch_name not in branches:
                    branches[branch_name] = {
                        "name": branch_name,
                        "rootEventId": branch_info.get("rootEventId"),
                        "firstEventId": event["eventId"],
                        "eventCount": 1,
                        "created": event["eventTimestamp"],
                    }
                else:
                    branches[branch_name]["eventCount"] += 1
            else:
                main_branch_events.append(event)

        # Build result list
        result: List[Branch] = []

        # Only add main branch if there are actual events
        if main_branch_events:
            result.append(
                {
                    "name": "main",
                    "rootEventId": None,
                    "firstEventId": main_branch_events[0]["eventId"],
                    "eventCount": len(main_branch_events),
                    "created": main_branch_events[0]["eventTimestamp"],
                }
            )

        # Add other branches
        result.extend(list(branches.values()))

        logger.info("Found %d branches in session %s", len(result), session_id)
        return [Branch(branch) for branch in result]

    except ClientError as e:
        logger.error("Failed to list branches: %s", e)
        raise
```

#### `list_events(actor_id, session_id, branch_name=None, include_parent_branches=False, max_results=100, include_payload=True)`

List all events in a session with pagination support.

This method provides direct access to the raw events API, allowing developers to retrieve all events without the turn grouping logic of get_last_k_turns.

Parameters:

| Name                      | Type            | Description                                                             | Default    |
| ------------------------- | --------------- | ----------------------------------------------------------------------- | ---------- |
| `actor_id`                | `str`           | Actor identifier                                                        | *required* |
| `session_id`              | `str`           | Session identifier                                                      | *required* |
| `branch_name`             | `Optional[str]` | Optional branch name to filter events (None for all branches)           | `None`     |
| `include_parent_branches` | `bool`          | Whether to include parent branch events (only applies with branch_name) | `False`    |
| `max_results`             | `int`           | Maximum number of events to return                                      | `100`      |
| `include_payload`         | `bool`          | Whether to include event payloads in response                           | `True`     |

Returns:

| Type          | Description                                       |
| ------------- | ------------------------------------------------- |
| `List[Event]` | List of event dictionaries in chronological order |

Example

##### Get all events

events = client.list_events(actor_id, session_id)

##### Get only main branch events

main_events = client.list_events(actor_id, session_id, branch_name="main")

##### Get events from a specific branch

branch_events = client.list_events(actor_id, session_id, branch_name="test-branch")

Source code in `bedrock_agentcore/memory/session.py`

```
def list_events(
    self,
    actor_id: str,
    session_id: str,
    branch_name: Optional[str] = None,
    include_parent_branches: bool = False,
    max_results: int = 100,
    include_payload: bool = True,
) -> List[Event]:
    """List all events in a session with pagination support.

    This method provides direct access to the raw events API, allowing developers
    to retrieve all events without the turn grouping logic of get_last_k_turns.

    Args:
        actor_id: Actor identifier
        session_id: Session identifier
        branch_name: Optional branch name to filter events (None for all branches)
        include_parent_branches: Whether to include parent branch events (only applies with branch_name)
        max_results: Maximum number of events to return
        include_payload: Whether to include event payloads in response

    Returns:
        List of event dictionaries in chronological order

    Example:
        # Get all events
        events = client.list_events(actor_id, session_id)

        # Get only main branch events
        main_events = client.list_events(actor_id, session_id, branch_name="main")

        # Get events from a specific branch
        branch_events = client.list_events(actor_id, session_id, branch_name="test-branch")
    """
    try:
        all_events: List[Event] = []
        next_token = None
        max_iterations = 1000  # Safety limit to prevent infinite loops

        iteration_count = 0
        while len(all_events) < max_results and iteration_count < max_iterations:
            iteration_count += 1

            params = {
                "memoryId": self._memory_id,
                "actorId": actor_id,
                "sessionId": session_id,
                "maxResults": min(100, max_results - len(all_events)),
                "includePayloads": include_payload,
            }

            if next_token:
                params["nextToken"] = next_token

            # Add branch filter if specified (but not for "main")
            if branch_name and branch_name != "main":
                params["filter"] = {
                    "branch": {"name": branch_name, "includeParentBranches": include_parent_branches}
                }

            response = self._data_plane_client.list_events(**params)

            events = response.get("events", [])

            # If no events returned, break to prevent infinite loop
            if not events:
                logger.debug("No more events returned, ending pagination")
                break

            all_events.extend([Event(event) for event in events])

            next_token = response.get("nextToken")
            if not next_token or len(all_events) >= max_results:
                break

        if iteration_count >= max_iterations:
            logger.warning("Reached maximum iteration limit (%d) in list_events pagination", max_iterations)

        logger.info("Retrieved total of %d events", len(all_events))
        return all_events[:max_results]

    except ClientError as e:
        logger.error("Failed to list events: %s", e)
        raise
```

#### `list_long_term_memory_records(namespace_prefix, strategy_id=None, max_results=10)`

Lists all long-term memory records for this actor without a semantic query.

Maps to: bedrock-agentcore.list_memory_records.

Source code in `bedrock_agentcore/memory/session.py`

```
def list_long_term_memory_records(
    self, namespace_prefix: str, strategy_id: Optional[str] = None, max_results: int = 10
) -> List[MemoryRecord]:
    """Lists all long-term memory records for this actor without a semantic query.

    Maps to: bedrock-agentcore.list_memory_records.
    """
    logger.info("  -> Listing all long-term records in namespace '%s'...", namespace_prefix)

    try:
        paginator = self._data_plane_client.get_paginator("list_memory_records")

        params = {
            "memoryId": self._memory_id,
            "namespace": namespace_prefix,
        }

        if strategy_id:
            params["memoryStrategyId"] = strategy_id

        pages = paginator.paginate(**params)
        all_records: List[MemoryRecord] = []

        for page in pages:
            memory_records = page.get("memoryRecords", [])
            # Also check for memoryRecordSummaries (which is what the API actually returns)
            if not memory_records:
                memory_records = page.get("memoryRecordSummaries", [])

            all_records.extend([MemoryRecord(record) for record in memory_records])

            # Stop if we've reached max_results
            if len(all_records) >= max_results:
                break

        logger.info("     ✅ Found a total of %d long-term records.", len(all_records))
        return all_records[:max_results]

    except ClientError as e:
        logger.error("     ❌ Error listing long-term records: %s", e)
        raise
```

#### `process_turn_with_llm(actor_id, session_id, user_input, llm_callback, retrieval_config, event_timestamp=None)`

Complete conversation turn with LLM callback integration.

This method combines memory retrieval, LLM invocation, and response storage in a single call using a callback pattern.

Parameters:

| Name               | Type                                         | Description                                                                                                                                                                                        | Default    |
| ------------------ | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `actor_id`         | `str`                                        | Actor identifier (e.g., "user-123")                                                                                                                                                                | *required* |
| `session_id`       | `str`                                        | Session identifier                                                                                                                                                                                 | *required* |
| `user_input`       | `str`                                        | The user's message                                                                                                                                                                                 | *required* |
| `llm_callback`     | `Callable[[str, List[Dict[str, Any]]], str]` | Function that takes (user_input, memories) and returns agent_response The callback receives the user input and retrieved memories, and should return the agent's response string                   | *required* |
| `retrieval_config` | `Optional[Dict[str, RetrievalConfig]]`       | Optional dictionary mapping namespaces to RetrievalConfig objects. Each namespace can contain template variables like {actorId}, {sessionId}, {memoryStrategyId} that will be resolved at runtime. | *required* |
| `event_timestamp`  | `Optional[datetime]`                         | Optional timestamp for the event                                                                                                                                                                   | `None`     |

Returns:

| Type                                               | Description                                                  |
| -------------------------------------------------- | ------------------------------------------------------------ |
| `Tuple[List[Dict[str, Any]], str, Dict[str, Any]]` | Tuple of (retrieved_memories, agent_response, created_event) |

Example

from bedrock_agentcore.memory.constants import RetrievalConfig

def my_llm(user_input: str, memories: List[Dict]) -> str:

# Format context from memories

context = "\\n".join([m.get('content', {}).get('text', '') for m in memories])

```
# Call your LLM (Bedrock, OpenAI, etc.)
response = bedrock.invoke_model(
    messages=[
        {"role": "system", "content": f"Context: {context}"},
        {"role": "user", "content": user_input}
    ]
)
return response['content']
```

retrieval_config = { "support/facts/{sessionId}": RetrievalConfig(top_k=5, relevance_score=0.3), "user/preferences/{actorId}": RetrievalConfig(top_k=3, relevance_score=0.5) }

memories, response, event = manager.process_turn_with_llm( actor_id="user-123", session_id="session-456", user_input="What did we discuss yesterday?", llm_callback=my_llm, retrieval_config=retrieval_config )

Source code in `bedrock_agentcore/memory/session.py`

```
def process_turn_with_llm(
    self,
    actor_id: str,
    session_id: str,
    user_input: str,
    llm_callback: Callable[[str, List[Dict[str, Any]]], str],
    retrieval_config: Optional[Dict[str, RetrievalConfig]],
    event_timestamp: Optional[datetime] = None,
) -> Tuple[List[Dict[str, Any]], str, Dict[str, Any]]:
    r"""Complete conversation turn with LLM callback integration.

    This method combines memory retrieval, LLM invocation, and response storage
    in a single call using a callback pattern.

    Args:
        actor_id: Actor identifier (e.g., "user-123")
        session_id: Session identifier
        user_input: The user's message
        llm_callback: Function that takes (user_input, memories) and returns agent_response
                     The callback receives the user input and retrieved memories,
                     and should return the agent's response string
        retrieval_config: Optional dictionary mapping namespaces to RetrievalConfig objects.
                        Each namespace can contain template variables like {actorId}, {sessionId},
                        {memoryStrategyId} that will be resolved at runtime.
        event_timestamp: Optional timestamp for the event

    Returns:
        Tuple of (retrieved_memories, agent_response, created_event)

    Example:
        from bedrock_agentcore.memory.constants import RetrievalConfig

        def my_llm(user_input: str, memories: List[Dict]) -> str:
            # Format context from memories
            context = "\\n".join([m.get('content', {}).get('text', '') for m in memories])

            # Call your LLM (Bedrock, OpenAI, etc.)
            response = bedrock.invoke_model(
                messages=[
                    {"role": "system", "content": f"Context: {context}"},
                    {"role": "user", "content": user_input}
                ]
            )
            return response['content']

        retrieval_config = {
            "support/facts/{sessionId}": RetrievalConfig(top_k=5, relevance_score=0.3),
            "user/preferences/{actorId}": RetrievalConfig(top_k=3, relevance_score=0.5)
        }

        memories, response, event = manager.process_turn_with_llm(
            actor_id="user-123",
            session_id="session-456",
            user_input="What did we discuss yesterday?",
            llm_callback=my_llm,
            retrieval_config=retrieval_config
        )
    """
    # Step 1: Retrieve relevant memories
    retrieved_memories = []
    if retrieval_config:
        for namespace, config in retrieval_config.items():
            resolved_namespace = namespace.format(
                actorId=actor_id,
                sessionId=session_id,
                strategyId=config.strategy_id or "",
            )
            search_query = f"{config.retrieval_query} {user_input}" if config.retrieval_query else user_input
            memory_records = self.search_long_term_memories(
                query=search_query, namespace_prefix=resolved_namespace, top_k=config.top_k
            )
            # Filter memory records with a relevance score which is lower than config.relevance_score
            if config.relevance_score:
                memory_records = [
                    record
                    for record in memory_records
                    if record.get("relevanceScore", config.relevance_score) >= config.relevance_score
                ]

            retrieved_memories.extend(memory_records)

    logger.info("Retrieved %d memories for LLM context", len(retrieved_memories))

    # Step 2: Invoke LLM callback
    try:
        agent_response = llm_callback(user_input, retrieved_memories)
        if not isinstance(agent_response, str):
            raise ValueError("LLM callback must return a string response")
        logger.info("LLM callback generated response")
    except Exception as e:
        logger.error("LLM callback failed: %s", e)
        raise

    # Step 3: Save the conversation turn
    event = self.add_turns(
        actor_id=actor_id,
        session_id=session_id,
        messages=[
            ConversationalMessage(user_input, MessageRole.USER),
            ConversationalMessage(agent_response, MessageRole.ASSISTANT),
        ],
        event_timestamp=event_timestamp,
    )

    logger.info("Completed full conversation turn with LLM")
    return retrieved_memories, agent_response, event
```

#### `search_long_term_memories(query, namespace_prefix, top_k=3, strategy_id=None, max_results=20)`

Performs a semantic search against the long-term memory for this actor.

Maps to: bedrock-agentcore.retrieve_memory_records.

Source code in `bedrock_agentcore/memory/session.py`

```
def search_long_term_memories(
    self,
    query: str,
    namespace_prefix: str,
    top_k: int = 3,
    strategy_id: str = None,
    max_results: int = 20,
) -> List[MemoryRecord]:
    """Performs a semantic search against the long-term memory for this actor.

    Maps to: bedrock-agentcore.retrieve_memory_records.
    """
    logger.info("  -> Querying long-term memory in namespace '%s' with query: '%s'...", namespace_prefix, query)
    search_criteria = {"searchQuery": query, "topK": top_k}
    if strategy_id:
        search_criteria["strategyId"] = strategy_id

    namespace = namespace_prefix
    params = {
        "memoryId": self._memory_id,
        "searchCriteria": search_criteria,
        "namespace": namespace,
        "maxResults": max_results,
    }

    try:
        response = self._data_plane_client.retrieve_memory_records(**params)
        records = response.get("memoryRecordSummaries", [])
        logger.info("     ✅ Found %d relevant long-term records.", len(records))
        return [MemoryRecord(record) for record in records]
    except ClientError as e:
        logger.info("     ❌ Error querying long-term memory", e)
        raise
```
