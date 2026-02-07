import os
from psycopg import Connection
from psycopg.rows import dict_row
from langgraph.graph import StateGraph, START
from langgraph.checkpoint.postgres import PostgresSaver
from src.nodes.bookingAgent import booking_agent_node
from src.nodes.orchestrator import orchestrator_node
from src.nodes.guardianAgent import guardian_node   
from src.state.AgentState import AgentState
from langgraph.checkpoint.memory import InMemorySaver
from src.nodes.capacityAgent import capacity_node
from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv())

def get_checkpointer():
    # if os.getenv("CI") == "true":
    #     return InMemorySaver()
    db_url = os.getenv(
        "CHECKPOINT_DB_URL",
        "postgresql://postgres:123456789@localhost:5432/microhack_checkpoints",
    )
    conn = Connection.connect(
        db_url, autocommit=True, prepare_threshold=0, row_factory=dict_row
    )
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()
    return checkpointer

def build_agent_graph(checkpointer) -> StateGraph[AgentState]:
    """
    Constructs the agent workflow graph:
    
    START -> Orchestrator -> [Booking | Capacity | Guardian] -> Guardian -> END
    """
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("ORCHESTRATOR", orchestrator_node)
    graph.add_node("BOOKING", booking_agent_node)
    graph.add_node("CAPACITY", capacity_node)
    graph.add_node("GUARDIAN", guardian_node)
    
    # Connect nodes
    graph.add_edge(START, "ORCHESTRATOR")
    
    # Compile graph with proper checkpointer
    return graph.compile(checkpointer=checkpointer)
