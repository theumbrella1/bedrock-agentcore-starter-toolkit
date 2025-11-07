"""Bedrock AgentCore Memory CLI - Command line interface for Memory operations."""

import json
from typing import Optional

import typer
from rich.table import Table

from ...operations.memory import MemoryManager
from ..common import console

# Create a Typer app for memory commands
memory_app = typer.Typer(help="Manage Bedrock AgentCore Memory resources")


@memory_app.command()
def create(
    name: str = typer.Argument(..., help="Name for the memory resource"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region (default: session region)"),
    description: Optional[str] = typer.Option(None, "--description", "-d", help="Description for the memory"),
    event_expiry_days: int = typer.Option(90, "--event-expiry-days", "-e", help="Event retention in days"),
    strategies: Optional[str] = typer.Option(
        None,
        "--strategies",
        "-s",
        help="JSON string of memory strategies (e.g., '[{\"semanticMemoryStrategy\": {\"name\": \"Facts\"}}]')",
    ),
    memory_execution_role_arn: Optional[str] = typer.Option(
        None, "--role-arn", help="IAM role ARN for memory execution"
    ),
    encryption_key_arn: Optional[str] = typer.Option(None, "--encryption-key-arn", help="KMS key ARN for encryption"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for memory to become ACTIVE"),
    max_wait: int = typer.Option(300, "--max-wait", help="Maximum wait time in seconds"),
) -> None:
    """Create a new memory resource.

    Examples:

        # Create basic memory (STM only)
        agentcore memory create my_agent_memory

        # Create with LTM strategies
        agentcore memory create my_memory --strategies '[{"semanticMemoryStrategy": {"name": "Facts"}}]' --wait
    """
    try:
        manager = MemoryManager(region_name=region, console=console)

        parsed_strategies = None
        if strategies:
            try:
                parsed_strategies = json.loads(strategies)
            except json.JSONDecodeError as e:
                console.print(f"[red]Error parsing strategies JSON: {e}[/red]")
                raise typer.Exit(1)

        console.print(f"[cyan]Creating memory: {name}...[/cyan]")

        if wait:
            memory = manager.create_memory_and_wait(
                name=name,
                strategies=parsed_strategies,
                description=description,
                event_expiry_days=event_expiry_days,
                memory_execution_role_arn=memory_execution_role_arn,
                encryption_key_arn=encryption_key_arn,
                max_wait=max_wait,
            )
        else:
            memory = manager._create_memory(
                name=name,
                strategies=parsed_strategies,
                description=description,
                event_expiry_days=event_expiry_days,
                memory_execution_role_arn=memory_execution_role_arn,
                encryption_key_arn=encryption_key_arn,
            )

        console.print(f"[green]✓ Memory created successfully![/green]")
        console.print(f"[bold]Memory ID:[/bold] {memory.id}")
        console.print(f"[bold]Status:[/bold] {memory.status}")
        console.print(f"[bold]Region:[/bold] {manager.region_name or 'default'}")

    except Exception as e:
        console.print(f"[red]Error creating memory: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command()
def get(
    memory_id: str = typer.Argument(..., help="Memory resource ID"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
) -> None:
    """Get details of a memory resource.

    Example:
        agentcore memory get my_memory_abc123
    """
    try:
        manager = MemoryManager(region_name=region, console=console)
        memory = manager.get_memory(memory_id)

        console.print(f"\n[bold cyan]Memory Details:[/bold cyan]")
        console.print(f"[bold]ID:[/bold] {memory.id}")
        console.print(f"[bold]Name:[/bold] {memory.name}")
        console.print(f"[bold]Status:[/bold] {memory.status}")
        console.print(f"[bold]Description:[/bold] {memory.description or 'N/A'}")
        console.print(f"[bold]Event Expiry:[/bold] {memory.event_expiry_duration} days")

        if memory.strategies:
            console.print(f"\n[bold]Strategies ({len(memory.strategies)}):[/bold]")
            for strategy in memory.strategies:
                console.print(f"  • {strategy.get('name', 'N/A')} ({strategy.get('type', 'N/A')})")

    except Exception as e:
        console.print(f"[red]Error getting memory: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command()
def list(
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
    max_results: int = typer.Option(100, "--max-results", "-n", help="Maximum number of results"),
) -> None:
    """List all memory resources.

    Example:
        agentcore memory list
    """
    try:
        manager = MemoryManager(region_name=region, console=console)
        memories = manager.list_memories(max_results=max_results)

        if not memories:
            console.print("[yellow]No memories found.[/yellow]")
            return

        table = Table(title=f"Memory Resources ({len(memories)})")
        table.add_column("ID", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Created At", style="blue")
        table.add_column("Updated At", style="magenta")

        for memory in memories:
            table.add_row(
                memory.get("id", "N/A"),
                memory.get("status", "N/A"),
                str(memory.get("createdAt", "N/A")),
                str(memory.get("updatedAt", "N/A")),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing memories: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command()
def delete(
    memory_id: str = typer.Argument(..., help="Memory resource ID to delete"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
    wait: bool = typer.Option(False, "--wait", help="Wait for deletion to complete"),
    max_wait: int = typer.Option(300, "--max-wait", help="Maximum wait time in seconds"),
) -> None:
    """Delete a memory resource.

    Example:
        agentcore memory delete my_memory_abc123 --wait
    """
    try:
        manager = MemoryManager(region_name=region, console=console)

        console.print(f"[yellow]Deleting memory: {memory_id}...[/yellow]")

        if wait:
            manager.delete_memory_and_wait(memory_id, max_wait=max_wait)
        else:
            manager.delete_memory(memory_id)

        console.print(f"[green]✓ Memory deleted successfully![/green]")

    except Exception as e:
        console.print(f"[red]Error deleting memory: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command()
def create_event(
    memory_id: str = typer.Argument(..., help="Memory resource ID"),
    actor_id: str = typer.Argument(..., help="Actor ID (e.g., user ID)"),
    payload: str = typer.Argument(..., help="Event payload as JSON string"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
    session_id: Optional[str] = typer.Option(None, "--session-id", "-s", help="Session ID"),
) -> None:
    """Create a memory event for conversation tracking.

    Examples:

        # Single conversational event
        agentcore memory create-event mem_123 user_456 '{"conversational": {"content": {"text": "Hello!"}, "role": "USER"}}'

        # With session ID
        agentcore memory create-event mem_123 user_456 '{"conversational": {"content": {"text": "Hi"}, "role": "USER"}}' --session-id session_789
    """
    try:
        manager = MemoryManager(region_name=region, console=console)

        try:
            event_payload = json.loads(payload)
        except json.JSONDecodeError as e:
            console.print(f"[red]Error parsing payload JSON: {e}[/red]")
            raise typer.Exit(1)

        response = manager.create_memory_event(
            memory_id=memory_id,
            actor_id=actor_id,
            event_payload=event_payload,
            session_id=session_id,
        )

        console.print(f"[green]✓ Event created successfully![/green]")
        console.print(f"[bold]Event ID:[/bold] {response.get('eventId')}")
        console.print(f"[bold]Memory ID:[/bold] {memory_id}")

    except Exception as e:
        console.print(f"[red]Error creating event: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command()
def retrieve(
    memory_id: str = typer.Argument(..., help="Memory resource ID"),
    namespace: str = typer.Argument(..., help="Namespace to search in"),
    query: str = typer.Argument(..., help="Search query text"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
    top_k: int = typer.Option(5, "--top-k", "-k", help="Number of results to return"),
) -> None:
    """Retrieve memories using semantic search.

    Example:
        agentcore memory retrieve mem_123 "/users/user_456/facts" "What are the user preferences?" --top-k 5
    """
    try:
        manager = MemoryManager(region_name=region, console=console)

        records = manager.retrieve_memories(
            memory_id=memory_id,
            namespace=namespace,
            search_query=query,
            top_k=top_k,
        )

        if not records:
            console.print("[yellow]No memory records found.[/yellow]")
            return

        console.print(f"\n[bold cyan]Retrieved {len(records)} memory records:[/bold cyan]\n")
        for i, record in enumerate(records, 1):
            console.print(f"[bold]{i}. Record ID:[/bold] {record.get('memoryRecordId', 'N/A')}")
            console.print(f"   [bold]Content:[/bold] {record.get('content', 'N/A')}")
            console.print(f"   [bold]Score:[/bold] {record.get('score', 'N/A')}\n")

    except Exception as e:
        console.print(f"[red]Error retrieving memories: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command()
def list_actors(
    memory_id: str = typer.Argument(..., help="Memory resource ID"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
    max_results: int = typer.Option(100, "--max-results", "-n", help="Maximum number of results"),
) -> None:
    """List actors in a memory.

    Example:
        agentcore memory list-actors mem_123
    """
    try:
        manager = MemoryManager(region_name=region, console=console)
        actors = manager.list_memory_actors(memory_id=memory_id, max_results=max_results)

        if not actors:
            console.print("[yellow]No actors found.[/yellow]")
            return

        table = Table(title=f"Actors in Memory ({len(actors)})")
        table.add_column("Actor ID", style="cyan")
        table.add_column("Last Activity", style="green")

        for actor in actors:
            table.add_row(
                actor.get("actorId", "N/A"),
                str(actor.get("lastActivityTimestamp", "N/A")),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing actors: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command()
def list_sessions(
    memory_id: str = typer.Argument(..., help="Memory resource ID"),
    actor_id: str = typer.Argument(..., help="Actor ID"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
    max_results: int = typer.Option(100, "--max-results", "-n", help="Maximum number of results"),
) -> None:
    """List sessions for an actor in a memory.

    Example:
        agentcore memory list-sessions mem_123 user_456
    """
    try:
        manager = MemoryManager(region_name=region, console=console)
        sessions = manager.list_memory_sessions(
            memory_id=memory_id,
            actor_id=actor_id,
            max_results=max_results,
        )

        if not sessions:
            console.print("[yellow]No sessions found.[/yellow]")
            return

        table = Table(title=f"Sessions for Actor {actor_id} ({len(sessions)})")
        table.add_column("Session ID", style="cyan")
        table.add_column("Last Activity", style="green")

        for session in sessions:
            table.add_row(
                session.get("sessionId", "N/A"),
                str(session.get("lastActivityTimestamp", "N/A")),
            )

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error listing sessions: {e}[/red]")
        raise typer.Exit(1)


@memory_app.command()
def status(
    memory_id: str = typer.Argument(..., help="Memory resource ID"),
    region: Optional[str] = typer.Option(None, "--region", "-r", help="AWS region"),
) -> None:
    """Get memory provisioning status.

    Example:
        agentcore memory status mem_123
    """
    try:
        manager = MemoryManager(region_name=region, console=console)
        status = manager.get_memory_status(memory_id)

        console.print(f"[bold]Memory Status:[/bold] {status}")
        console.print(f"[bold]Memory ID:[/bold] {memory_id}")

    except Exception as e:
        console.print(f"[red]Error getting status: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    memory_app()
