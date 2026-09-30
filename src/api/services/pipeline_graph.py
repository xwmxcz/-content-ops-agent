"""LangGraph orchestration; PostgreSQL plan/run_steps remain the only durable state.

Each invocation builds a fresh graph bound to its tenant-scoped pipeline and
worker token. There is deliberately no LangGraph saver or automatic node retry:
recovery rebuilds from run_steps, and the queue owns delivery and lease fencing.
"""

from typing import TYPE_CHECKING, Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from src.api.schemas.agent import PipelineRunResponse
from src.api.services.pipeline_execution import PipelineExecution
from src.api.services.plan_schema import MAX_REVISIONS, MAX_STEPS

if TYPE_CHECKING:
    from src.api.services.dynamic_pipeline import DynamicPipeline


class PipelineGraphState(TypedDict, total=False):
    execution: PipelineExecution
    has_next_step: bool
    response: PipelineRunResponse


# A revision may reset pending steps, but at most MAX_REVISIONS times. Each
# executed business step visits select/execute/revise; add prepare/final select/finish.
GRAPH_RECURSION_LIMIT = 3 * MAX_STEPS * (MAX_REVISIONS + 1) + 4


def build_pipeline_graph(pipeline: "DynamicPipeline"):
    async def prepare(state: PipelineGraphState) -> PipelineGraphState:
        await pipeline._prepare_execution(state["execution"])
        return {"execution": state["execution"]}

    def select(state: PipelineGraphState) -> PipelineGraphState:
        return {"has_next_step": pipeline._select_next_step(state["execution"])}

    def next_node(state: PipelineGraphState) -> Literal["execute_step", "finish"]:
        return "execute_step" if state["has_next_step"] else "finish"

    async def execute_step(state: PipelineGraphState) -> PipelineGraphState:
        await pipeline._execute_step(state["execution"])
        return {"execution": state["execution"]}

    async def revise(state: PipelineGraphState) -> PipelineGraphState:
        await pipeline._revise_after_step(state["execution"])
        return {"execution": state["execution"]}

    async def finish(state: PipelineGraphState) -> PipelineGraphState:
        return {"response": await pipeline._finish_execution(state["execution"])}

    graph = StateGraph(PipelineGraphState)
    graph.add_node("prepare", prepare)
    graph.add_node("select", select)
    graph.add_node("execute_step", execute_step)
    graph.add_node("revise", revise)
    graph.add_node("finish", finish)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "select")
    graph.add_conditional_edges("select", next_node)
    graph.add_edge("execute_step", "revise")
    graph.add_edge("revise", "select")
    graph.add_edge("finish", END)
    return graph.compile()


async def run_pipeline_graph(pipeline: "DynamicPipeline", execution: PipelineExecution) -> PipelineRunResponse:
    state = await build_pipeline_graph(pipeline).ainvoke(
        {"execution": execution}, config={"recursion_limit": GRAPH_RECURSION_LIMIT}
    )
    return state["response"]
